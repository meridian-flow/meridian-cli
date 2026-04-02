"""Shared launch-time resolution helpers for launch orchestration."""

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.catalog.agent import AgentProfile, load_agent_profile
from meridian.lib.catalog.models import route_model
from meridian.lib.catalog.skill import SkillRegistry
from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.domain import SkillContent
from meridian.lib.core.overrides import RuntimeOverrides
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
    skill_sources: dict[str, Path]
    missing_skills: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedPolicies:
    profile: AgentProfile | None
    model: str
    harness: HarnessId
    adapter: SubprocessHarness
    resolved_skills: ResolvedSkills
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
    skill_sources = {
        skill.name: Path(skill.path).expanduser().resolve().parent for skill in loaded_skills
    }
    return ResolvedSkills(
        skill_names=tuple(skill.name for skill in loaded_skills),
        loaded_skills=loaded_skills,
        skill_sources=skill_sources,
        missing_skills=missing_skills,
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


def resolve_policies(
    *,
    repo_root: Path,
    overrides: RuntimeOverrides,
    requested_agent: str | None,
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
    configured_default_agent: str | None = None,
    builtin_default_agent: str = "",
    configured_default_harness: str = "claude",
    skills_readonly: bool = True,
) -> ResolvedPolicies:
    profile, profile_warning = resolve_agent_profile_with_builtin_fallback(
        repo_root=repo_root,
        requested_agent=requested_agent,
        configured_default=configured_default_agent or "",
        builtin_default=builtin_default_agent,
    )

    resolved_model = (overrides.model or "").strip()
    model_independently_specified = bool(resolved_model)
    if not resolved_model and profile is not None and profile.model:
        resolved_model = profile.model.strip()
        model_independently_specified = bool(resolved_model)

    explicit_harness = (overrides.harness or "").strip()
    profile_harness = ""
    if profile is not None and profile.harness:
        profile_harness = profile.harness.strip()

    if explicit_harness:
        harness_id = HarnessId(explicit_harness)
    elif profile_harness:
        harness_id = HarnessId(profile_harness)
    elif resolved_model:
        harness_id = resolve_harness(
            model=ModelId(resolved_model),
            harness_override=None,
            harness_registry=harness_registry,
            repo_root=repo_root,
        )
    else:
        harness_id = HarnessId(configured_default_harness or "claude")
    harness_independently_specified = bool(explicit_harness or profile_harness)

    try:
        adapter = harness_registry.get_subprocess_harness(harness_id)
    except (KeyError, TypeError) as exc:
        supported = ", ".join(str(harness) for harness in harness_registry.ids())
        raise ValueError(
            f"Unknown or unsupported harness '{harness_id}'. Available harnesses: {supported}"
        ) from exc

    if not resolved_model:
        harness_default = config.default_model_for_harness(str(harness_id))
        if harness_default:
            resolved_model = harness_default
    if not resolved_model and config.default_model:
        resolved_model = config.default_model
        model_independently_specified = bool(resolved_model)

    if resolved_model:
        try:
            from meridian.lib.catalog.models import resolve_model as resolve_model_entry

            catalog_entry = resolve_model_entry(resolved_model, repo_root=repo_root)
            resolved_model = str(catalog_entry.model_id)
        except ValueError:
            pass

    if resolved_model and harness_independently_specified and model_independently_specified:
        resolve_harness(
            model=ModelId(resolved_model),
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
        model=resolved_model,
        harness=harness_id,
        adapter=adapter,
        resolved_skills=resolved_skills,
        warning=profile_warning,
    )


__all__ = [
    "ResolvedPolicies",
    "ResolvedSkills",
    "load_agent_profile_with_fallback",
    "resolve_harness",
    "resolve_policies",
    "resolve_profile_path",
    "resolve_skill_paths",
    "resolve_skills_from_profile",
]
