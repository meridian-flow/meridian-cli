"""Shared launch-context assembly used by subprocess and streaming runners."""

from __future__ import annotations

import os
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.types import ModelId
from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness
from meridian.lib.launch.launch_types import (
    PermissionResolver,
    PreflightResult,
    ResolvedLaunchSpec,
)

from .cwd import resolve_child_execution_cwd
from .env import build_harness_child_env, inherit_child_env
from .env import merge_env_overrides as _merge_env_overrides
from .fork import materialize_fork

if TYPE_CHECKING:
    from meridian.lib.ops.spawn.plan import PreparedSpawnPlan


@dataclass(frozen=True)
class NormalLaunchContext:
    """Complete resolved launch context for one harness run."""

    run_params: SpawnParams
    perms: PermissionResolver
    spec: ResolvedLaunchSpec
    child_cwd: Path
    env: Mapping[str, str]
    env_overrides: Mapping[str, str]
    report_output_path: Path


@dataclass(frozen=True)
class BypassLaunchContext:
    """Launch context for MERIDIAN_HARNESS_COMMAND bypass."""

    argv: tuple[str, ...]
    env: Mapping[str, str]
    cwd: Path


LaunchContext = NormalLaunchContext | BypassLaunchContext


@dataclass(frozen=True)
class LaunchOutcome:
    """Raw executor output before adapter post-processing."""

    exit_code: int
    child_pid: int | None = None
    captured_stdout: bytes | None = None


@dataclass(frozen=True)
class LaunchResult:
    """Post-processed launch result returned to driving adapters."""

    exit_code: int
    child_pid: int | None = None
    session_id: str | None = None


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


def build_launch_context(
    *,
    spawn_id: str,
    run_prompt: str,
    run_model: str | None,
    plan: PreparedSpawnPlan,
    harness: SubprocessHarness,
    execution_cwd: Path,
    state_root: Path,
    plan_overrides: Mapping[str, str],
    report_output_path: Path,
    runtime_work_id: str | None = None,
    runtime_chat_id: str | None = None,
    runtime_spawn_id: str | None = None,
    harness_command_override: str | None = None,
) -> LaunchContext:
    """Build deterministic launch context for one runner attempt.

    This is the canonical entry point for launch composition.
    All driving adapters must call this factory.
    """

    child_cwd = resolve_child_execution_cwd(
        repo_root=execution_cwd,
        spawn_id=spawn_id,
        harness_id=harness.id.value,
    )
    if child_cwd != execution_cwd:
        child_cwd.mkdir(parents=True, exist_ok=True)

    try:
        preflight = harness.preflight(
            execution_cwd=execution_cwd,
            child_cwd=child_cwd,
            passthrough_args=tuple(plan.passthrough_args),
        )
    except AttributeError:
        preflight = PreflightResult.build(
            expanded_passthrough_args=tuple(plan.passthrough_args)
        )

    parent_runtime_ctx = RuntimeContext.from_environment()
    runtime_ctx = parent_runtime_ctx.model_copy(
        update={
            "repo_root": execution_cwd.resolve(),
            "state_root": state_root.resolve(),
            "chat_id": (
                runtime_chat_id.strip()
                if runtime_chat_id is not None and runtime_chat_id.strip()
                else parent_runtime_ctx.chat_id
            ),
        }
    )
    runtime_ctx = runtime_ctx.with_work_id(runtime_work_id)
    runtime_overrides = runtime_ctx.child_context()
    normalized_runtime_spawn_id = (runtime_spawn_id or "").strip()
    if normalized_runtime_spawn_id:
        runtime_overrides["MERIDIAN_SPAWN_ID"] = normalized_runtime_spawn_id
    merged_overrides = merge_env_overrides(
        plan_overrides=plan_overrides,
        runtime_overrides=runtime_overrides,
        preflight_overrides=preflight.extra_env,
    )

    normalized_override = (
        harness_command_override.strip()
        if harness_command_override is not None
        else os.getenv("MERIDIAN_HARNESS_COMMAND", "").strip()
    )
    if normalized_override:
        if plan.session.continue_fork:
            raise ValueError(
                "Cannot use --fork with MERIDIAN_HARNESS_COMMAND override. "
                "Fork requires native harness adapter support."
            )
        argv = tuple([*shlex.split(normalized_override), *preflight.expanded_passthrough_args])
        if not argv:
            raise ValueError("MERIDIAN_HARNESS_COMMAND resolved to an empty command.")
        env = inherit_child_env(
            base_env=os.environ,
            env_overrides=merged_overrides,
        )
        return BypassLaunchContext(
            argv=argv,
            env=MappingProxyType(env),
            cwd=child_cwd,
        )

    run_params = SpawnParams(
        prompt=run_prompt,
        model=ModelId(run_model) if run_model and run_model.strip() else None,
        effort=plan.effort,
        skills=plan.skills,
        agent=plan.agent_name,
        adhoc_agent_payload=plan.adhoc_agent_payload,
        extra_args=preflight.expanded_passthrough_args,
        repo_root=child_cwd.as_posix(),
        mcp_tools=plan.mcp_tools,
        continue_harness_session_id=plan.session.harness_session_id,
        continue_fork=plan.session.continue_fork,
        report_output_path=report_output_path.as_posix(),
        appended_system_prompt=plan.appended_system_prompt,
    )
    run_params = materialize_fork(
        adapter=harness,
        run_params=run_params,
    )

    perms = plan.execution.permission_resolver
    spec = harness.resolve_launch_spec(run_params, perms)
    env = build_harness_child_env(
        base_env=os.environ,
        adapter=harness,
        run_params=run_params,
        permission_config=plan.execution.permission_config,
        runtime_env_overrides=merged_overrides,
    )

    return NormalLaunchContext(
        run_params=run_params,
        perms=perms,
        spec=spec,
        child_cwd=child_cwd,
        env=MappingProxyType(env),
        env_overrides=MappingProxyType(merged_overrides),
        report_output_path=report_output_path,
    )


__all__ = [
    "BypassLaunchContext",
    "LaunchContext",
    "LaunchOutcome",
    "LaunchResult",
    "NormalLaunchContext",
    "RuntimeContext",
    "build_launch_context",
    "merge_env_overrides",
]
