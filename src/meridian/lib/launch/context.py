"""Shared launch-context assembly used by subprocess and streaming runners."""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from meridian.lib.config.project_paths import ProjectPaths
from meridian.lib.config.settings import MeridianConfig, load_config
from meridian.lib.config.workspace import get_projectable_roots
from meridian.lib.core.overrides import RuntimeOverrides
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.adapter import SubprocessHarness
from meridian.lib.harness.workspace_projection import (
    OPENCODE_CONFIG_CONTENT_ENV,
    project_workspace_roots,
)
from meridian.lib.launch.launch_types import (
    CompositionWarning,
    PermissionResolver,
    PreflightResult,
    ResolvedLaunchSpec,
    summarize_composition_warnings,
)
from meridian.lib.state.paths import (
    resolve_spawn_log_dir,
)

from .command import (
    build_launch_argv,
    normalize_system_prompt_passthrough_args,
    resolve_launch_spec_stage,
)
from .cwd import resolve_child_execution_cwd
from .env import build_env_plan, inherit_child_env
from .env import merge_env_overrides as _merge_env_overrides
from .permissions import resolve_permission_pipeline
from .policies import resolve_policies
from .prompt import (
    build_primary_inventory_prompt,
    compose_run_prompt_text,
    compose_skill_injections,
    dedupe_skill_names,
)
from .reference import load_reference_files
from .request import (
    LaunchArgvIntent,
    LaunchCompositionSurface,
    LaunchRuntime,
    SpawnRequest,
)
from .resolve import (
    format_missing_skills_warning,
    resolve_profile_path,
    resolve_skill_paths,
    resolve_skills_from_profile,
)
from .run_inputs import ResolvedRunInputs
from .workspace import resolve_workspace_snapshot_for_launch

if TYPE_CHECKING:
    from meridian.lib.harness.registry import HarnessRegistry

_ALLOWED_MERIDIAN_KEYS: frozenset[str] = frozenset(
    {
        "MERIDIAN_REPO_ROOT",
        "MERIDIAN_STATE_ROOT",
        "MERIDIAN_DEPTH",
        "MERIDIAN_CHAT_ID",
    }
)


@dataclass(frozen=True)
class ChildEnvContext:
    """Sole producer for child `MERIDIAN_*` environment overrides."""

    repo_root: Path
    state_root: Path
    parent_chat_id: str | None
    parent_depth: int

    @classmethod
    def from_environment(
        cls,
        *,
        project_paths: ProjectPaths,
        state_root: Path,
    ) -> ChildEnvContext:
        parent_chat_id = os.getenv("MERIDIAN_CHAT_ID", "").strip() or None
        parent_depth_raw = os.getenv("MERIDIAN_DEPTH", "0").strip()
        parent_depth = 0
        try:
            parent_depth = max(0, int(parent_depth_raw))
        except (TypeError, ValueError):
            parent_depth = 0

        return cls(
            # Keep launch semantics unchanged: runtime repo_root follows the
            # execution cwd used by the child process.
            repo_root=project_paths.execution_cwd.resolve(),
            state_root=state_root.resolve(),
            parent_chat_id=parent_chat_id,
            parent_depth=parent_depth,
        )

    def child_context(self) -> dict[str, str]:
        overrides: dict[str, str] = {
            "MERIDIAN_REPO_ROOT": self.repo_root.as_posix(),
            "MERIDIAN_STATE_ROOT": self.state_root.as_posix(),
            "MERIDIAN_DEPTH": str(self.parent_depth + 1),
        }
        if self.parent_chat_id:
            overrides["MERIDIAN_CHAT_ID"] = self.parent_chat_id

        if not set(overrides).issubset(_ALLOWED_MERIDIAN_KEYS):
            missing = sorted(set(overrides) - _ALLOWED_MERIDIAN_KEYS)
            raise RuntimeError(f"ChildEnvContext.child_context drifted keys: {missing}")
        return overrides


@dataclass(frozen=True)
class LaunchContext:
    request: SpawnRequest
    runtime: LaunchRuntime
    repo_root: Path
    execution_cwd: Path
    state_root: Path
    work_id: str | None
    argv: tuple[str, ...]
    run_params: ResolvedRunInputs
    perms: PermissionResolver
    spec: ResolvedLaunchSpec
    child_cwd: Path
    env: Mapping[str, str]
    env_overrides: Mapping[str, str]
    report_output_path: Path
    harness: SubprocessHarness
    resolved_request: SpawnRequest
    seed_harness_session_id: str | None = None
    is_bypass: bool = False
    # I-13: adapter input transformations surface here instead of silently mutating.
    warnings: tuple[CompositionWarning, ...] = ()


def merge_env_overrides(
    *,
    plan_overrides: Mapping[str, str],
    runtime_overrides: Mapping[str, str],
    preflight_overrides: Mapping[str, str],
) -> dict[str, str]:
    """Merge launch env overrides with `MERIDIAN_*` leak checks."""

    return _merge_env_overrides(
        plan_overrides=plan_overrides,
        runtime_overrides=runtime_overrides,
        preflight_overrides=preflight_overrides,
    )


def _build_composition_warnings(
    *,
    request_warning: str | None,
    policy_warning: str | None,
    route_warning: str | None,
    missing_skills_warning: str | None,
    continuation_warning: str | None,
) -> tuple[CompositionWarning, ...]:
    warnings: list[CompositionWarning] = []
    for code, message in (
        ("request_warning", request_warning),
        ("policy_warning", policy_warning),
        ("route_warning", route_warning),
        ("missing_skills", missing_skills_warning),
        ("continuation_warning", continuation_warning),
    ):
        normalized = (message or "").strip()
        if not normalized:
            continue
        warnings.append(CompositionWarning(code=code, message=normalized))
    return tuple(warnings)


def _missing_continue_session_error(source_ref: str | None) -> str:
    normalized_source = (source_ref or "").strip()
    if normalized_source:
        if normalized_source.startswith("p") and normalized_source[1:].isdigit():
            return (
                f"Spawn '{normalized_source}' has no recorded session - "
                "cannot continue/fork."
            )
        return (
            f"Session '{normalized_source}' has no recorded harness session - "
            "cannot continue/fork."
        )
    return "Source reference has no recorded harness session - cannot continue/fork."


def _spawn_request_overrides(request: SpawnRequest) -> RuntimeOverrides:
    return RuntimeOverrides(
        model=(request.model or "").strip() or None,
        harness=(request.harness or "").strip() or None,
        agent=(request.agent or "").strip() or None,
        effort=(request.effort or "").strip() or None,
        sandbox=(request.sandbox or "").strip() or None,
        approval=(request.approval or "").strip() or None,
        autocompact=request.autocompact,
    )


def _resolve_harness_id(
    *,
    request: SpawnRequest,
    runtime: LaunchRuntime,
) -> HarnessId:
    explicit_harness = (request.harness or "").strip()
    if explicit_harness:
        try:
            return HarnessId(explicit_harness)
        except ValueError as exc:
            raise ValueError(f"Unknown harness '{explicit_harness}'.") from exc

    override = (runtime.harness_command_override or "").strip()
    if override:
        command_tokens = shlex.split(override)
        if command_tokens:
            command_name = Path(command_tokens[0]).name.strip().lower()
            if command_name:
                try:
                    return HarnessId(command_name)
                except ValueError as exc:
                    raise ValueError(
                        "LaunchRuntime.harness_command_override must start with a known harness "
                        f"binary name; got '{command_name}'."
                    ) from exc

    raise ValueError("SpawnRequest.harness is required when no command override is present.")


def _resolve_report_output_path(
    *,
    runtime: LaunchRuntime,
    project_paths: ProjectPaths,
    spawn_id: str,
) -> Path:
    report_path_raw = (runtime.report_output_path or "").strip()
    if report_path_raw:
        return Path(report_path_raw).expanduser()
    return resolve_spawn_log_dir(project_paths.repo_root, spawn_id) / "report.md"


def _build_bypass_context(
    *,
    override: str,
    preflight: PreflightResult,
    env_overrides: Mapping[str, str],
) -> tuple[tuple[str, ...], dict[str, str]]:
    command = tuple([*shlex.split(override), *preflight.expanded_passthrough_args])
    if not command:
        raise ValueError("MERIDIAN_HARNESS_COMMAND resolved to an empty command.")
    env = inherit_child_env(
        base_env=os.environ,
        env_overrides=env_overrides,
    )
    return command, env


def _resolve_surface_request(
    *,
    request: SpawnRequest,
    runtime: LaunchRuntime,
    project_paths: ProjectPaths,
    harness_registry: HarnessRegistry,
    dry_run: bool,
) -> tuple[SpawnRequest, SubprocessHarness, str | None, tuple[CompositionWarning, ...]]:
    config = (
        MeridianConfig.model_validate(runtime.config_snapshot)
        if runtime.config_snapshot
        else load_config(project_paths.repo_root)
    )
    cli_overrides = _spawn_request_overrides(request)
    env_overrides = RuntimeOverrides.from_env()
    if runtime.composition_surface == LaunchCompositionSurface.PRIMARY:
        config_overrides = RuntimeOverrides.from_config(config)
        configured_default_harness = config.primary.harness or "claude"
    else:
        config_overrides = RuntimeOverrides.from_spawn_config(config)
        configured_default_harness = config.default_harness

    policies = resolve_policies(
        repo_root=project_paths.repo_root,
        layers=(cli_overrides, env_overrides),
        config_overrides=config_overrides,
        config=config,
        harness_registry=harness_registry,
        configured_default_harness=configured_default_harness,
        skills_readonly=dry_run,
    )
    profile = policies.profile
    resolved = policies.resolved_overrides
    harness = policies.adapter
    resolved_skills = policies.resolved_skills
    if request.skills:
        merged_skill_names = dedupe_skill_names((*resolved_skills.skill_names, *request.skills))
        resolved_skills = resolve_skills_from_profile(
            profile_skills=merged_skill_names,
            repo_root=project_paths.repo_root,
            readonly=dry_run,
        )

    route_warning = None
    reference_mode = harness.capabilities.reference_input_mode
    prompt_policy = harness.run_prompt_policy()
    resolved_context_from = request.context_from
    prompt = request.prompt
    if (
        runtime.composition_surface == LaunchCompositionSurface.SPAWN_PREPARE
        and not request.prompt_is_composed
    ):
        loaded_references = load_reference_files(
            request.reference_files,
            base_dir=project_paths.repo_root,
            include_content=reference_mode != "paths",
        )
        prior_output: str | None = None
        if request.context_from:
            from meridian.lib.ops.spawn.context_ref import (
                render_context_refs,
                resolve_context_ref,
            )

            resolved_context_refs = tuple(
                resolve_context_ref(project_paths.repo_root, ref) for ref in request.context_from
            )
            resolved_context_from = tuple(ref.spawn_id for ref in resolved_context_refs)
            prior_output = render_context_refs(resolved_context_refs)
        prompt = compose_run_prompt_text(
            skills=resolved_skills.loaded_skills if prompt_policy.include_skills else (),
            references=loaded_references,
            user_prompt=request.prompt,
            agent_body=(profile.body.strip() if profile is not None else "")
            if prompt_policy.include_agent_body
            else "",
            template_variables=request.template_vars,
            prior_output=prior_output,
            reference_mode=reference_mode,
        )

    requested_harness_session_id = (
        (request.session.requested_harness_session_id or "").strip() or None
    )
    requested_continue_fork = request.session.continue_fork
    requested_harness = (request.session.continue_harness or "").strip()
    if request.session.continue_source_tracked and requested_harness_session_id is None:
        raise ValueError(_missing_continue_session_error(request.session.continue_source_ref))

    resolved_continue_harness_session_id: str | None = None
    resolved_continue_fork = False
    continuation_warning: str | None = None
    if requested_harness_session_id:
        if requested_harness and requested_harness != str(harness.id):
            continuation_warning = (
                "Continuation session ignored because target harness differs from source run."
            )
        elif not harness.capabilities.supports_session_resume:
            continuation_warning = (
                f"Harness '{harness.id}' does not support session resume; starting fresh."
            )
        else:
            resolved_continue_harness_session_id = requested_harness_session_id
            if requested_continue_fork:
                if harness.capabilities.supports_session_fork:
                    resolved_continue_fork = True
                else:
                    continuation_warning = (
                        f"Harness '{harness.id}' does not support session fork; "
                        "resuming in-place."
                    )

    final_prompt = prompt
    final_passthrough_args = request.extra_args
    appended_system_prompt: str | None = None
    seed_harness_session_id = resolved_continue_harness_session_id
    if runtime.composition_surface == LaunchCompositionSurface.PRIMARY:
        session_mode = (
            (request.session.primary_session_mode or "fresh").strip().lower()
        ) or "fresh"
        if session_mode != "resume":
            inventory_prompt = build_primary_inventory_prompt(repo_root=project_paths.repo_root)
            if inventory_prompt:
                final_prompt = "\n\n".join((final_prompt, inventory_prompt))

        seed = harness.seed_session(
            is_resume=session_mode == "resume",
            harness_session_id=resolved_continue_harness_session_id or "",
            passthrough_args=request.extra_args,
        )
        seed_harness_session_id = seed.session_id
        seeded_passthrough_args = (*request.extra_args, *seed.session_args)
        override = (runtime.harness_command_override or "").strip()
        if override and resolved_continue_fork:
            raise ValueError(
                "Cannot use --fork with MERIDIAN_HARNESS_COMMAND override. "
                "Fork requires native harness adapter support."
            )

        final_passthrough_args = seeded_passthrough_args
        if not override:
            passthrough_args, passthrough_prompt_fragments = (
                normalize_system_prompt_passthrough_args(seeded_passthrough_args)
            )
            final_passthrough_args = passthrough_args
            skill_injection = compose_skill_injections(resolved_skills.loaded_skills) or ""
            if harness.id == HarnessId.CODEX and profile is not None and profile.body.strip():
                skill_injection = "\n\n".join(
                    part
                    for part in (
                        f"# Agent Profile\n\n{profile.body.strip()}",
                        skill_injection.strip(),
                    )
                    if part
                )
            policy = harness.filter_launch_content(
                prompt=final_prompt,
                skill_injection=skill_injection,
                is_resume=session_mode == "resume",
                harness_session_id=resolved_continue_harness_session_id or "",
            )
            if policy.skill_injection is not None:
                appended_parts = [policy.prompt.strip()]
                appended_parts.extend(
                    fragment.strip()
                    for fragment in passthrough_prompt_fragments
                    if fragment.strip()
                )
                if policy.skill_injection:
                    appended_parts.append(policy.skill_injection)
                final_prompt = "\n\n".join(part for part in appended_parts if part)
                appended_system_prompt = final_prompt if final_prompt else None
            else:
                final_prompt = policy.prompt
    elif prompt_policy.skill_injection_mode == "append-system-prompt":
        appended_system_prompt = compose_skill_injections(resolved_skills.loaded_skills) or None

    missing_skills_warning = (
        format_missing_skills_warning(resolved_skills.missing_skills)
        if resolved_skills.missing_skills
        else None
    )
    composition_warnings = _build_composition_warnings(
        request_warning=request.warning,
        policy_warning=policies.warning,
        route_warning=route_warning,
        missing_skills_warning=missing_skills_warning,
        continuation_warning=continuation_warning,
    )
    warning = summarize_composition_warnings(composition_warnings)

    agent_metadata = dict(request.agent_metadata)
    resolved_agent_name = profile.name if profile is not None else request.agent
    session_agent_path = resolve_profile_path(profile)
    if resolved_agent_name is not None:
        agent_metadata["session_agent"] = resolved_agent_name
    if session_agent_path:
        agent_metadata["session_agent_path"] = session_agent_path
    if profile is not None and harness.capabilities.supports_native_agents:
        agent_metadata["adhoc_agent_payload"] = harness.build_adhoc_agent_payload(
            name=profile.name,
            description=profile.description,
            prompt=profile.body,
        )
    if appended_system_prompt:
        agent_metadata["appended_system_prompt"] = appended_system_prompt

    resolved_request = request.model_copy(
        update={
            "prompt": final_prompt,
            "prompt_is_composed": True,
            "model": policies.model,
            "harness": str(policies.harness),
            "agent": resolved_agent_name,
            "skills": resolved_skills.skill_names,
            "extra_args": final_passthrough_args,
            "mcp_tools": profile.mcp_tools if profile is not None else request.mcp_tools,
            "sandbox": resolved.sandbox,
            "approval": resolved.approval,
            "allowed_tools": profile.tools if profile is not None else request.allowed_tools,
            "disallowed_tools": (
                profile.disallowed_tools
                if profile is not None
                else request.disallowed_tools
            ),
            "autocompact": resolved.autocompact,
            "effort": resolved.effort,
            "session": request.session.model_copy(
                update={
                    "requested_harness_session_id": resolved_continue_harness_session_id,
                    "continue_fork": resolved_continue_fork,
                }
            ),
            "context_from": resolved_context_from,
            "warning": warning,
            "agent_metadata": agent_metadata,
            "skill_paths": resolve_skill_paths(resolved_skills.loaded_skills),
        }
    )
    return resolved_request, harness, seed_harness_session_id, composition_warnings


def build_launch_context(
    *,
    spawn_id: str,
    request: SpawnRequest,
    runtime: LaunchRuntime,
    harness_registry: HarnessRegistry,
    dry_run: bool = False,
    plan_overrides: Mapping[str, str] | None = None,
    runtime_work_id: str | None = None,
) -> LaunchContext:
    """Build deterministic launch context from raw request/runtime inputs."""

    project_paths = ProjectPaths(
        repo_root=Path(runtime.project_paths_repo_root).expanduser().resolve(),
        execution_cwd=Path(runtime.project_paths_execution_cwd).expanduser().resolve(),
    )
    workspace_snapshot = resolve_workspace_snapshot_for_launch(project_paths.repo_root)
    workspace_roots = get_projectable_roots(workspace_snapshot)
    state_root = Path(runtime.state_root).expanduser().resolve()
    resolved_request = request
    composition_warnings: tuple[CompositionWarning, ...] = ()
    seed_harness_session_id = (
        (request.session.requested_harness_session_id or "").strip() or None
    )
    if runtime.composition_surface != LaunchCompositionSurface.DIRECT:
        (
            resolved_request,
            harness,
            seed_harness_session_id,
            composition_warnings,
        ) = _resolve_surface_request(
            request=request,
            runtime=runtime,
            project_paths=project_paths,
            harness_registry=harness_registry,
            dry_run=dry_run,
        )
    else:
        harness_id = _resolve_harness_id(request=request, runtime=runtime)
        harness = harness_registry.get_subprocess_harness(harness_id)
        composition_warnings = _build_composition_warnings(
            request_warning=resolved_request.warning,
            policy_warning=None,
            route_warning=None,
            missing_skills_warning=None,
            continuation_warning=None,
        )

    report_output_path = _resolve_report_output_path(
        runtime=runtime,
        project_paths=project_paths,
        spawn_id=spawn_id,
    )
    execution_cwd = project_paths.execution_cwd
    child_cwd = resolve_child_execution_cwd(
        repo_root=execution_cwd,
        spawn_id=spawn_id,
        harness_id=harness.id.value,
    )
    # Preview/dry-run callers need composed data without filesystem side-effects.
    if child_cwd != execution_cwd and not dry_run:
        child_cwd.mkdir(parents=True, exist_ok=True)

    try:
        preflight = harness.preflight(
            execution_cwd=execution_cwd,
            child_cwd=child_cwd,
            passthrough_args=tuple(resolved_request.extra_args),
        )
    except AttributeError:
        preflight = PreflightResult.build(
            expanded_passthrough_args=tuple(resolved_request.extra_args)
        )

    workspace_projection = project_workspace_roots(
        harness_id=harness.id,
        roots=workspace_roots,
        parent_opencode_config_content=os.getenv(OPENCODE_CONFIG_CONTENT_ENV),
    )
    projected_extra_args = (
        *preflight.expanded_passthrough_args,
        *workspace_projection.args,
    )
    if workspace_projection.diagnostics:
        composition_warnings = (
            *composition_warnings,
            *(
                CompositionWarning(code=diag.code, message=diag.message)
                for diag in workspace_projection.diagnostics
            ),
        )
        resolved_request = resolved_request.model_copy(
            update={"warning": summarize_composition_warnings(composition_warnings)}
        )

    resolved_agent_metadata = resolved_request.agent_metadata
    model = (resolved_request.model or "").strip()
    requested_harness_session_id = (
        (resolved_request.session.requested_harness_session_id or "").strip() or None
    )
    appended_system_prompt = (
        (resolved_agent_metadata.get("appended_system_prompt") or "").strip() or None
    )
    is_primary_launch = runtime.composition_surface == LaunchCompositionSurface.PRIMARY
    run_params = ResolvedRunInputs(
        prompt=resolved_request.prompt,
        model=ModelId(model) if model else None,
        effort=resolved_request.effort,
        skills=resolved_request.skills,
        agent=resolved_request.agent,
        adhoc_agent_payload=(resolved_agent_metadata.get("adhoc_agent_payload") or "").strip(),
        extra_args=projected_extra_args,
        repo_root=child_cwd.as_posix(),
        mcp_tools=resolved_request.mcp_tools,
        interactive=is_primary_launch,
        continue_harness_session_id=requested_harness_session_id,
        continue_fork=resolved_request.session.continue_fork,
        report_output_path=report_output_path.as_posix(),
        appended_system_prompt=appended_system_prompt,
        context_from_payload=resolved_request.context_from,
    )

    permission_config, perms = resolve_permission_pipeline(
        sandbox=resolved_request.sandbox,
        allowed_tools=resolved_request.allowed_tools,
        disallowed_tools=resolved_request.disallowed_tools,
        approval=resolved_request.approval or "default",
        unsafe_no_permissions=runtime.unsafe_no_permissions,
    )
    spec = resolve_launch_spec_stage(adapter=harness, run_inputs=run_params, perms=perms)
    override = (runtime.harness_command_override or "").strip()
    argv: tuple[str, ...] = ()
    if not override:
        try:
            argv = build_launch_argv(
                adapter=harness,
                run_inputs=run_params,
                perms=perms,
                projected_spec=spec,
            )
        except Exception:
            # Streaming/app callers launch from typed specs, not subprocess argv.
            if runtime.argv_intent != LaunchArgvIntent.SPEC_ONLY:
                raise

    runtime_ctx = ChildEnvContext.from_environment(
        project_paths=project_paths,
        state_root=state_root,
    )
    effective_work_id = (runtime_work_id or resolved_request.work_id_hint or "").strip() or None
    merged_overrides = merge_env_overrides(
        plan_overrides=plan_overrides or {},
        runtime_overrides=runtime_ctx.child_context(),
        preflight_overrides=preflight.extra_env,
    )
    merged_overrides.update(workspace_projection.env_overrides)
    is_bypass = bool(override)
    if is_bypass:
        argv, env = _build_bypass_context(
            override=override,
            preflight=preflight,
            env_overrides=merged_overrides,
        )
    else:
        env = build_env_plan(
            base_env=os.environ,
            adapter=harness,
            run_inputs=run_params,
            permission_config=permission_config,
            runtime_env_overrides=merged_overrides,
        )

    return LaunchContext(
        request=request,
        runtime=runtime,
        repo_root=project_paths.repo_root,
        execution_cwd=execution_cwd,
        state_root=state_root,
        work_id=effective_work_id,
        argv=argv,
        run_params=run_params,
        perms=perms,
        spec=spec,
        child_cwd=child_cwd,
        env=MappingProxyType(env),
        env_overrides=MappingProxyType(merged_overrides),
        report_output_path=report_output_path,
        harness=harness,
        resolved_request=resolved_request,
        seed_harness_session_id=seed_harness_session_id,
        is_bypass=is_bypass,
        warnings=composition_warnings,
    )


__all__ = [
    "ChildEnvContext",
    "LaunchContext",
    "build_launch_context",
    "merge_env_overrides",
]
