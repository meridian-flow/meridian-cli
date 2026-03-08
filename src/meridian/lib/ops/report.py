"""Report operations for spawn-scoped report files."""


from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import require_space_id, resolve_runtime_root_and_config
from meridian.lib.ops.spawn.query import resolve_spawn_reference
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir


def _runtime_context(ctx: RuntimeContext | None) -> RuntimeContext:
    if ctx is not None:
        return ctx
    return RuntimeContext.from_environment()


def _resolve_target_spawn_id(
    repo_root: Path,
    spawn_id: str | None,
    space: str,
    *,
    current_spawn_id: str | None = None,
) -> str:
    candidate = (spawn_id or "").strip()
    if candidate:
        return resolve_spawn_reference(repo_root, candidate, space)
    normalized_current_spawn = (current_spawn_id or "").strip()
    if normalized_current_spawn:
        return resolve_spawn_reference(repo_root, normalized_current_spawn, space)
    raise ValueError("Spawn ID is required. Pass --spawn or set MERIDIAN_SPAWN_ID.")


def _resolve_space_and_spawn(
    *,
    repo_root: Path,
    space: str | None,
    spawn_id: str | None,
    ctx: RuntimeContext | None = None,
) -> tuple[str, str]:
    runtime_context = _runtime_context(ctx)
    resolved_space = str(require_space_id(space, space_id=runtime_context.space_id))
    resolved_spawn = _resolve_target_spawn_id(
        repo_root,
        spawn_id,
        resolved_space,
        current_spawn_id=str(runtime_context.spawn_id or ""),
    )
    if spawn_store.get_spawn(resolve_space_dir(repo_root, resolved_space), resolved_spawn) is None:
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


class ReportCreateInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str = ""
    spawn_id: str | None = None
    space: str | None = None
    repo_root: str | None = None


class ReportCreateOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

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


class ReportShowInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str | None = None
    space: str | None = None
    repo_root: str | None = None


class ReportShowOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    report_path: str
    report: str

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return self.report


class ReportSearchInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = ""
    spawn_id: str | None = None
    limit: int = 20
    space: str | None = None
    repo_root: str | None = None


class ReportSearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    report_path: str
    snippet: str


class ReportSearchOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: tuple[ReportSearchResult, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        if not self.results:
            return "(no matching reports)"
        from meridian.cli.format_helpers import tabular

        return tabular([[item.spawn_id, item.report_path, item.snippet] for item in self.results])


def report_create_sync(
    payload: ReportCreateInput,
    ctx: RuntimeContext | None = None,
) -> ReportCreateOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    space_id, spawn_id = _resolve_space_and_spawn(
        repo_root=repo_root,
        space=payload.space,
        spawn_id=payload.spawn_id,
        ctx=ctx,
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


def report_show_sync(
    payload: ReportShowInput,
    ctx: RuntimeContext | None = None,
) -> ReportShowOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    space_id, spawn_id = _resolve_space_and_spawn(
        repo_root=repo_root,
        space=payload.space,
        spawn_id=payload.spawn_id,
        ctx=ctx,
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


def report_search_sync(
    payload: ReportSearchInput,
    ctx: RuntimeContext | None = None,
) -> ReportSearchOutput:
    runtime_context = _runtime_context(ctx)
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = str(require_space_id(payload.space, space_id=runtime_context.space_id))
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


async def report_create(
    payload: ReportCreateInput,
    ctx: RuntimeContext | None = None,
) -> ReportCreateOutput:
    return report_create_sync(payload, ctx=ctx)


async def report_show(
    payload: ReportShowInput,
    ctx: RuntimeContext | None = None,
) -> ReportShowOutput:
    return report_show_sync(payload, ctx=ctx)


async def report_search(
    payload: ReportSearchInput,
    ctx: RuntimeContext | None = None,
) -> ReportSearchOutput:
    return report_search_sync(payload, ctx=ctx)
