"""Run state query and shaping helpers backed by `runs.jsonl`."""

from __future__ import annotations

import os
from pathlib import Path

from meridian.lib.state import run_store
from meridian.lib.state.paths import resolve_space_dir, resolve_state_paths

from ._runtime import SPACE_REQUIRED_ERROR
from ._run_models import RunDetailOutput

_RUN_REFERENCE_STATUS_FILTERS: dict[str, tuple[str, ...] | None] = {
    "@latest": None,
    "@last-failed": ("failed",),
    "@last-completed": ("succeeded",),
}


def _require_space_id() -> str:
    resolved = os.getenv("MERIDIAN_SPACE_ID", "").strip()
    if not resolved:
        raise ValueError(SPACE_REQUIRED_ERROR)
    return resolved


def _space_dir(repo_root: Path) -> Path:
    return resolve_space_dir(repo_root, _require_space_id())


def _select_latest_run_id(
    repo_root: Path,
    *,
    statuses: tuple[str, ...] | None,
) -> str | None:
    runs = run_store.list_runs(_space_dir(repo_root))
    if statuses is not None:
        wanted = set(statuses)
        runs = [item for item in runs if item.status in wanted]
    if not runs:
        return None
    return runs[-1].id


def resolve_run_reference(repo_root: Path, ref: str) -> str:
    normalized = ref.strip()
    if not normalized:
        raise ValueError("run_id is required")
    if not normalized.startswith("@"):
        return normalized

    status_filter = _RUN_REFERENCE_STATUS_FILTERS.get(normalized)
    if normalized not in _RUN_REFERENCE_STATUS_FILTERS:
        supported = ", ".join(sorted(_RUN_REFERENCE_STATUS_FILTERS))
        raise ValueError(f"Unknown run reference '{normalized}'. Supported references: {supported}")

    resolved = _select_latest_run_id(repo_root, statuses=status_filter)
    if resolved is None:
        raise ValueError(f"No runs found for reference '{normalized}'")
    return resolved


def resolve_run_references(repo_root: Path, refs: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(resolve_run_reference(repo_root, ref) for ref in refs))


def _read_run_row(repo_root: Path, run_id: str) -> run_store.RunRecord | None:
    return run_store.get_run(_space_dir(repo_root), run_id)


def _read_report_text(repo_root: Path, run_id: str) -> tuple[str | None, str | None]:
    report_path = _space_dir(repo_root) / "runs" / run_id / "report.md"
    if not report_path.is_file():
        return None, None
    text = report_path.read_text(encoding="utf-8", errors="ignore").strip() or None
    return report_path.as_posix(), text


def _read_files_touched(repo_root: Path, run_id: str) -> tuple[str, ...]:
    from meridian.lib.extract.files_touched import extract_files_touched
    from meridian.lib.state.artifact_store import LocalStore
    from meridian.lib.types import RunId

    artifacts = LocalStore(resolve_state_paths(repo_root).artifacts_dir)
    return extract_files_touched(artifacts, RunId(run_id))


def _detail_from_row(
    *,
    repo_root: Path,
    row: run_store.RunRecord,
    report: bool,
    include_files: bool,
) -> RunDetailOutput:
    report_path, report_text = _read_report_text(repo_root, row.id)
    report_summary = report_text[:500] if report_text else None

    files_touched: tuple[str, ...] | None = None
    if include_files:
        files_touched = _read_files_touched(repo_root, row.id)

    return RunDetailOutput(
        run_id=row.id,
        status=row.status,
        model=row.model or "",
        harness=row.harness or "",
        space_id=_require_space_id(),
        started_at=row.started_at or "",
        finished_at=row.finished_at,
        duration_secs=row.duration_secs,
        exit_code=row.exit_code,
        failure_reason=row.error,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cost_usd=row.total_cost_usd,
        report_path=report_path,
        report_summary=report_summary,
        report=report_text if report else None,
        files_touched=files_touched,
        skills=(),
    )
