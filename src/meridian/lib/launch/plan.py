"""Resolved primary-launch planning for one harness process run."""

import logging
import os
import shlex
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.settings import MeridianConfig, load_config, resolve_repo_root
from meridian.lib.core.overrides import RuntimeOverrides
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.launch_types import PermissionResolver
from meridian.lib.safety.permissions import (
    PermissionConfig,
    resolve_permission_pipeline,
)
from meridian.lib.state.paths import resolve_state_paths

from .prompt import build_primary_inventory_prompt, compose_skill_injections
from .resolve import (
    ResolvedPolicies,
    format_missing_skills_warning,
    resolve_policies,
    resolve_profile_path,
    resolve_skill_paths,
)
from .types import (
    LaunchRequest,
    PrimarySessionMetadata,
    SessionIntent,
    SessionMode,
    build_primary_prompt,
)

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
    permission_resolver: PermissionResolver | None = None
    command: tuple[str, ...]
    seed_harness_session_id: str
    command_request: LaunchRequest
    warning: str | None = None
    resolved_work_id: str | None = None
    source_execution_cwd: str | None = None


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


def _build_run_params(
    *,
    prompt: str,
    model: ModelId | None,
    effort: str | None,
    skills: tuple[str, ...],
    agent: str | None,
    adhoc_agent_payload: str,
    extra_args: tuple[str, ...],
    repo_root: str,
    mcp_tools: tuple[str, ...],
    continue_harness_session_id: str | None,
    continue_fork: bool = False,
    appended_system_prompt: str | None = None,
    report_output_path: str | None = None,
) -> SpawnParams:
    return SpawnParams(
        prompt=prompt,
        model=model,
        effort=effort,
        skills=skills,
        agent=agent,
        adhoc_agent_payload=adhoc_agent_payload,
        extra_args=extra_args,
        repo_root=repo_root,
        mcp_tools=mcp_tools,
        interactive=True,
        continue_harness_session_id=continue_harness_session_id,
        continue_fork=continue_fork,
        appended_system_prompt=appended_system_prompt,
        report_output_path=report_output_path,
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
    state_root = resolve_state_paths(resolved_root).root_dir
    resolved_prompt = prompt if prompt is not None else build_primary_prompt(request)
    cli_overrides = RuntimeOverrides.from_launch_request(request)
    env_overrides = RuntimeOverrides.from_env()
    config_overrides = RuntimeOverrides.from_config(resolved_config)

    policies: ResolvedPolicies = resolve_policies(
        repo_root=resolved_root,
        layers=(cli_overrides, env_overrides),
        config_overrides=config_overrides,
        config=resolved_config,
        harness_registry=harness_registry,
        configured_default_harness=resolved_config.primary.harness or "claude",
        skills_readonly=True,
    )
    profile = policies.profile
    resolved = policies.resolved_overrides
    model = ModelId(policies.model) if policies.model else None
    harness = policies.harness
    adapter = policies.adapter
    resolved_skills = policies.resolved_skills
    adhoc_agent_payload = (
        adapter.build_adhoc_agent_payload(
            name=profile.name,
            description=profile.description,
            prompt=profile.body,
        )
        if profile is not None and adapter.capabilities.supports_native_agents
        else ""
    )

    if resolved_skills.missing_skills:
        logger.warning("%s", format_missing_skills_warning(resolved_skills.missing_skills))

    profile_name = profile.name if profile is not None else ""
    profile_path = resolve_profile_path(profile)
    skill_paths = resolve_skill_paths(resolved_skills.loaded_skills)
    session_metadata = _build_session_metadata(
        profile_name=profile_name,
        profile_path=profile_path,
        harness_id=str(harness),
        model_id=policies.model,
        skills=resolved_skills.skill_names,
        skill_paths=skill_paths,
    )

    resolved_harness_session_id = (request.session.harness_session_id or "").strip() or None
    resolved_continue_chat_id = (request.session.continue_chat_id or "").strip() or None
    resolved_continue_fork = request.session.continue_fork
    resolved_forked_from_chat_id = request.session.forked_from_chat_id
    resolved_continue_harness = (request.session.continue_harness or "").strip() or None
    source_execution_cwd = request.session.source_execution_cwd
    resolved_session = request.session.model_copy(
        update={
            "harness_session_id": resolved_harness_session_id,
            "continue_harness": resolved_continue_harness,
            "continue_chat_id": resolved_continue_chat_id,
            "continue_fork": resolved_continue_fork,
            "forked_from_chat_id": resolved_forked_from_chat_id,
        }
    )
    resolved_request = request.model_copy(
        update={
            "session": resolved_session,
        }
    )

    explicit_harness_session_id = resolved_harness_session_id or ""
    session_intent = SessionIntent(
        mode=resolved_request.session_mode,
        harness_session_id=explicit_harness_session_id or None,
        chat_id=resolved_request.session.continue_chat_id,
        forked_from_chat_id=resolved_request.session.forked_from_chat_id,
    )
    continuation_harness_session_id = (
        session_intent.harness_session_id if session_intent.mode != SessionMode.FRESH else None
    )
    continue_fork = (
        session_intent.mode == SessionMode.FORK or resolved_request.session.continue_fork
    )
    if session_intent.mode != SessionMode.RESUME:
        inventory_prompt = build_primary_inventory_prompt(repo_root=resolved_root)
        if inventory_prompt:
            resolved_prompt = "\n\n".join((resolved_prompt, inventory_prompt))
    seed = adapter.seed_session(
        is_resume=session_intent.mode == SessionMode.RESUME,
        harness_session_id=explicit_harness_session_id,
        passthrough_args=resolved_request.passthrough_args,
    )
    seed_harness_session_id = seed.session_id
    command_request = resolved_request
    if seed.session_args:
        command_request = resolved_request.model_copy(
            update={
                "passthrough_args": (*resolved_request.passthrough_args, *seed.session_args)
            },
        )

    override = os.getenv("MERIDIAN_HARNESS_COMMAND", "").strip()
    if override:
        if continue_fork:
            raise ValueError(
                "Cannot use --fork with MERIDIAN_HARNESS_COMMAND override. "
                "Fork requires native harness adapter support."
            )
        command = tuple([*shlex.split(override), *command_request.passthrough_args])
        if not command:
            raise ValueError("MERIDIAN_HARNESS_COMMAND resolved to an empty command.")
        run_params = _build_run_params(
            prompt=resolved_prompt,
            model=model,
            effort=resolved.effort,
            skills=resolved_skills.skill_names,
            agent=profile_name or None,
            adhoc_agent_payload=adhoc_agent_payload,
            extra_args=command_request.passthrough_args,
            repo_root=resolved_root.as_posix(),
            mcp_tools=profile.mcp_tools if profile is not None else (),
            continue_harness_session_id=continuation_harness_session_id,
            continue_fork=continue_fork,
        )
        return ResolvedPrimaryLaunchPlan(
            repo_root=resolved_root,
            state_root=state_root,
            prompt=resolved_prompt,
            request=resolved_request,
            config=resolved_config,
            adapter=adapter,
            session_metadata=session_metadata,
            run_params=run_params,
            permission_config=PermissionConfig(),
            permission_resolver=None,
            command=command,
            seed_harness_session_id=seed_harness_session_id,
            command_request=command_request,
            warning=policies.warning,
            source_execution_cwd=source_execution_cwd,
        )

    passthrough_args, passthrough_prompt_fragments = normalize_system_prompt_passthrough_args(
        command_request.passthrough_args
    )
    permission_config, resolver = resolve_permission_pipeline(
        sandbox=resolved.sandbox,
        allowed_tools=profile.tools if profile is not None else (),
        disallowed_tools=profile.disallowed_tools if profile is not None else (),
        approval=resolved.approval or "default",
    )

    # Let the adapter decide what prompt/skill content to include.
    # Resume launches typically suppress prompt and skill injection.
    is_resume = session_intent.mode == SessionMode.RESUME
    skill_injection = compose_skill_injections(resolved_skills.loaded_skills) or ""
    if adapter.id == HarnessId.CODEX and profile is not None and profile.body.strip():
        skill_injection = "\n\n".join(
            part
            for part in (
                f"# Agent Profile\n\n{profile.body.strip()}",
                skill_injection.strip(),
            )
            if part
        )
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

    run_params = _build_run_params(
        prompt=appended_prompt,
        model=model,
        effort=resolved.effort,
        skills=resolved_skills.skill_names,
        agent=profile_name or None,
        adhoc_agent_payload=adhoc_agent_payload,
        extra_args=passthrough_args,
        repo_root=resolved_root.as_posix(),
        mcp_tools=profile.mcp_tools if profile is not None else (),
        continue_harness_session_id=continuation_harness_session_id,
        continue_fork=continue_fork,
        appended_system_prompt=appended_system_prompt,
    )
    command = tuple(adapter.build_command(run_params, resolver))

    return ResolvedPrimaryLaunchPlan(
        repo_root=resolved_root,
        state_root=state_root,
        prompt=resolved_prompt,
        request=resolved_request,
        config=resolved_config,
        adapter=adapter,
        session_metadata=session_metadata,
        run_params=run_params,
        permission_config=permission_config,
        permission_resolver=resolver,
        command=command,
        seed_harness_session_id=seed_harness_session_id,
        command_request=command_request,
        warning=policies.warning,
        source_execution_cwd=source_execution_cwd,
    )


__all__ = [
    "ResolvedPrimaryLaunchPlan",
    "normalize_system_prompt_passthrough_args",
    "resolve_primary_launch_plan",
]
