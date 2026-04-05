"""Shared launch-time resolution helpers for launch orchestration."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.catalog.agent import AgentProfile, load_agent_profile
from meridian.lib.catalog.models import route_model
from meridian.lib.catalog.skill import SkillRegistry
from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.domain import SkillContent
from meridian.lib.core.overrides import RuntimeOverrides, resolve
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.adapter import SubprocessHarness
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.default_agent_policy import (
    resolve_agent_profile_with_builtin_fallback,
)

from .prompt import dedupe_skill_names, load_skill_contents


def load_agent_profile_with_fallback(
    *,
    repo_root: Path,
    requested_agent: str | None = None,
    configured_default: str = "",
) -> AgentProfile | None:
    """Load agent profile with a standard fallback chain.

    Resolution order:
    1. requested_agent (explicit --agent flag) -> load or raise
    2. configured_default (from config) -> try load
    3. None (no profile)
    """

    requested_profile = requested_agent.strip() if requested_agent is not None else ""
    if requested_profile:
        return load_agent_profile(
            requested_profile,
            repo_root=repo_root,
        )

    configured_profile = configured_default.strip()
    if configured_profile:
        return load_agent_profile(
            configured_profile,
            repo_root=repo_root,
        )

    return None


class ResolvedSkills(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_names: tuple[str, ...]
    loaded_skills: tuple[SkillContent, ...]
    missing_skills: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPolicies:
    profile: AgentProfile | None
    model: str
    harness: HarnessId
    adapter: SubprocessHarness
    resolved_skills: ResolvedSkills
    resolved_overrides: RuntimeOverrides
    warning: str | None = None


def resolve_skills_from_profile(
    *,
    profile_skills: tuple[str, ...],
    repo_root: Path,
    readonly: bool = False,
) -> ResolvedSkills:
    """Load and resolve skills declared in an agent profile."""

    registry = SkillRegistry(
        repo_root=repo_root,
        readonly=readonly,
    )
    manifests = registry.list_skills()
    if not manifests and not registry.readonly:
        registry.reindex()
        manifests = registry.list_skills()

    available_skill_names = {item.name for item in manifests}
    missing_skills = tuple(
        skill_name for skill_name in profile_skills if skill_name not in available_skill_names
    )
    resolved_skill_names = tuple(
        skill_name for skill_name in profile_skills if skill_name in available_skill_names
    )
    loaded_skills = load_skill_contents(registry, resolved_skill_names)
    return ResolvedSkills(
        skill_names=tuple(skill.name for skill in loaded_skills),
        loaded_skills=loaded_skills,
        missing_skills=missing_skills,
    )


def format_missing_skills_warning(missing_skills: tuple[str, ...]) -> str:
    """Render a user-facing warning for unavailable skills."""

    if not missing_skills:
        return ""

    expected_paths = [f".agents/skills/{skill}/SKILL.md" for skill in missing_skills]
    expected_lines = [f"Expected: {expected_paths[0]}"]
    expected_lines.extend(f"         {path}" for path in expected_paths[1:])
    return "\n".join(
        (
            f"Warning: Skipped unavailable skills: {', '.join(missing_skills)}",
            *expected_lines,
            "Run `meridian mars sync` to install missing skills.",
        )
    )


def resolve_profile_path(profile: AgentProfile | None) -> str:
    if profile is None:
        return ""
    if profile.path.is_absolute() and profile.path.exists():
        return profile.path.resolve().as_posix()
    return ""


def resolve_skill_paths(loaded_skills: tuple[SkillContent, ...]) -> tuple[str, ...]:
    return tuple(Path(skill.path).expanduser().resolve().as_posix() for skill in loaded_skills)


def resolve_harness(
    *,
    model: ModelId,
    harness_override: str | None,
    harness_registry: HarnessRegistry,
    repo_root: Path,
) -> HarnessId:
    warning: str | None = None
    from meridian.lib.catalog.models import resolve_model

    try:
        resolved = resolve_model(str(model), repo_root=repo_root)
        routed_harness_id = resolved.harness
    except ValueError:
        decision = route_model(str(model), mode="harness", repo_root=repo_root)
        routed_harness_id = decision.harness_id
        warning = decision.warning
    supported_primary_harnesses = tuple(
        harness_id
        for harness_id in harness_registry.ids()
        if harness_registry.get(harness_id).capabilities.supports_primary_launch
    )
    supported_primary_set = set(supported_primary_harnesses)

    normalized_override = (harness_override or "").strip()
    if not normalized_override:
        return routed_harness_id

    override_harness = HarnessId(normalized_override)
    if override_harness not in supported_primary_set:
        supported_text = ", ".join(str(harness_id) for harness_id in supported_primary_harnesses)
        raise ValueError(
            f"Unsupported harness '{normalized_override}'. Expected one of: {supported_text}."
        )
    if override_harness != routed_harness_id:
        message = (
            f"Harness '{override_harness}' is incompatible with model '{model}' "
            f"(routes to '{routed_harness_id}')."
        )
        if warning:
            message = f"{message} {warning}"
        raise ValueError(message)
    return override_harness


def _derive_harness_from_model(model_str: str, *, repo_root: Path) -> HarnessId:
    """Derive harness from model when no layer specifies harness."""

    from meridian.lib.catalog.models import resolve_model as resolve_model_entry

    try:
        resolved = resolve_model_entry(model_str, repo_root=repo_root)
        return resolved.harness
    except ValueError:
        decision = route_model(model_str, mode="harness", repo_root=repo_root)
        return decision.harness_id


def _resolve_final_model(
    *,
    layer_model: str | None,
    harness_id: HarnessId,
    config: MeridianConfig,
    repo_root: Path,
) -> str:
    """Resolve final model string after harness is known."""

    from meridian.lib.catalog.models import resolve_model as resolve_model_entry

    if layer_model:
        try:
            catalog_entry = resolve_model_entry(layer_model, repo_root=repo_root)
            return str(catalog_entry.model_id)
        except ValueError:
            return layer_model
    harness_default = config.default_model_for_harness(str(harness_id))
    if harness_default:
        return harness_default
    if config.default_model:
        return config.default_model
    return ""


def resolve_policies(
    *,
    repo_root: Path,
    layers: tuple[RuntimeOverrides, ...],
    config_overrides: RuntimeOverrides,
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
    builtin_default_agent: str = '',
    configured_default_harness: str = 'claude',
    skills_readonly: bool = True,
) -> ResolvedPolicies:
    pre_profile_resolved = resolve(*layers, config_overrides)
    agent_name = pre_profile_resolved.agent or builtin_default_agent

    profile, profile_warning = resolve_agent_profile_with_builtin_fallback(
        repo_root=repo_root,
        requested_agent=agent_name if pre_profile_resolved.agent else None,
        configured_default=agent_name if not pre_profile_resolved.agent else '',
        builtin_default=builtin_default_agent,
    )
    profile_overrides = RuntimeOverrides.from_agent_profile(profile)
    full_layers = (*layers, profile_overrides, config_overrides)
    resolved = resolve(*full_layers)

    if resolved.harness:
        harness_id = HarnessId(resolved.harness)
    elif resolved.model:
        harness_id = _derive_harness_from_model(resolved.model, repo_root=repo_root)
    else:
        harness_id = HarnessId(configured_default_harness or 'claude')

    try:
        adapter = harness_registry.get_subprocess_harness(harness_id)
    except (KeyError, TypeError) as exc:
        supported = ", ".join(str(harness) for harness in harness_registry.ids())
        raise ValueError(
            f"Unknown or unsupported harness '{harness_id}'. Available harnesses: {supported}"
        ) from exc

    final_model = _resolve_final_model(
        layer_model=resolved.model,
        harness_id=harness_id,
        config=config,
        repo_root=repo_root,
    )

    if final_model and resolved.harness and resolved.model:
        resolve_harness(
            model=ModelId(final_model),
            harness_override=str(harness_id),
            harness_registry=harness_registry,
            repo_root=repo_root,
        )

    profile_skills: tuple[str, ...] = ()
    if profile is not None:
        profile_skills = dedupe_skill_names(profile.skills)
    resolved_skills = resolve_skills_from_profile(
        profile_skills=profile_skills,
        repo_root=repo_root,
        readonly=skills_readonly,
    )

    return ResolvedPolicies(
        profile=profile,
        model=final_model,
        harness=harness_id,
        adapter=adapter,
        resolved_skills=resolved_skills,
        resolved_overrides=resolved,
        warning=profile_warning,
    )


__all__ = [
    "ResolvedPolicies",
    "ResolvedSkills",
    "format_missing_skills_warning",
    "load_agent_profile_with_fallback",
    "resolve_harness",
    "resolve_policies",
    "resolve_profile_path",
    "resolve_skill_paths",
    "resolve_skills_from_profile",
]
