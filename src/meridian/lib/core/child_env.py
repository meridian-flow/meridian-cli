"""Shared child-env contract for spawn and launch boundaries.

This module defines the canonical ``MERIDIAN_*`` key surface that callers may
propagate into child processes.
"""

from collections.abc import Mapping
from pathlib import Path

from meridian.lib.core.types import SpawnId

# Authoritative ``MERIDIAN_*`` key allowlist for child-process propagation.
# Must stay aligned with ResolvedContext.child_env_overrides().
ALLOWED_CHILD_ENV_KEYS: frozenset[str] = frozenset(
    {
        "MERIDIAN_SPAWN_ID",
        "MERIDIAN_REPO_ROOT",
        "MERIDIAN_STATE_ROOT",
        "MERIDIAN_DEPTH",
        "MERIDIAN_CHAT_ID",
        "MERIDIAN_WORK_ID",
        "MERIDIAN_WORK_DIR",
        "MERIDIAN_FS_DIR",
    }
)


def validate_child_env_keys(overrides: Mapping[str, str]) -> None:
    """Raise if overrides contain unexpected MERIDIAN_* keys.

    Unexpected means: starts with ``MERIDIAN_`` but is not in
    :data:`ALLOWED_CHILD_ENV_KEYS`.
    """
    for key in overrides:
        if key.startswith("MERIDIAN_") and key not in ALLOWED_CHILD_ENV_KEYS:
            raise RuntimeError(f"Unexpected MERIDIAN_* key in child env: {key}")


def build_child_env_overrides(
    *,
    parent_spawn_id: str | None,
    repo_root: Path | None,
    state_root: Path | None,
    parent_chat_id: str | None,
    parent_depth: int,
    work_id: str | None = None,
    work_dir: Path | None = None,
    fs_dir: Path | None = None,
    increment_depth: bool = True,
) -> dict[str, str]:
    """Build ``MERIDIAN_*`` child env overrides from resolved context fields.

    Delegates to :meth:`~meridian.lib.core.resolved_context.ResolvedContext.child_env_overrides`
    so that key naming and omission rules are owned by one authoritative seam.

    Parameters
    ----------
    parent_spawn_id:
        Parent spawn ID string, or ``None`` to omit ``MERIDIAN_SPAWN_ID``.
    repo_root:
        Repo root path, or ``None`` to omit ``MERIDIAN_REPO_ROOT``.
    state_root:
        State root path, or ``None`` to omit ``MERIDIAN_STATE_ROOT``.
    parent_chat_id:
        Parent chat ID string, or ``None``/empty to omit ``MERIDIAN_CHAT_ID``.
    parent_depth:
        The *current* process's depth value.  When ``increment_depth=True``
        (the default) the child gets ``parent_depth + 1``; pass
        ``increment_depth=False`` to keep the depth unchanged (needed for
        background workers that run at the same depth as their launcher).
    work_id:
        Work item ID, or ``None`` to omit ``MERIDIAN_WORK_ID``.
    work_dir:
        Pre-computed work scratch directory, or ``None`` to omit
        ``MERIDIAN_WORK_DIR``.
    fs_dir:
        Pre-computed filesystem directory, or ``None`` to omit
        ``MERIDIAN_FS_DIR``.
    increment_depth:
        Whether to increment ``MERIDIAN_DEPTH`` for the child.  Defaults to
        ``True`` for standard child-process launches; use ``False`` for the
        detached background-worker process that inherits the caller's depth.
    """
    from meridian.lib.core.resolved_context import ResolvedContext

    # Route through ResolvedContext so all launch paths share one contract.
    ctx = ResolvedContext(
        spawn_id=SpawnId(parent_spawn_id) if parent_spawn_id else None,
        depth=parent_depth,
        repo_root=repo_root,
        state_root=state_root,
        chat_id=parent_chat_id or "",
        work_id=work_id,
        work_dir=work_dir,
        fs_dir=fs_dir,
    )
    return ctx.child_env_overrides(increment_depth=increment_depth)


__all__ = [
    "ALLOWED_CHILD_ENV_KEYS",
    "build_child_env_overrides",
    "validate_child_env_keys",
]
