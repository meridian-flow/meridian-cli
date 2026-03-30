"""Resolved primary-launch planning for one harness process run."""

import logging
import os
import shlex
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.config.settings import MeridianConfig, load_config, resolve_repo_root
from meridian.lib.core.overrides import RuntimeOverrides, resolve
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.install.provenance import resolve_runtime_asset_provenance
from meridian.lib.safety.permissions import (
    PermissionConfig,
    resolve_permission_pipeline,
)
from meridian.lib.state.paths import resolve_state_paths

from .prompt import compose_skill_injections
from .resolve import (
    ResolvedPolicies,
    ensure_bootstrap_ready,
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
    command: tuple[str, ...]
    seed_harness_session_id: str
    command_request: LaunchRequest
    warning: str | None = None
    resolved_work_id: str | None = None


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
    profile_source: str | None,
    harness_id: str,
    model_id: str,
    skills: tuple[str, ...],
    skill_paths: tuple[str, ...],
    skill_sources: dict[str, str],
    bootstrap_required_items: tuple[str, ...],
    bootstrap_missing_items: tuple[str, ...],
) -> PrimarySessionMetadata:
    return PrimarySessionMetadata(
        harness=harness_id,
        model=model_id,
        agent=profile_name,
        agent_path=profile_path,
        agent_source=profile_source,
        skills=skills,
        skill_paths=skill_paths,
        skill_sources=skill_sources,
        bootstrap_required_items=bootstrap_required_items,
        bootstrap_missing_items=bootstrap_missing_items,
    )


def _build_run_params(
    *,
    prompt: str,
    model: ModelId | None,
    thinking: str | None,
    skills: tuple[str, ...],
    agent: str | None,
    adhoc_agent_payload: str,
    extra_args: tuple[str, ...],
    repo_root: str,
    mcp_tools: tuple[str, ...],
    continue_harness_session_id: str | None,
    appended_system_prompt: str | None = None,
    report_output_path: str | None = None,
) -> SpawnParams:
    return SpawnParams(
        prompt=prompt,
        model=model,
        thinking=thinking,
        skills=skills,
        agent=agent,
        adhoc_agent_payload=adhoc_agent_payload,
        extra_args=extra_args,
        repo_root=repo_root,
        mcp_tools=mcp_tools,
        interactive=True,
        continue_harness_session_id=continue_harness_session_id,
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
    bootstrap_plan = ensure_bootstrap_ready(
        repo_root=resolved_root,
        configured_default_agent=resolved_config.primary_agent,
        requested_agent=request.agent,
        dry_run=request.dry_run,
        builtin_default_agent="__meridian-orchestrator",
    )
    cli_overrides = RuntimeOverrides.from_launch_request(request)
    env_overrides = RuntimeOverrides.from_env()
    config_overrides = RuntimeOverrides.from_config(resolved_config)
    pre_resolved = resolve(cli_overrides, env_overrides)

    policies: ResolvedPolicies = resolve_policies(
        repo_root=resolved_root,
        overrides=pre_resolved,
        requested_agent=request.agent,
        config=resolved_config,
        harness_registry=harness_registry,
        configured_default_agent=resolved_config.primary_agent,
        builtin_default_agent="__meridian-orchestrator",
        configured_default_harness=resolved_config.primary.harness or "claude",
        skills_readonly=True,
    )
    profile = policies.profile
    profile_overrides = RuntimeOverrides.from_agent_profile(profile)
    resolved = resolve(cli_overrides, env_overrides, profile_overrides, config_overrides)
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
        logger.warning(
            "Skipped unavailable skills for primary agent: %s",
            ", ".join(resolved_skills.missing_skills),
        )

    profile_name = profile.name if profile is not None else ""
    profile_path = resolve_profile_path(profile)
    skill_paths = resolve_skill_paths(resolved_skills.loaded_skills)
    runtime_provenance = resolve_runtime_asset_provenance(
        repo_root=resolved_root,
        agent_path=profile_path,
        skill_paths=skill_paths,
    )
    session_metadata = _build_session_metadata(
        profile_name=profile_name,
        profile_path=profile_path,
        profile_source=runtime_provenance.agent_source,
        harness_id=str(harness),
        model_id=policies.model,
        skills=resolved_skills.skill_names,
        skill_paths=skill_paths,
        skill_sources=runtime_provenance.skill_sources,
        bootstrap_required_items=bootstrap_plan.required_items,
        bootstrap_missing_items=bootstrap_plan.missing_items,
    )

    explicit_harness_session_id = (
        request.continue_harness_session_id.strip()
        if request.continue_harness_session_id is not None
        else ""
    )
    session_intent = SessionIntent(
        mode=request.session_mode,
        harness_session_id=explicit_harness_session_id or None,
        chat_id=request.continue_chat_id,
        forked_from_chat_id=request.forked_from_chat_id,
    )
    continuation_harness_session_id = (
        session_intent.harness_session_id if session_intent.mode != SessionMode.FRESH else None
    )
    seed = adapter.seed_session(
        is_resume=session_intent.mode == SessionMode.RESUME,
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
        run_params = _build_run_params(
            prompt=resolved_prompt,
            model=model,
            thinking=resolved.thinking,
            skills=resolved_skills.skill_names,
            agent=profile_name or None,
            adhoc_agent_payload=adhoc_agent_payload,
            extra_args=command_request.passthrough_args,
            repo_root=resolved_root.as_posix(),
            mcp_tools=profile.mcp_tools if profile is not None else (),
            continue_harness_session_id=continuation_harness_session_id,
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
            seed_harness_session_id=seed_harness_session_id,
            command_request=command_request,
            warning=policies.warning,
        )

    passthrough_args, passthrough_prompt_fragments = normalize_system_prompt_passthrough_args(
        command_request.passthrough_args
    )
    permission_config, resolver = resolve_permission_pipeline(
        sandbox=resolved.sandbox,
        allowed_tools=profile.tools if profile is not None else (),
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
        thinking=resolved.thinking,
        skills=resolved_skills.skill_names,
        agent=profile_name or None,
        adhoc_agent_payload=adhoc_agent_payload,
        extra_args=passthrough_args,
        repo_root=resolved_root.as_posix(),
        mcp_tools=profile.mcp_tools if profile is not None else (),
        continue_harness_session_id=continuation_harness_session_id,
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
        seed_harness_session_id=seed_harness_session_id,
        command_request=command_request,
        warning=policies.warning,
    )


__all__ = [
    "ResolvedPrimaryLaunchPlan",
    "normalize_system_prompt_passthrough_args",
    "resolve_primary_launch_plan",
]
