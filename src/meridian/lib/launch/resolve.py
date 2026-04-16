"""Shared launch-time resolution helpers for launch orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from meridian.lib.catalog.agent import AgentProfile, load_agent_profile
from meridian.lib.catalog.skill import SkillRegistry
from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.domain import SkillContent
from meridian.lib.core.overrides import RuntimeOverrides
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.registry import HarnessRegistry

from .prompt import load_skill_contents

if TYPE_CHECKING:
    from .policies import ResolvedPolicies


def load_agent_profile_with_fallback(
    *,
    repo_root: Path,
    requested_agent: str | None = None,
    configured_default: str | None = None,
) -> tuple[AgentProfile | None, str | None]:
    """Load agent profile with a standard fallback chain.

    Resolution order:
    1. requested_agent (explicit --agent flag) -> load or raise
    2. configured_default (from config) -> try load
    3. None (no profile)
    """

    requested_profile = requested_agent.strip() if requested_agent is not None else ""
    if requested_profile:
        return (
            load_agent_profile(
                requested_profile,
                repo_root=repo_root,
            ),
            None,
        )

    configured_profile = configured_default.strip() if configured_default is not None else ""
    if configured_profile:
        try:
            return (
                load_agent_profile(
                    configured_profile,
                    repo_root=repo_root,
                ),
                None,
            )
        except FileNotFoundError:
            return (
                None,
                "Configured agent profile "
                f"'{configured_profile}' is unavailable; running without an agent profile.",
            )

    return None, None


class ResolvedSkills(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_names: tuple[str, ...]
    loaded_skills: tuple[SkillContent, ...]
    missing_skills: tuple[str, ...]


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
    from meridian.lib.catalog.models import resolve_model

    resolved = resolve_model(str(model), repo_root=repo_root)
    routed_harness_id = resolved.harness
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
        raise ValueError(message)
    return override_harness


def resolve_policies(
    *,
    repo_root: Path,
    layers: tuple[RuntimeOverrides, ...],
    config_overrides: RuntimeOverrides,
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
    configured_default_harness: str = "claude",
    skills_readonly: bool = True,
) -> ResolvedPolicies:
    """Compatibility shim forwarding to stage-owned policy resolver."""

    from .policies import resolve_policies as _resolve_policies

    return _resolve_policies(
        repo_root=repo_root,
        layers=layers,
        config_overrides=config_overrides,
        config=config,
        harness_registry=harness_registry,
        configured_default_harness=configured_default_harness,
        skills_readonly=skills_readonly,
    )


__all__ = [
    "ResolvedSkills",
    "format_missing_skills_warning",
    "load_agent_profile_with_fallback",
    "resolve_harness",
    "resolve_policies",
    "resolve_profile_path",
    "resolve_skill_paths",
    "resolve_skills_from_profile",
]
