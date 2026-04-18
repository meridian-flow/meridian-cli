"""Context query operations — runtime context derivation via CLI query."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.config.settings import resolve_project_root
from meridian.lib.config.workspace import get_projectable_roots, resolve_workspace_snapshot
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import resolve_state_root_for_read
from meridian.lib.state.paths import resolve_fs_dir, resolve_work_scratch_dir
from meridian.lib.state.session_store import get_session_active_work_id


class ContextInput(BaseModel):
    """Input for context query operation."""

    model_config = ConfigDict(frozen=True)


class ContextOutput(BaseModel):
    """Output for context query operation."""

    model_config = ConfigDict(frozen=True)

    work_dir: str | None = None
    fs_dir: str
    repo_root: str
    state_root: str
    depth: int
    context_roots: list[str] = Field(default_factory=list)

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines: list[str] = []
        lines.append(f"work_dir: {self.work_dir or '(none)'}")
        lines.append(f"fs_dir: {self.fs_dir}")
        lines.append(f"repo_root: {self.repo_root}")
        lines.append(f"state_root: {self.state_root}")
        lines.append(f"depth: {self.depth}")
        if self.context_roots:
            lines.append(f"context_roots: {', '.join(self.context_roots)}")
        return "\n".join(lines)


class WorkCurrentInput(BaseModel):
    """Input for work current operation."""

    model_config = ConfigDict(frozen=True)


class WorkCurrentOutput(BaseModel):
    """Output for work current operation."""

    model_config = ConfigDict(frozen=True)

    work_dir: str | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return self.work_dir or ""


def _resolve_work_id_from_chat_id(state_root: Path, chat_id: str) -> str | None:
    """Look up active work_id from MERIDIAN_CHAT_ID in session store."""

    if not chat_id:
        return None
    return get_session_active_work_id(state_root, chat_id)


def context_sync(input: ContextInput) -> ContextOutput:
    """Synchronous handler for context query."""

    _ = input
    repo_root = resolve_project_root()
    state_root = resolve_state_root_for_read(repo_root)
    depth_raw = os.getenv("MERIDIAN_DEPTH", "0").strip()
    chat_id = os.getenv("MERIDIAN_CHAT_ID", "").strip()

    depth = 0
    try:
        depth = max(0, int(depth_raw))
    except (ValueError, TypeError):
        depth = 0

    work_id = _resolve_work_id_from_chat_id(state_root, chat_id)
    work_dir = (
        resolve_work_scratch_dir(state_root, work_id).as_posix() if work_id is not None else None
    )
    workspace_snapshot = resolve_workspace_snapshot(repo_root)
    context_roots = [root.as_posix() for root in get_projectable_roots(workspace_snapshot)]

    return ContextOutput(
        work_dir=work_dir,
        fs_dir=resolve_fs_dir(repo_root).as_posix(),
        repo_root=repo_root.as_posix(),
        state_root=state_root.as_posix(),
        depth=depth,
        context_roots=context_roots,
    )


async def context(input: ContextInput) -> ContextOutput:
    """Async handler for context query."""

    return await asyncio.to_thread(context_sync, input)


def work_current_sync(input: WorkCurrentInput) -> WorkCurrentOutput:
    """Synchronous handler for work current query."""

    _ = input
    repo_root = resolve_project_root()
    state_root = resolve_state_root_for_read(repo_root)
    chat_id = os.getenv("MERIDIAN_CHAT_ID", "").strip()

    work_id = _resolve_work_id_from_chat_id(state_root, chat_id)
    work_dir = (
        resolve_work_scratch_dir(state_root, work_id).as_posix() if work_id is not None else None
    )

    return WorkCurrentOutput(work_dir=work_dir)


async def work_current(input: WorkCurrentInput) -> WorkCurrentOutput:
    """Async handler for work current query."""

    return await asyncio.to_thread(work_current_sync, input)


__all__ = [
    "ContextInput",
    "ContextOutput",
    "WorkCurrentInput",
    "WorkCurrentOutput",
    "context",
    "context_sync",
    "work_current",
    "work_current_sync",
]
