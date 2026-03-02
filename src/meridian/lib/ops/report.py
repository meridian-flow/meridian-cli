"""Report operations for spawn-scoped report files."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.ops._runtime import require_space_id, resolve_runtime_root_and_config
from meridian.lib.ops._spawn_query import _read_spawn_row, resolve_spawn_reference
from meridian.lib.ops.registry import OperationSpec, operation
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir

if TYPE_CHECKING:
    from meridian.lib.formatting import FormatContext


def _resolve_target_spawn_id(repo_root: Path, spawn_id: str | None, space: str) -> str:
    candidate = (spawn_id or "").strip()
    if candidate:
        return resolve_spawn_reference(repo_root, candidate, space)
    current_spawn_id = os.getenv("MERIDIAN_SPAWN_ID", "").strip()
    if current_spawn_id:
        return resolve_spawn_reference(repo_root, current_spawn_id, space)
    raise ValueError("Spawn ID is required. Pass --spawn or set MERIDIAN_SPAWN_ID.")


def _resolve_space_and_spawn(
    *,
    repo_root: Path,
    space: str | None,
    spawn_id: str | None,
) -> tuple[str, str]:
    resolved_space = str(require_space_id(space))
    resolved_spawn = _resolve_target_spawn_id(repo_root, spawn_id, resolved_space)
    if _read_spawn_row(repo_root, resolved_spawn, resolved_space) is None:
        raise ValueError(f"Spawn '{resolved_spawn}' not found")
    return resolved_space, resolved_spawn


def _report_path(repo_root: Path, *, space: str, spawn_id: str) -> Path:
    return resolve_space_dir(repo_root, space) / "spawns" / spawn_id / "report.md"


def _report_snippet(text: str, *, query: str) -> str:
    normalized = text.strip()
    if not normalized:
        return ""
    if not query:
        return normalized[:200]
    lower_text = normalized.lower()
    lower_query = query.lower()
    idx = lower_text.find(lower_query)
    if idx < 0:
        return normalized[:200]
    start = max(idx - 80, 0)
    end = min(idx + len(query) + 80, len(normalized))
    return normalized[start:end]


@dataclass(frozen=True, slots=True)
class ReportCreateInput:
    content: str = ""
    spawn_id: str | None = None
    space: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ReportCreateOutput:
    command: str
    status: str
    spawn_id: str
    report_path: str
    bytes_written: int

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return (
            f"{self.command}  {self.status}  spawn={self.spawn_id}  "
            f"path={self.report_path}  bytes={self.bytes_written}"
        )


@dataclass(frozen=True, slots=True)
class ReportShowInput:
    spawn_id: str | None = None
    space: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ReportShowOutput:
    spawn_id: str
    report_path: str
    report: str

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return self.report


@dataclass(frozen=True, slots=True)
class ReportSearchInput:
    query: str = ""
    spawn_id: str | None = None
    limit: int = 20
    space: str | None = None
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ReportSearchResult:
    spawn_id: str
    report_path: str
    snippet: str


@dataclass(frozen=True, slots=True)
class ReportSearchOutput:
    results: tuple[ReportSearchResult, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        if not self.results:
            return "(no matching reports)"
        from meridian.cli.format_helpers import tabular

        return tabular([[item.spawn_id, item.report_path, item.snippet] for item in self.results])


def report_create_sync(payload: ReportCreateInput) -> ReportCreateOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    space_id, spawn_id = _resolve_space_and_spawn(
        repo_root=repo_root,
        space=payload.space,
        spawn_id=payload.spawn_id,
    )
    content = payload.content.strip()
    if not content:
        raise ValueError("Report content must not be empty.")
    report_path = _report_path(repo_root, space=space_id, spawn_id=spawn_id)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    text = f"{content}\n"
    report_path.write_text(text, encoding="utf-8")
    return ReportCreateOutput(
        command="report.create",
        status="succeeded",
        spawn_id=spawn_id,
        report_path=report_path.as_posix(),
        bytes_written=len(text.encode("utf-8")),
    )


def report_show_sync(payload: ReportShowInput) -> ReportShowOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    space_id, spawn_id = _resolve_space_and_spawn(
        repo_root=repo_root,
        space=payload.space,
        spawn_id=payload.spawn_id,
    )
    report_path = _report_path(repo_root, space=space_id, spawn_id=spawn_id)
    if not report_path.is_file():
        raise ValueError(f"Report for spawn '{spawn_id}' not found")
    report = report_path.read_text(encoding="utf-8", errors="ignore").strip()
    return ReportShowOutput(
        spawn_id=spawn_id,
        report_path=report_path.as_posix(),
        report=report,
    )


def report_search_sync(payload: ReportSearchInput) -> ReportSearchOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = str(require_space_id(payload.space))
    limit = payload.limit if payload.limit > 0 else 20
    query = payload.query.strip()

    if payload.spawn_id is not None and payload.spawn_id.strip():
        spawn_ids = (
            resolve_spawn_reference(repo_root, payload.spawn_id.strip(), resolved_space),
        )
    else:
        space_dir = resolve_space_dir(repo_root, resolved_space)
        spawn_ids = tuple(row.id for row in reversed(spawn_store.list_spawns(space_dir)))

    matches: list[ReportSearchResult] = []
    for spawn_id in spawn_ids:
        report_path = _report_path(repo_root, space=resolved_space, spawn_id=spawn_id)
        if not report_path.is_file():
            continue
        report = report_path.read_text(encoding="utf-8", errors="ignore")
        if query and query.lower() not in report.lower():
            continue
        matches.append(
            ReportSearchResult(
                spawn_id=spawn_id,
                report_path=report_path.as_posix(),
                snippet=_report_snippet(report, query=query),
            )
        )
        if len(matches) >= limit:
            break

    return ReportSearchOutput(results=tuple(matches))


async def report_create(payload: ReportCreateInput) -> ReportCreateOutput:
    return report_create_sync(payload)


async def report_show(payload: ReportShowInput) -> ReportShowOutput:
    return report_show_sync(payload)


async def report_search(payload: ReportSearchInput) -> ReportSearchOutput:
    return report_search_sync(payload)


operation(
    OperationSpec[ReportCreateInput, ReportCreateOutput](
        name="report.create",
        handler=report_create,
        sync_handler=report_create_sync,
        input_type=ReportCreateInput,
        output_type=ReportCreateOutput,
        cli_group="report",
        cli_name="create",
        mcp_name="report_create",
        description="Create or overwrite a spawn report.",
    )
)

operation(
    OperationSpec[ReportShowInput, ReportShowOutput](
        name="report.show",
        handler=report_show,
        sync_handler=report_show_sync,
        input_type=ReportShowInput,
        output_type=ReportShowOutput,
        cli_group="report",
        cli_name="show",
        mcp_name="report_show",
        description="Show one spawn report.",
    )
)

operation(
    OperationSpec[ReportSearchInput, ReportSearchOutput](
        name="report.search",
        handler=report_search,
        sync_handler=report_search_sync,
        input_type=ReportSearchInput,
        output_type=ReportSearchOutput,
        cli_group="report",
        cli_name="search",
        mcp_name="report_search",
        description="Search spawn reports by keyword.",
    )
)
