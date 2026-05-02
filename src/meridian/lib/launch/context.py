"""Shared launch-context assembly used by subprocess and streaming runners."""

from __future__ import annotations

import os
import shlex
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

from meridian.lib.config.context_config import (
    ArbitraryContextConfig,
    ContextConfig,
    ContextSourceType,
)
from meridian.lib.config.project_paths import ProjectConfigPaths
from meridian.lib.config.settings import MeridianConfig, load_config
from meridian.lib.config.workspace import get_projectable_roots
from meridian.lib.context.resolver import resolve_context_paths
from meridian.lib.core.child_env import build_child_env_overrides, validate_child_env_keys
from meridian.lib.core.overrides import RuntimeOverrides
from meridian.lib.core.resolved_context import ResolvedContext
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
    load_context_config,
    resolve_project_paths,
    resolve_spawn_log_dir,
    resolve_work_scratch_dir,
)
from meridian.lib.state.session_store import get_session_active_work_id
from meridian.plugin_api.git import resolve_clone_path

from .command import (
    build_launch_argv,
    normalize_system_prompt_passthrough_args,
    resolve_launch_spec_stage,
)
from .composition import ComposedLaunchContent, ProjectedContent
from .cwd import resolve_child_execution_cwd
from .env import build_env_plan, inherit_child_env
from .env import merge_env_overrides as _merge_env_overrides
from .permissions import (
    CLAUDE_NATIVE_DELEGATION_TOOLS,
    resolve_nested_claude_permission_request,
    resolve_permission_pipeline,
)
from .policies import ModelSelectionContext, resolve_policies
from .prompt import (
    build_agent_inventory_prompt,
    build_context_prompt,
    build_report_instruction,
    compose_skill_injections,
    dedupe_skill_names,
    sanitize_prior_output,
    strip_stale_report_paths,
)
from .reference import (
    ReferenceItem,
    load_reference_items,
    resolve_template_variables,
    substitute_template_variables,
)
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


@dataclass(frozen=True)
class ChildEnvContext:
    """Sole producer for child `MERIDIAN_*` environment overrides."""

    parent_spawn_id: str | None
    project_root: Path
    runtime_root: Path
    parent_chat_id: str | None
    parent_depth: int
    work_id: str | None = None
    work_dir: Path | None = None
    context_dirs: tuple[tuple[str, Path], ...] = ()

    @classmethod
    def from_environment(
        cls,
        *,
        project_paths: ProjectConfigPaths,
        runtime_root: Path,
    ) -> ChildEnvContext:
        resolved_project_root = project_paths.project_root.resolve()
        resolved_runtime_root = runtime_root.resolve()
        context_config = load_context_config(resolved_project_root) or ContextConfig()
        parent_ctx = ResolvedContext.from_environment(
            explicit_project_root=resolved_project_root,
            explicit_runtime_root=resolved_runtime_root,
            context_config=context_config,
        )
        parent_spawn_id = str(parent_ctx.spawn_id) if parent_ctx.spawn_id else None
        parent_chat_id = parent_ctx.chat_id.strip() or None
        parent_depth = parent_ctx.depth

        work_id = parent_ctx.work_id or os.getenv("MERIDIAN_WORK_ID", "").strip() or None
        if work_id is None and parent_chat_id:
            # Keep launch semantics: runtime_root decides active work lookup.
            try:
                work_id = get_session_active_work_id(resolved_runtime_root, parent_chat_id)
            except Exception:
                work_id = None

        repo_paths = resolve_project_paths(resolved_project_root)
        work_dir = (
            parent_ctx.work_dir
            if parent_ctx.work_dir is not None and parent_ctx.work_id == work_id
            else resolve_work_scratch_dir(repo_paths.root_dir, work_id)
            if work_id is not None
            else None
        )

        resolved_context_paths = resolve_context_paths(
            resolved_project_root,
            context_config,
        )
        context_dirs = (
            ("work", resolved_context_paths.work_root),
            ("work_archive", resolved_context_paths.work_archive),
            ("kb", resolved_context_paths.kb_root),
            *tuple(
                sorted(
                    (name, path)
                    for name, (path, _) in resolved_context_paths.extra.items()
                )
            ),
        )

        return cls(
            # Keep MERIDIAN_PROJECT_DIR anchored to the project/config root so
            # nested meridian commands resolve repo-local profiles, skills,
            # and config from the same place as the parent launch.
            parent_spawn_id=parent_spawn_id,
            project_root=resolved_project_root,
            runtime_root=resolved_runtime_root,
            parent_chat_id=parent_chat_id,
            parent_depth=parent_depth,
            work_id=work_id,
            work_dir=work_dir,
            context_dirs=context_dirs,
        )

    def child_context(
        self,
        *,
        child_spawn_id: str | None = None,
        increment_depth: bool = True,
    ) -> dict[str, str]:
        overrides = build_child_env_overrides(
            parent_spawn_id=self.parent_spawn_id,
            child_spawn_id=child_spawn_id,
            project_root=self.project_root,
            runtime_root=self.runtime_root,
            parent_chat_id=self.parent_chat_id,
            parent_depth=self.parent_depth,
            work_id=self.work_id,
            work_dir=self.work_dir,
            context_dirs=self.context_dirs,
            increment_depth=increment_depth,
        )
        validate_child_env_keys(overrides)
        return overrides


@dataclass(frozen=True)
class LaunchContext:
    request: SpawnRequest
    runtime: LaunchRuntime
    project_root: Path
    execution_cwd: Path
    runtime_root: Path
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
    projected_content: ProjectedContent | None = None
    seed_harness_session_id: str | None = None
    seed_harness_session_args: tuple[str, ...] = ()
    is_bypass: bool = False
    # I-13: adapter input transformations surface here instead of silently mutating.
    warnings: tuple[CompositionWarning, ...] = ()
    model_selection: ModelSelectionContext | None = None


@dataclass(frozen=True)
class _SurfaceResolution:
    request: SpawnRequest
    harness: SubprocessHarness
    seed_harness_session_id: str | None
    composition_warnings: tuple[CompositionWarning, ...]
    loaded_references: tuple[ReferenceItem, ...]
    profile_tools_for_deny_optout: tuple[str, ...]
    has_profile_for_deny_optout: bool
    projected_content: ProjectedContent | None
    model_selection: ModelSelectionContext | None
    seed_session_args: tuple[str, ...] = ()


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
            return f"Spawn '{normalized_source}' has no recorded session - cannot continue/fork."
        return (
            f"Session '{normalized_source}' has no recorded harness session - cannot continue/fork."
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


def _collect_git_context_clone_roots(config: ContextConfig | None) -> tuple[Path, ...]:
    """Return configured clone roots for git-backed context entries."""

    if config is None:
        return ()

    roots: list[Path] = []

    def add_root(*, source: ContextSourceType, remote: str | None) -> None:
        if source != ContextSourceType.GIT:
            return
        normalized_remote = (remote or "").strip()
        if not normalized_remote:
            return
        roots.append(resolve_clone_path(normalized_remote))

    add_root(source=config.work.source, remote=config.work.remote)
    add_root(source=config.kb.source, remote=config.kb.remote)

    extras_raw = getattr(config, "__pydantic_extra__", None)
    extras = cast("dict[str, object]", extras_raw) if isinstance(extras_raw, dict) else {}
    for value in extras.values():
        try:
            parsed = (
                value
                if isinstance(value, ArbitraryContextConfig)
                else ArbitraryContextConfig.model_validate(value)
            )
        except ValidationError:
            continue
        add_root(source=parsed.source, remote=parsed.remote)

    return tuple(roots)


def _collect_context_projection_roots(
    project_root: Path, config: ContextConfig | None
) -> tuple[Path, ...]:
    """Return all meridian context paths for workspace projection.

    Includes work_root, work_archive, kb_root, and any extra context dirs.
    These are the paths that meridian exports as MERIDIAN_CONTEXT_*_DIR env vars.
    """
    if config is None:
        return ()

    resolved = resolve_context_paths(project_root, config)
    roots: list[Path] = [
        resolved.work_root,
        resolved.work_archive,
        resolved.kb_root,
    ]
    for path, _source in resolved.extra.values():
        roots.append(path)

    return tuple(roots)


def _dedupe_roots_in_order(roots: tuple[Path, ...]) -> tuple[Path, ...]:
    """Deduplicate root paths while preserving the first-seen order."""

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = root.as_posix()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(root)
    return tuple(deduped)


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
    project_paths: ProjectConfigPaths,
    spawn_id: str,
) -> Path:
    report_path_raw = (runtime.report_output_path or "").strip()
    if report_path_raw:
        return Path(report_path_raw).expanduser()
    return resolve_spawn_log_dir(project_paths.project_root, spawn_id) / "report.md"


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
    project_paths: ProjectConfigPaths,
    harness_registry: HarnessRegistry,
    dry_run: bool,
) -> _SurfaceResolution:
    config = (
        MeridianConfig.model_validate(runtime.config_snapshot)
        if runtime.config_snapshot
        else load_config(project_paths.project_root)
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
        project_root=project_paths.project_root,
        layers=(cli_overrides, env_overrides),
        config_overrides=config_overrides,
        config=config,
        harness_registry=harness_registry,
        configured_default_harness=configured_default_harness,
        skills_readonly=dry_run,
    )
    profile = policies.profile
    has_profile = profile is not None
    resolved = policies.resolved_overrides
    model_selection = policies.model_selection
    harness = policies.adapter
    resolved_skills = policies.resolved_skills
    if request.skills:
        merged_skill_names = dedupe_skill_names((*resolved_skills.skill_names, *request.skills))
        resolved_skills = resolve_skills_from_profile(
            profile_skills=merged_skill_names,
            project_root=project_paths.project_root,
            readonly=dry_run,
        )

    route_warning = None
    prompt_policy = harness.run_prompt_policy()
    resolved_context_from = request.context_from
    prompt = request.prompt
    loaded_references: tuple[ReferenceItem, ...] = ()
    spawn_composed_content: ComposedLaunchContent | None = None
    if (
        runtime.composition_surface == LaunchCompositionSurface.SPAWN_PREPARE
        and not request.prompt_is_composed
    ):
        loaded_references = load_reference_items(
            request.reference_files,
            base_dir=project_paths.project_root,
        )
        prior_output: str | None = None
        if request.context_from:
            from meridian.lib.ops.spawn.context_ref import (
                render_context_refs,
                resolve_context_ref,
                resolved_context_ref_value,
            )

            resolved_context_refs = tuple(
                resolve_context_ref(project_paths.project_root, ref) for ref in request.context_from
            )
            resolved_context_from = tuple(
                resolved_context_ref_value(ref) for ref in resolved_context_refs
            )
            prior_output = render_context_refs(resolved_context_refs)

        resolved_template_variables = resolve_template_variables(request.template_vars)
        cleaned_user_prompt = substitute_template_variables(
            strip_stale_report_paths(request.prompt),
            resolved_template_variables,
        )
        prompt = cleaned_user_prompt

        skill_injection = compose_skill_injections(resolved_skills.loaded_skills) or ""

        agent_profile_body = ""
        # When harness supports native agents, agent body is delivered separately
        # (e.g. Claude's adhoc_agent_payload). Otherwise include it in composition.
        if (
            profile is not None
            and profile.body.strip()
            and not harness.capabilities.supports_native_agents
        ):
            rendered_agent_body = substitute_template_variables(
                profile.body.strip(),
                resolved_template_variables,
            )
            agent_profile_body = f"# Agent Profile\n\n{rendered_agent_body}"
        inventory_prompt = (
            build_agent_inventory_prompt(project_root=project_paths.project_root) or ""
        )
        context_prompt = build_context_prompt(project_root=project_paths.project_root) or ""

        spawn_composed_content = ComposedLaunchContent(
            skill_injection=skill_injection,
            agent_profile_body=agent_profile_body,
            report_instruction=build_report_instruction(),
            inventory_prompt=inventory_prompt,
            context_prompt=context_prompt,
            passthrough_system_fragments=(),
            user_task_prompt=cleaned_user_prompt,
            reference_items=loaded_references,
            prior_output=(
                sanitize_prior_output(prior_output)
                if prior_output is not None and prior_output.strip()
                else ""
            ),
        )

    requested_harness_session_id = (
        request.session.requested_harness_session_id or ""
    ).strip() or None
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
                        f"Harness '{harness.id}' does not support session fork; resuming in-place."
                    )

    final_prompt = prompt
    final_passthrough_args = request.extra_args
    appended_system_prompt: str | None = None
    user_turn_content: str | None = None
    projected_content: ProjectedContent | None = None
    seed_harness_session_id = resolved_continue_harness_session_id
    seed_session_args: tuple[str, ...] = ()
    if runtime.composition_surface == LaunchCompositionSurface.PRIMARY:
        session_mode = (
            (request.session.primary_session_mode or "fresh").strip().lower()
        ) or "fresh"
        inventory_prompt: str | None = None
        context_prompt_primary: str | None = None
        if session_mode != "resume":
            inventory_prompt = build_agent_inventory_prompt(
                project_root=project_paths.project_root
            )
            context_prompt_primary = build_context_prompt(
                project_root=project_paths.project_root
            )

        seed = harness.seed_session(
            is_resume=session_mode == "resume",
            harness_session_id=resolved_continue_harness_session_id or "",
            passthrough_args=request.extra_args,
        )
        seed_harness_session_id = seed.session_id
        seed_session_args = seed.session_args
        seeded_passthrough_args = (*request.extra_args, *seed.session_args)
        override = (runtime.harness_command_override or "").strip()
        if override and resolved_continue_fork:
            raise ValueError(
                "Cannot use --fork with MERIDIAN_HARNESS_COMMAND override. "
                "Fork requires native harness adapter support."
            )

        final_passthrough_args = seeded_passthrough_args
        user_turn_content: str | None = None
        if not override:
            passthrough_args, passthrough_prompt_fragments = (
                normalize_system_prompt_passthrough_args(seeded_passthrough_args)
            )
            final_passthrough_args = passthrough_args
            skill_injection = compose_skill_injections(resolved_skills.loaded_skills) or ""
            agent_profile_body = ""
            # When harness supports native agents, agent body is delivered separately
            # (e.g. Claude's adhoc_agent_payload). Otherwise include it in composition.
            if (
                profile is not None
                and profile.body.strip()
                and not harness.capabilities.supports_native_agents
            ):
                agent_profile_body = profile.body.strip()

            composed = ComposedLaunchContent(
                skill_injection=skill_injection,
                agent_profile_body=agent_profile_body,
                report_instruction="",
                inventory_prompt=inventory_prompt or "",
                context_prompt=context_prompt_primary or "",
                passthrough_system_fragments=tuple(
                    frag.strip() for frag in passthrough_prompt_fragments if frag.strip()
                ),
                user_task_prompt=request.prompt,
                reference_items=(),
                prior_output="",
            )

            projected = harness.project_content(composed)
            projected_content = projected

            # Use projected content for channel-separated prompt state.
            if projected.system_prompt.strip():
                appended_system_prompt = projected.system_prompt
            if projected.user_turn_content.strip():
                user_turn_content = projected.user_turn_content
                final_prompt = projected.user_turn_content
        elif inventory_prompt:
            final_prompt = "\n\n".join((final_prompt, inventory_prompt))
    elif spawn_composed_content is not None:
        projected = harness.project_content(spawn_composed_content)
        projected_content = projected
        if projected.system_prompt.strip():
            appended_system_prompt = projected.system_prompt
        if projected.user_turn_content.strip():
            user_turn_content = projected.user_turn_content
            final_prompt = projected.user_turn_content
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
    model_selection_update: dict[str, str | None] = {
        "model_selection_requested_token": None,
        "model_selection_canonical_id": None,
        "model_selection_harness_provenance": None,
    }
    if model_selection is not None:
        model_selection_update = {
            "model_selection_requested_token": model_selection.requested_token,
            "model_selection_canonical_id": model_selection.canonical_model_id,
            "model_selection_harness_provenance": model_selection.harness_provenance,
        }
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
    if user_turn_content:
        agent_metadata["user_turn_content"] = user_turn_content
    profile_tools_for_deny_optout = profile.tools if profile is not None else ()

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
                profile.disallowed_tools if profile is not None else request.disallowed_tools
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
            **model_selection_update,
        }
    )
    return _SurfaceResolution(
        request=resolved_request,
        harness=harness,
        seed_harness_session_id=seed_harness_session_id,
        composition_warnings=composition_warnings,
        loaded_references=loaded_references,
        profile_tools_for_deny_optout=profile_tools_for_deny_optout,
        has_profile_for_deny_optout=has_profile,
        projected_content=projected_content,
        model_selection=model_selection,
        seed_session_args=seed_session_args,
    )


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

    project_paths = ProjectConfigPaths(
        project_root=Path(runtime.project_paths_project_root).expanduser().resolve(),
        execution_cwd=Path(runtime.project_paths_execution_cwd).expanduser().resolve(),
    )
    workspace_snapshot = resolve_workspace_snapshot_for_launch(project_paths.project_root)
    workspace_roots = get_projectable_roots(workspace_snapshot)
    context_config = load_context_config(project_paths.project_root)
    git_context_roots = _collect_git_context_clone_roots(context_config)
    context_projection_roots = _collect_context_projection_roots(
        project_paths.project_root, context_config
    )
    runtime_root = Path(runtime.runtime_root).expanduser().resolve()
    system_temp_root = Path(tempfile.gettempdir()).resolve()
    resolved_request = request
    composition_warnings: tuple[CompositionWarning, ...] = ()
    profile_tools_for_deny_optout: tuple[str, ...] = ()
    has_profile_for_deny_optout = False
    projected_content: ProjectedContent | None = None
    seed_harness_session_id = (request.session.requested_harness_session_id or "").strip() or None
    seed_harness_session_args: tuple[str, ...] = ()
    model_selection: ModelSelectionContext | None = None
    if runtime.composition_surface != LaunchCompositionSurface.DIRECT:
        surface = _resolve_surface_request(
            request=request,
            runtime=runtime,
            project_paths=project_paths,
            harness_registry=harness_registry,
            dry_run=dry_run,
        )
        resolved_request = surface.request
        harness = surface.harness
        seed_harness_session_id = surface.seed_harness_session_id
        composition_warnings = surface.composition_warnings
        loaded_references = surface.loaded_references
        profile_tools_for_deny_optout = surface.profile_tools_for_deny_optout
        has_profile_for_deny_optout = surface.has_profile_for_deny_optout
        projected_content = surface.projected_content
        seed_harness_session_args = surface.seed_session_args
        model_selection = surface.model_selection
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
        loaded_references = load_reference_items(
            resolved_request.reference_files,
            base_dir=project_paths.project_root,
        )
        profile_tools_for_deny_optout = ()
        has_profile_for_deny_optout = False

    report_output_path = _resolve_report_output_path(
        runtime=runtime,
        project_paths=project_paths,
        spawn_id=spawn_id,
    )
    execution_cwd = project_paths.execution_cwd
    child_cwd = resolve_child_execution_cwd(
        project_root=execution_cwd,
        spawn_id=spawn_id,
        harness_id=harness.id.value,
    )
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
        roots=_dedupe_roots_in_order(
            (
                *workspace_roots,
                *git_context_roots,
                *context_projection_roots,
                runtime_root,
                system_temp_root,
            )
        ),
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
        resolved_request.session.requested_harness_session_id or ""
    ).strip() or None
    if projected_content is not None:
        appended_system_prompt = projected_content.system_prompt.strip() or None
        user_turn_content = projected_content.user_turn_content.strip() or None
    else:
        appended_system_prompt = (
            resolved_agent_metadata.get("appended_system_prompt") or ""
        ).strip() or None
        user_turn_content = (resolved_agent_metadata.get("user_turn_content") or "").strip() or None
    is_primary_launch = runtime.composition_surface == LaunchCompositionSurface.PRIMARY
    run_params = ResolvedRunInputs(
        prompt=resolved_request.prompt,
        model=ModelId(model) if model else None,
        effort=resolved_request.effort,
        skills=resolved_request.skills,
        agent=resolved_request.agent,
        adhoc_agent_payload=(resolved_agent_metadata.get("adhoc_agent_payload") or "").strip(),
        extra_args=projected_extra_args,
        project_root=child_cwd.as_posix(),
        mcp_tools=resolved_request.mcp_tools,
        interactive=is_primary_launch,
        continue_harness_session_id=requested_harness_session_id,
        continue_fork=resolved_request.session.continue_fork,
        report_output_path=report_output_path.as_posix(),
        appended_system_prompt=appended_system_prompt,
        context_from_payload=resolved_request.context_from,
        reference_items=loaded_references,
        user_turn_content=user_turn_content,
    )

    if (
        runtime.composition_surface == LaunchCompositionSurface.SPAWN_PREPARE
        and harness.id == HarnessId.CLAUDE
        and CLAUDE_NATIVE_DELEGATION_TOOLS
    ):
        allowed_tools, disallowed_tools = resolve_nested_claude_permission_request(
            allowed_tools=resolved_request.allowed_tools,
            disallowed_tools=resolved_request.disallowed_tools,
            profile_allowed_tools=profile_tools_for_deny_optout,
            has_profile=has_profile_for_deny_optout,
        )
        if (
            allowed_tools != resolved_request.allowed_tools
            or disallowed_tools != resolved_request.disallowed_tools
        ):
            resolved_request = resolved_request.model_copy(
                update={
                    "allowed_tools": allowed_tools,
                    "disallowed_tools": disallowed_tools,
                }
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
    if not override and runtime.argv_intent != LaunchArgvIntent.SPEC_ONLY:
        argv = build_launch_argv(
            adapter=harness,
            run_inputs=run_params,
            perms=perms,
            projected_spec=spec,
        )

    runtime_ctx = ChildEnvContext.from_environment(
        project_paths=project_paths,
        runtime_root=runtime_root,
    )
    effective_work_id = (runtime_work_id or resolved_request.work_id_hint or "").strip() or None
    increment_depth = runtime.composition_surface != LaunchCompositionSurface.PRIMARY
    runtime_overrides = runtime_ctx.child_context(
        child_spawn_id=spawn_id,
        increment_depth=increment_depth,
    )
    # Informational: tells the child its own harness for yield timing.
    # Not a policy override — from_env() does not read it back.
    runtime_overrides["MERIDIAN_HARNESS"] = harness.id.value
    merged_overrides = merge_env_overrides(
        plan_overrides=plan_overrides or {},
        runtime_overrides=runtime_overrides,
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
        project_root=project_paths.project_root,
        execution_cwd=execution_cwd,
        runtime_root=runtime_root,
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
        projected_content=projected_content,
        seed_harness_session_id=seed_harness_session_id,
        seed_harness_session_args=seed_harness_session_args,
        is_bypass=is_bypass,
        warnings=composition_warnings,
        model_selection=model_selection,
    )


__all__ = [
    "ChildEnvContext",
    "LaunchContext",
    "build_launch_context",
    "merge_env_overrides",
]
