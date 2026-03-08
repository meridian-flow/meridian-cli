"""Shared launch-time resolution helpers for launch orchestration."""


import logging
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from meridian.lib.catalog.agent import AgentProfile, load_agent_profile
from meridian.lib.catalog.models import route_model
from meridian.lib.config.settings import MeridianConfig, SearchPathConfig
from meridian.lib.catalog.skill import SkillRegistry
from meridian.lib.core.domain import SkillContent
from meridian.lib.harness.registry import HarnessRegistry
from .prompt import load_skill_contents, resolve_run_defaults
from meridian.lib.safety.permissions import permission_tier_from_profile
from meridian.lib.core.types import HarnessId, ModelId

from .types import PrimarySessionMetadata, SpaceLaunchRequest

logger = logging.getLogger(__name__)


class _WarningLogger(Protocol):
    def warning(self, message: str, *args: object) -> None: ...


def load_agent_profile_with_fallback(
    *,
    repo_root: Path,
    search_paths: SearchPathConfig | None = None,
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
            search_paths=search_paths,
        )

    configured_profile = configured_default.strip()
    if configured_profile:
        try:
            return load_agent_profile(
                configured_profile,
                repo_root=repo_root,
                search_paths=search_paths,
            )
        except FileNotFoundError:
            pass

    return None


class ResolvedSkills(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_names: tuple[str, ...]
    loaded_skills: tuple[SkillContent, ...]
    skill_sources: dict[str, Path]
    missing_skills: tuple[str, ...]


def resolve_skills_from_profile(
    *,
    profile_skills: tuple[str, ...],
    repo_root: Path,
    search_paths: SearchPathConfig | None = None,
    readonly: bool = False,
) -> ResolvedSkills:
    """Load and resolve skills declared in an agent profile."""

    registry = SkillRegistry(
        repo_root=repo_root,
        search_paths=search_paths,
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


def resolve_permission_tier_from_profile(
    *,
    profile: AgentProfile | None,
    default_tier: str,
    warning_logger: _WarningLogger | None = None,
) -> str:
    """Infer permission tier from agent profile sandbox field."""

    sandbox_value = profile.sandbox if profile is not None else None
    inferred_tier = permission_tier_from_profile(sandbox_value)
    if inferred_tier is not None:
        return inferred_tier

    if profile is not None and sandbox_value is not None and sandbox_value.strip():
        sink = warning_logger or logger
        sink.warning(
            "Agent profile '%s' has unsupported sandbox '%s'; "
            "falling back to default permission tier '%s'.",
            profile.name,
            sandbox_value.strip(),
            default_tier,
        )
    return default_tier


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
        decision = route_model(str(model), mode="harness")
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
            f"Unsupported harness '{normalized_override}'. "
            f"Expected one of: {supported_text}."
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


def resolve_primary_session_metadata(
    *,
    repo_root: Path,
    request: SpaceLaunchRequest,
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
) -> PrimarySessionMetadata:
    profile = load_agent_profile_with_fallback(
        repo_root=repo_root,
        search_paths=config.search_paths,
        requested_agent=request.agent,
        configured_default=config.default_primary_agent,
    )

    default_model = config.harness.claude
    requested_model = request.model
    if request.harness is not None and request.harness.strip():
        override_default = config.default_model_for_harness(request.harness)
        if override_default:
            default_model = override_default
            if not requested_model.strip():
                requested_model = override_default

    defaults = resolve_run_defaults(
        requested_model,
        profile=profile,
        default_model=default_model,
    )
    model = ModelId(defaults.model)
    harness = resolve_harness(
        model=model,
        harness_override=request.harness,
        harness_registry=harness_registry,
        repo_root=repo_root,
    )

    resolved_skills = resolve_skills_from_profile(
        profile_skills=defaults.skills,
        repo_root=repo_root,
        search_paths=config.search_paths,
        readonly=True,
    )
    if resolved_skills.missing_skills:
        logger.warning(
            "Skipped unavailable skills for primary agent: %s",
            ", ".join(resolved_skills.missing_skills),
        )
    skill_names = resolved_skills.skill_names
    skill_paths = tuple(
        Path(skill.path).expanduser().resolve().as_posix()
        for skill in resolved_skills.loaded_skills
    )

    agent_path = ""
    if profile is not None and profile.path.is_absolute() and profile.path.exists():
        agent_path = profile.path.resolve().as_posix()

    return PrimarySessionMetadata(
        harness=str(harness),
        model=str(model),
        agent=profile.name if profile is not None else "",
        agent_path=agent_path,
        skills=skill_names,
        skill_paths=skill_paths,
    )


__all__ = [
    "ResolvedSkills",
    "load_agent_profile_with_fallback",
    "resolve_harness",
    "resolve_permission_tier_from_profile",
    "resolve_primary_session_metadata",
    "resolve_skills_from_profile",
]
