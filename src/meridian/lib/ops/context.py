"""Context query operations — runtime context derivation via CLI query."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.config.context_config import ContextConfig
from meridian.lib.config.settings import resolve_project_root
from meridian.lib.context.resolver import resolve_context_paths
from meridian.lib.core.resolved_context import ResolvedContext
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import resolve_runtime_root_for_read
from meridian.lib.state.paths import load_context_config


class ContextInput(BaseModel):
    """Input for context query operation."""

    model_config = ConfigDict(frozen=True)
    verbose: bool = False


class ContextOutput(BaseModel):
    """Output for context query operation."""

    model_config = ConfigDict(frozen=True)

    work_path: str
    work_resolved: str
    work_source: str
    work_archive: str
    work_archive_resolved: str
    kb_path: str
    kb_resolved: str
    kb_source: str
    render_verbose: bool = Field(default=False, exclude=True, repr=False)

    def format_text(self, ctx: FormatContext | None = None) -> str:
        verbose = self.render_verbose
        if ctx is not None and ctx.verbosity > 0:
            verbose = True

        lines: list[str] = []
        if verbose:
            lines.append("work:")
            lines.append(f"  source: {self.work_source}")
            lines.append(f"  path: {self.work_path}")
            lines.append(f"  resolved: {self.work_resolved}")
            lines.append(f"  archive: {self.work_archive}")
            lines.append(f"  archive_resolved: {self.work_archive_resolved}")
            lines.append("kb:")
            lines.append(f"  source: {self.kb_source}")
            lines.append(f"  path: {self.kb_path}")
            lines.append(f"  resolved: {self.kb_resolved}")
            return "\n".join(lines)

        lines.append(f"work: {self.work_path} ({self.work_source})")
        lines.append(f"  archive: {self.work_archive}")
        lines.append(f"kb: {self.kb_path} ({self.kb_source})")
        return "\n".join(lines)

    def resolve_name(self, name: str) -> str:
        """Resolve one context-name query to its absolute path string."""

        normalized = name.strip().lower()
        if normalized == "work":
            return self.work_resolved
        if normalized == "kb":
            return self.kb_resolved
        if normalized in {"work.archive", "archive", "archive.work"}:
            return self.work_archive_resolved
        raise KeyError(
            f"Unknown context '{name}'. Expected one of: work, kb, work.archive."
        )


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


def _resolve_runtime_context(project_root: Path, runtime_root: Path) -> ResolvedContext:
    """Resolve context with explicit roots — no env mutation needed."""

    return ResolvedContext.from_environment(
        explicit_project_root=project_root,
        explicit_runtime_root=runtime_root,
    )


def context_sync(input: ContextInput) -> ContextOutput:
    """Synchronous handler for context query."""

    project_root = resolve_project_root()
    context_config = load_context_config(project_root) or ContextConfig()
    resolved_paths = resolve_context_paths(project_root, context_config)

    return ContextOutput(
        work_path=context_config.work.path,
        work_resolved=resolved_paths.work_root.as_posix(),
        work_source=context_config.work.source.value,
        work_archive=context_config.work.archive,
        work_archive_resolved=resolved_paths.work_archive.as_posix(),
        kb_path=context_config.kb.path,
        kb_resolved=resolved_paths.kb_root.as_posix(),
        kb_source=context_config.kb.source.value,
        render_verbose=input.verbose,
    )


async def context(input: ContextInput) -> ContextOutput:
    """Async handler for context query."""

    return await asyncio.to_thread(context_sync, input)


def work_current_sync(input: WorkCurrentInput) -> WorkCurrentOutput:
    """Synchronous handler for work current query."""

    _ = input
    project_root = resolve_project_root()
    runtime_root = resolve_runtime_root_for_read(project_root)
    resolved = _resolve_runtime_context(project_root, runtime_root)

    return WorkCurrentOutput(
        work_dir=resolved.work_dir.as_posix() if resolved.work_dir is not None else None
    )


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
