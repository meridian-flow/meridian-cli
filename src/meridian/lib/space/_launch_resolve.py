"""Resolution logic for primary agent launch — harness routing and session metadata."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from meridian.lib.config.routing import route_model
from meridian.lib.config.settings import MeridianConfig
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch_resolve import (
    load_agent_profile_with_fallback,
    resolve_skills_from_profile,
)
from meridian.lib.prompt.assembly import resolve_run_defaults
from meridian.lib.space._launch_types import SpaceLaunchRequest, _PrimarySessionMetadata
from meridian.lib.types import HarnessId, ModelId

logger = logging.getLogger(__name__)


def _resolve_harness(
    *,
    model: ModelId,
    harness_override: str | None,
    harness_registry: HarnessRegistry,
    repo_root: Path,
) -> HarnessId:
    warning: str | None = None
    from meridian.lib.config.catalog import resolve_model

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


def _resolve_primary_session_metadata(
    *,
    repo_root: Path,
    request: SpaceLaunchRequest,
    config: MeridianConfig,
    harness_registry: HarnessRegistry,
) -> _PrimarySessionMetadata:
    profile = load_agent_profile_with_fallback(
        repo_root=repo_root,
        search_paths=config.search_paths,
        requested_agent=request.agent,
        configured_default=config.default_primary_agent,
        fallback_name="primary",
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
    harness = _resolve_harness(
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

    return _PrimarySessionMetadata(
        harness=str(harness),
        model=str(model),
        agent=profile.name if profile is not None else "",
        agent_path=agent_path,
        skills=skill_names,
        skill_paths=skill_paths,
    )
