"""Resolved primary-launch planning for one harness process run."""

import logging
import os
import shlex
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.settings import MeridianConfig, load_config, resolve_repo_root
from meridian.lib.core.types import ModelId
from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.safety.permissions import (
    PermissionConfig,
    resolve_permission_pipeline,
)
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.sync.runtime_ensure import ensure_runtime_assets, plan_required_runtime_assets

from .prompt import compose_skill_injections, resolve_run_defaults
from .resolve import (
    load_agent_profile_with_fallback,
    resolve_harness,
    resolve_skills_from_profile,
)
from .types import LaunchRequest, PrimarySessionMetadata, build_primary_prompt

logger = logging.getLogger(__name__)


class ResolvedPrimaryLaunchPlan(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    repo_root: Path
    state_root: Path
    prompt: str
    request: LaunchRequest
    config: MeridianConfig
    adapter: SubprocessHarness
    session_metadata: PrimarySessionMetadata
    run_params: SpawnParams
    permission_config: PermissionConfig
    command: tuple[str, ...]
    lock_path: Path
    seed_harness_session_id: str
    command_request: LaunchRequest


def normalize_system_prompt_passthrough_args(
    passthrough_args: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Extract system-prompt passthroughs and return args without duplicate prompt flags."""

    cleaned: list[str] = []
    prompt_fragments: list[str] = []
    index = 0
    while index < len(passthrough_args):
        token = passthrough_args[index]

        if token in {"--append-system-prompt", "--system-prompt"}:
            if index + 1 >= len(passthrough_args):
                raise ValueError(f"{token} requires a value")
            prompt_fragments.append(passthrough_args[index + 1])
            index += 2
            continue

        if token.startswith("--append-system-prompt="):
            prompt_fragments.append(token.partition("=")[2])
            index += 1
            continue

        if token.startswith("--system-prompt="):
            prompt_fragments.append(token.partition("=")[2])
            index += 1
            continue

        cleaned.append(token)
        index += 1

    return tuple(cleaned), tuple(prompt_fragments)


def _build_session_metadata(
    *,
    profile_name: str,
    profile_path: str,
    harness_id: str,
    model_id: str,
    skills: tuple[str, ...],
    skill_paths: tuple[str, ...],
) -> PrimarySessionMetadata:
    return PrimarySessionMetadata(
        harness=harness_id,
        model=model_id,
        agent=profile_name,
        agent_path=profile_path,
        skills=skills,
        skill_paths=skill_paths,
    )


def resolve_primary_launch_plan(
    *,
    repo_root: Path,
    request: LaunchRequest,
    harness_registry: HarnessRegistry,
    prompt: str | None = None,
    config: MeridianConfig | None = None,
) -> ResolvedPrimaryLaunchPlan:
    """Resolve one end-to-end primary launch plan without duplicate policy resolution."""

    resolved_root = resolve_repo_root(repo_root)
    resolved_config = config if config is not None else load_config(resolved_root)
    paths = resolve_state_paths(resolved_root)
    state_root = paths.root_dir
    lock_path = paths.active_primary_lock
    resolved_prompt = prompt if prompt is not None else build_primary_prompt(request)
    if not (request.agent or "").strip():
        ensure_runtime_assets(
            repo_root=resolved_root,
            plan=plan_required_runtime_assets(
                repo_root=resolved_root,
                agent_names=(resolved_config.primary_agent,),
            ),
        )

    profile = load_agent_profile_with_fallback(
        repo_root=resolved_root,
        requested_agent=request.agent,
        configured_default=resolved_config.primary_agent,
    )

    default_model = resolved_config.harness.claude
    requested_model = request.model
    if request.harness is not None and request.harness.strip():
        override_default = resolved_config.default_model_for_harness(request.harness)
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
        repo_root=resolved_root,
    )
    adapter = harness_registry.get_subprocess_harness(harness)

    resolved_skills = resolve_skills_from_profile(
        profile_skills=defaults.skills,
        repo_root=resolved_root,
        readonly=True,
    )
    if resolved_skills.missing_skills:
        logger.warning(
            "Skipped unavailable skills for primary agent: %s",
            ", ".join(resolved_skills.missing_skills),
        )

    profile_name = profile.name if profile is not None else ""
    profile_path = ""
    if profile is not None and profile.path.is_absolute() and profile.path.exists():
        profile_path = profile.path.resolve().as_posix()
    skill_paths = tuple(
        Path(skill.path).expanduser().resolve().as_posix()
        for skill in resolved_skills.loaded_skills
    )
    session_metadata = _build_session_metadata(
        profile_name=profile_name,
        profile_path=profile_path,
        harness_id=str(harness),
        model_id=str(model),
        skills=resolved_skills.skill_names,
        skill_paths=skill_paths,
    )

    explicit_harness_session_id = (
        request.continue_harness_session_id.strip()
        if request.continue_harness_session_id is not None
        else ""
    )
    seed = adapter.seed_session(
        is_resume=bool(explicit_harness_session_id),
        harness_session_id=explicit_harness_session_id,
        passthrough_args=request.passthrough_args,
    )
    seed_harness_session_id = seed.session_id
    command_request = request
    if seed.session_args:
        command_request = request.model_copy(
            update={"passthrough_args": (*request.passthrough_args, *seed.session_args)},
        )

    override = os.getenv("MERIDIAN_HARNESS_COMMAND", "").strip()
    if override:
        command = tuple([*shlex.split(override), *command_request.passthrough_args])
        if not command:
            raise ValueError("MERIDIAN_HARNESS_COMMAND resolved to an empty command.")
        run_params = SpawnParams(
            prompt=resolved_prompt,
            model=model,
            skills=resolved_skills.skill_names,
            agent=profile_name or None,
            extra_args=command_request.passthrough_args,
            repo_root=resolved_root.as_posix(),
            mcp_tools=profile.mcp_tools if profile is not None else (),
            interactive=True,
            continue_harness_session_id=explicit_harness_session_id or None,
        )
        return ResolvedPrimaryLaunchPlan(
            repo_root=resolved_root,
            state_root=state_root,
            prompt=resolved_prompt,
            request=request,
            config=resolved_config,
            adapter=adapter,
            session_metadata=session_metadata,
            run_params=run_params,
            permission_config=PermissionConfig(),
            command=command,
            lock_path=lock_path,
            seed_harness_session_id=seed_harness_session_id,
            command_request=command_request,
        )

    passthrough_args, passthrough_prompt_fragments = normalize_system_prompt_passthrough_args(
        command_request.passthrough_args
    )
    permission_config, resolver = resolve_permission_pipeline(
        sandbox=profile.sandbox if profile is not None else None,
        allowed_tools=profile.allowed_tools if profile is not None else (),
        approval=request.approval,
    )

    # Let the adapter decide what prompt/skill content to include.
    # Resume launches typically suppress prompt and skill injection.
    is_resume = bool(explicit_harness_session_id)
    skill_injection = compose_skill_injections(resolved_skills.loaded_skills) or ""
    policy = adapter.filter_launch_content(
        prompt=resolved_prompt,
        skill_injection=skill_injection,
        is_resume=is_resume,
        harness_session_id=explicit_harness_session_id,
    )

    if policy.skill_injection is not None:
        appended_parts = [policy.prompt.strip()]
        appended_parts.extend(
            fragment.strip() for fragment in passthrough_prompt_fragments if fragment.strip()
        )
        if policy.skill_injection:
            appended_parts.append(policy.skill_injection)
        appended_prompt = "\n\n".join(part for part in appended_parts if part)
        appended_system_prompt = appended_prompt if appended_prompt else None
    else:
        appended_prompt = policy.prompt
        appended_system_prompt = None

    run_params = SpawnParams(
        prompt=appended_prompt,
        model=model,
        skills=resolved_skills.skill_names,
        agent=profile_name or None,
        extra_args=passthrough_args,
        repo_root=resolved_root.as_posix(),
        mcp_tools=profile.mcp_tools if profile is not None else (),
        interactive=True,
        continue_harness_session_id=explicit_harness_session_id or None,
        appended_system_prompt=appended_system_prompt,
    )
    command = tuple(adapter.build_command(run_params, resolver))

    return ResolvedPrimaryLaunchPlan(
        repo_root=resolved_root,
        state_root=state_root,
        prompt=resolved_prompt,
        request=request,
        config=resolved_config,
        adapter=adapter,
        session_metadata=session_metadata,
        run_params=run_params,
        permission_config=permission_config,
        command=command,
        lock_path=lock_path,
        seed_harness_session_id=seed_harness_session_id,
        command_request=command_request,
    )


__all__ = [
    "ResolvedPrimaryLaunchPlan",
    "normalize_system_prompt_passthrough_args",
    "resolve_primary_launch_plan",
]
