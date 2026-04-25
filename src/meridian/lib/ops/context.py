"""Context query operations — runtime context derivation via CLI query."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.config.context_config import ArbitraryContextConfig, ContextConfig
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


class ContextEntryOutput(BaseModel):
    """Output for one named context entry."""

    model_config = ConfigDict(frozen=True)

    source: str
    path: str
    resolved: str


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
    extra_contexts: dict[str, ContextEntryOutput] = Field(default_factory=dict)
    render_verbose: bool = Field(default=False, exclude=True, repr=False)

    def _available_names(self) -> tuple[str, ...]:
        return ("work", "kb", "work.archive", *sorted(self.extra_contexts))

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
            for name in sorted(self.extra_contexts):
                entry = self.extra_contexts[name]
                lines.append(f"{name}:")
                lines.append(f"  source: {entry.source}")
                lines.append(f"  path: {entry.path}")
                lines.append(f"  resolved: {entry.resolved}")
            return "\n".join(lines)

        lines.append(f"work: {self.work_resolved} ({self.work_source})")
        lines.append(f"  archive: {self.work_archive_resolved}")
        lines.append(f"kb: {self.kb_resolved} ({self.kb_source})")
        for name in sorted(self.extra_contexts):
            entry = self.extra_contexts[name]
            lines.append(f"{name}: {entry.resolved} ({entry.source})")
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
        if normalized in self.extra_contexts:
            return self.extra_contexts[normalized].resolved
        raise KeyError(
            f"Unknown context '{name}'. Expected one of: "
            f"{', '.join(self._available_names())}."
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


def _extra_context_config(config: ContextConfig) -> dict[str, ArbitraryContextConfig]:
    """Return arbitrary context configs keyed by normalized lookup name."""

    extras_raw = getattr(config, "__pydantic_extra__", None)
    extras = cast("dict[str, object]", extras_raw) if isinstance(extras_raw, dict) else {}
    parsed: dict[str, ArbitraryContextConfig] = {}
    for name, value in extras.items():
        parsed[name.strip().lower()] = (
            value
            if isinstance(value, ArbitraryContextConfig)
            else ArbitraryContextConfig.model_validate(value)
        )
    return parsed


def context_sync(input: ContextInput) -> ContextOutput:
    """Synchronous handler for context query."""

    project_root = resolve_project_root()
    context_config = load_context_config(project_root) or ContextConfig()
    resolved_paths = resolve_context_paths(project_root, context_config)
    extra_config = _extra_context_config(context_config)
    extra_contexts: dict[str, ContextEntryOutput] = {}
    for name, (path, source) in resolved_paths.extra.items():
        normalized = name.strip().lower()
        config_entry = extra_config.get(normalized)
        if config_entry is None:
            continue
        extra_contexts[normalized] = ContextEntryOutput(
            source=source.value,
            path=config_entry.path,
            resolved=path.as_posix(),
        )

    return ContextOutput(
        work_path=context_config.work.path,
        work_resolved=resolved_paths.work_root.as_posix(),
        work_source=context_config.work.source.value,
        work_archive=context_config.work.archive,
        work_archive_resolved=resolved_paths.work_archive.as_posix(),
        kb_path=context_config.kb.path,
        kb_resolved=resolved_paths.kb_root.as_posix(),
        kb_source=context_config.kb.source.value,
        extra_contexts=extra_contexts,
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
    "ContextEntryOutput",
    "ContextInput",
    "ContextOutput",
    "WorkCurrentInput",
    "WorkCurrentOutput",
    "context",
    "context_sync",
    "work_current",
    "work_current_sync",
]
