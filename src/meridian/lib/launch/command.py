"""Command assembly and launch-env helpers for primary launches."""

import os
from pathlib import Path

from meridian.lib.core.context import RuntimeContext
from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.state.paths import resolve_state_paths

from .env import build_harness_child_env, inherit_child_env
from .plan import normalize_system_prompt_passthrough_args
from .types import LaunchRequest


def build_launch_env(
    repo_root: Path,
    request: LaunchRequest,
    *,
    chat_id: str | None = None,
    work_id: str | None = None,
    default_autocompact_pct: int | None = None,
    spawn_id: str | None = None,
    adapter: SubprocessHarness | None = None,
    run_params: SpawnParams | None = None,
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
        return build_harness_child_env(
            base_env=os.environ,
            adapter=adapter,
            run_params=run_params,
            permission_config=permission_config,
            runtime_env_overrides=env_overrides,
        )

    return inherit_child_env(
        base_env=os.environ,
        env_overrides=env_overrides,
    )


__all__ = [
    "build_launch_env",
    "normalize_system_prompt_passthrough_args",
]
