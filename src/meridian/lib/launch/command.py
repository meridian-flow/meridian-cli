"""Command assembly and launch-env helpers for primary launches."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.types import ModelId
from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness
from meridian.lib.launch.launch_types import PermissionResolver, ResolvedLaunchSpec
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.state.paths import resolve_state_paths

from .env import build_env_plan, inherit_child_env
from .run_inputs import (
    ResolvedRunInputs,
    coerce_resolved_run_inputs,
    to_spawn_params,
)

if TYPE_CHECKING:
    from .types import LaunchRequest


def normalize_system_prompt_passthrough_args(
    passthrough_args: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Extract system-prompt passthroughs and return args without prompt duplicates."""

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


def resolve_launch_spec_stage(
    *,
    adapter: SubprocessHarness,
    run_inputs: ResolvedRunInputs | SpawnParams,
    perms: PermissionResolver,
) -> ResolvedLaunchSpec:
    """Stage-owned adapter callsite for `resolve_launch_spec`."""

    return adapter.resolve_launch_spec(to_spawn_params(run_inputs), perms)


def apply_workspace_projection(
    *,
    adapter: SubprocessHarness,
    spec: ResolvedLaunchSpec,
) -> ResolvedLaunchSpec:
    """Workspace projection seam between spec resolution and argv projection."""

    project_workspace = getattr(adapter, "project_workspace", None)
    if not callable(project_workspace):
        return spec

    try:
        projected = project_workspace(spec=spec)
    except TypeError:
        projected = project_workspace(spec)

    if projected is None:
        return spec
    if isinstance(projected, ResolvedLaunchSpec):
        return projected
    raise TypeError(
        "adapter.project_workspace() must return ResolvedLaunchSpec | None; "
        f"got {type(projected).__name__}"
    )


def _projected_spec_to_run_inputs(
    *,
    run_inputs: ResolvedRunInputs,
    projected_spec: ResolvedLaunchSpec,
) -> ResolvedRunInputs:
    projected_model = projected_spec.model.strip() if projected_spec.model else ""
    return run_inputs.model_copy(
        update={
            "prompt": projected_spec.prompt,
            "model": ModelId(projected_model) if projected_model else None,
            "effort": projected_spec.effort,
            "extra_args": projected_spec.extra_args,
            "continue_harness_session_id": projected_spec.continue_session_id,
            "continue_fork": projected_spec.continue_fork,
            "interactive": projected_spec.interactive,
            "mcp_tools": projected_spec.mcp_tools,
        }
    )


def build_launch_argv(
    *,
    adapter: SubprocessHarness,
    run_inputs: ResolvedRunInputs | SpawnParams,
    perms: PermissionResolver,
    projected_spec: ResolvedLaunchSpec | None = None,
) -> tuple[str, ...]:
    """Stage-owned adapter callsite for `build_command`."""

    normalized_inputs = coerce_resolved_run_inputs(run_inputs)
    effective_spec = projected_spec
    if effective_spec is None:
        resolved_spec = resolve_launch_spec_stage(
            adapter=adapter,
            run_inputs=normalized_inputs,
            perms=perms,
        )
        effective_spec = apply_workspace_projection(
            adapter=adapter,
            spec=resolved_spec,
        )
    argv_inputs = _projected_spec_to_run_inputs(
        run_inputs=normalized_inputs,
        projected_spec=effective_spec,
    )
    return tuple(adapter.build_command(to_spawn_params(argv_inputs), perms))


def build_launch_env(
    repo_root: Path,
    request: LaunchRequest,
    *,
    chat_id: str | None = None,
    work_id: str | None = None,
    default_autocompact_pct: int | None = None,
    spawn_id: str | None = None,
    adapter: SubprocessHarness | None = None,
    run_params: ResolvedRunInputs | SpawnParams | None = None,
    permission_config: PermissionConfig | None = None,
) -> dict[str, str]:
    current_context = RuntimeContext.from_environment()
    resolved_chat_id = (
        chat_id.strip() if chat_id is not None and chat_id.strip() else current_context.chat_id
    )
    resolved_work_id = (
        work_id.strip() if work_id is not None and work_id.strip() else current_context.work_id
    )
    runtime_context = RuntimeContext(
        depth=current_context.depth,
        repo_root=repo_root.resolve(),
        state_root=resolve_state_paths(repo_root).root_dir.resolve(),
        chat_id=resolved_chat_id,
        work_id=resolved_work_id,
    )
    env_overrides = runtime_context.to_env_overrides()
    if spawn_id is not None and spawn_id.strip():
        env_overrides["MERIDIAN_SPAWN_ID"] = spawn_id.strip()
    autocompact_pct = (
        request.autocompact if request.autocompact is not None else default_autocompact_pct
    )
    if autocompact_pct is not None:
        env_overrides["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(autocompact_pct)

    # Preserve command override behavior: explicit command launch bypasses harness-specific
    # permission env shaping and inherits the base environment only.
    if os.getenv("MERIDIAN_HARNESS_COMMAND", "").strip():
        return inherit_child_env(
            base_env=os.environ,
            env_overrides=env_overrides,
        )

    if adapter is not None and run_params is not None and permission_config is not None:
        return build_env_plan(
            base_env=os.environ,
            adapter=adapter,
            run_inputs=run_params,
            permission_config=permission_config,
            runtime_env_overrides=env_overrides,
        )

    return inherit_child_env(
        base_env=os.environ,
        env_overrides=env_overrides,
    )


__all__ = [
    "apply_workspace_projection",
    "build_launch_argv",
    "build_launch_env",
    "normalize_system_prompt_passthrough_args",
    "resolve_launch_spec_stage",
]
