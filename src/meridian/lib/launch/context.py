"""Shared launch-context assembly used by subprocess and streaming runners."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from meridian.lib.core.types import ModelId
from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness
from meridian.lib.launch.launch_types import (
    PermissionResolver,
    PreflightResult,
    ResolvedLaunchSpec,
)
from meridian.lib.state.paths import resolve_work_scratch_dir

from .cwd import resolve_child_execution_cwd
from .env import build_harness_child_env
from .env import merge_env_overrides as _merge_env_overrides

if TYPE_CHECKING:
    from meridian.lib.ops.spawn.plan import PreparedSpawnPlan

_ALLOWED_MERIDIAN_KEYS: frozenset[str] = frozenset(
    {
        "MERIDIAN_REPO_ROOT",
        "MERIDIAN_STATE_ROOT",
        "MERIDIAN_DEPTH",
        "MERIDIAN_CHAT_ID",
        "MERIDIAN_FS_DIR",
        "MERIDIAN_WORK_ID",
        "MERIDIAN_WORK_DIR",
    }
)


@dataclass(frozen=True)
class RuntimeContext:
    """Sole producer for child `MERIDIAN_*` environment overrides."""

    repo_root: Path
    state_root: Path
    parent_chat_id: str | None
    parent_depth: int
    fs_dir: Path | None
    work_id: str | None
    work_dir: Path | None

    @classmethod
    def from_environment(
        cls,
        *,
        repo_root: Path,
        state_root: Path,
    ) -> RuntimeContext:
        parent_chat_id = os.getenv("MERIDIAN_CHAT_ID", "").strip() or None
        parent_depth_raw = os.getenv("MERIDIAN_DEPTH", "0").strip()
        parent_depth = 0
        try:
            parent_depth = max(0, int(parent_depth_raw))
        except (TypeError, ValueError):
            parent_depth = 0

        fs_dir_raw = os.getenv("MERIDIAN_FS_DIR", "").strip()
        work_id_raw = os.getenv("MERIDIAN_WORK_ID", "").strip()
        work_dir_raw = os.getenv("MERIDIAN_WORK_DIR", "").strip()

        return cls(
            repo_root=repo_root.resolve(),
            state_root=state_root.resolve(),
            parent_chat_id=parent_chat_id,
            parent_depth=parent_depth,
            fs_dir=Path(fs_dir_raw) if fs_dir_raw else None,
            work_id=work_id_raw or None,
            work_dir=Path(work_dir_raw) if work_dir_raw else None,
        )

    def with_work_id(self, work_id: str | None) -> RuntimeContext:
        normalized = (work_id or "").strip()
        if not normalized:
            return self
        return RuntimeContext(
            repo_root=self.repo_root,
            state_root=self.state_root,
            parent_chat_id=self.parent_chat_id,
            parent_depth=self.parent_depth,
            fs_dir=self.fs_dir,
            work_id=normalized,
            work_dir=resolve_work_scratch_dir(self.state_root, normalized),
        )

    def child_context(self) -> dict[str, str]:
        overrides: dict[str, str] = {
            "MERIDIAN_REPO_ROOT": self.repo_root.as_posix(),
            "MERIDIAN_STATE_ROOT": self.state_root.as_posix(),
            "MERIDIAN_DEPTH": str(self.parent_depth + 1),
        }
        if self.parent_chat_id:
            overrides["MERIDIAN_CHAT_ID"] = self.parent_chat_id
        if self.fs_dir is not None:
            overrides["MERIDIAN_FS_DIR"] = self.fs_dir.as_posix()
        if self.work_id:
            overrides["MERIDIAN_WORK_ID"] = self.work_id
        if self.work_dir is not None:
            overrides["MERIDIAN_WORK_DIR"] = self.work_dir.as_posix()
        elif self.work_id:
            overrides["MERIDIAN_WORK_DIR"] = resolve_work_scratch_dir(
                self.state_root,
                self.work_id,
            ).as_posix()

        if not set(overrides).issubset(_ALLOWED_MERIDIAN_KEYS):
            missing = sorted(set(overrides) - _ALLOWED_MERIDIAN_KEYS)
            raise RuntimeError(f"RuntimeContext.child_context drifted keys: {missing}")
        return overrides


@dataclass(frozen=True)
class LaunchContext:
    run_params: SpawnParams
    perms: PermissionResolver
    spec: ResolvedLaunchSpec
    child_cwd: Path
    env: Mapping[str, str]
    env_overrides: Mapping[str, str]
    report_output_path: Path


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


def prepare_launch_context(
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
) -> LaunchContext:
    """Build deterministic launch context for one runner attempt."""

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

    perms = plan.execution.permission_resolver
    spec = harness.resolve_launch_spec(run_params, perms)

    runtime_ctx = RuntimeContext.from_environment(
        repo_root=execution_cwd,
        state_root=state_root,
    ).with_work_id(runtime_work_id)
    merged_overrides = merge_env_overrides(
        plan_overrides=plan_overrides,
        runtime_overrides=runtime_ctx.child_context(),
        preflight_overrides=preflight.extra_env,
    )
    env = build_harness_child_env(
        base_env=os.environ,
        adapter=harness,
        run_params=run_params,
        permission_config=plan.execution.permission_config,
        runtime_env_overrides=merged_overrides,
    )

    return LaunchContext(
        run_params=run_params,
        perms=perms,
        spec=spec,
        child_cwd=child_cwd,
        env=MappingProxyType(env),
        env_overrides=MappingProxyType(merged_overrides),
        report_output_path=report_output_path,
    )


__all__ = [
    "LaunchContext",
    "RuntimeContext",
    "merge_env_overrides",
    "prepare_launch_context",
]
