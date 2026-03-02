"""Spawn state query and shaping helpers backed by `spawns.jsonl`."""

from __future__ import annotations

import os
from pathlib import Path

from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir, resolve_state_paths

from ._runtime import SPACE_REQUIRED_ERROR
from ._spawn_models import SpawnDetailOutput

_SPAWN_REFERENCE_STATUS_FILTERS: dict[str, tuple[str, ...] | None] = {
    "@latest": None,
    "@last-failed": ("failed",),
    "@last-completed": ("succeeded",),
}


def _resolve_space_id(space: str | None = None) -> str:
    if space is not None:
        resolved = space.strip()
        if resolved:
            return resolved

    resolved = os.getenv("MERIDIAN_SPACE_ID", "").strip()
    if not resolved:
        raise ValueError(SPACE_REQUIRED_ERROR)
    return resolved


def _space_dir(repo_root: Path, space: str | None = None) -> Path:
    return resolve_space_dir(repo_root, _resolve_space_id(space))


def _select_latest_spawn_id(
    repo_root: Path,
    *,
    statuses: tuple[str, ...] | None,
    space: str | None = None,
) -> str | None:
    spawns = spawn_store.list_spawns(_space_dir(repo_root, space))
    if statuses is not None:
        wanted = set(statuses)
        spawns = [item for item in spawns if item.status in wanted]
    if not spawns:
        return None
    return spawns[-1].id


def resolve_spawn_reference(repo_root: Path, ref: str, space: str | None = None) -> str:
    normalized = ref.strip()
    if not normalized:
        raise ValueError("spawn_id is required")
    if not normalized.startswith("@"):
        return normalized

    status_filter = _SPAWN_REFERENCE_STATUS_FILTERS.get(normalized)
    if normalized not in _SPAWN_REFERENCE_STATUS_FILTERS:
        supported = ", ".join(sorted(_SPAWN_REFERENCE_STATUS_FILTERS))
        raise ValueError(f"Unknown spawn reference '{normalized}'. Supported references: {supported}")

    resolved = _select_latest_spawn_id(repo_root, statuses=status_filter, space=space)
    if resolved is None:
        raise ValueError(f"No spawns found for reference '{normalized}'")
    return resolved


def resolve_spawn_references(
    repo_root: Path,
    refs: tuple[str, ...],
    space: str | None = None,
) -> tuple[str, ...]:
    return tuple(dict.fromkeys(resolve_spawn_reference(repo_root, ref, space) for ref in refs))


def _read_spawn_row(
    repo_root: Path,
    spawn_id: str,
    space: str | None = None,
) -> spawn_store.SpawnRecord | None:
    return spawn_store.get_spawn(_space_dir(repo_root, space), spawn_id)


def _read_report_text(
    repo_root: Path,
    spawn_id: str,
    space: str | None = None,
) -> tuple[str | None, str | None]:
    report_path = _space_dir(repo_root, space) / "spawns" / spawn_id / "report.md"
    if not report_path.is_file():
        return None, None
    text = report_path.read_text(encoding="utf-8", errors="ignore").strip() or None
    return report_path.as_posix(), text


def _read_files_touched(
    repo_root: Path,
    spawn_id: str,
    space: str | None = None,
) -> tuple[str, ...]:
    from meridian.lib.extract.files_touched import extract_files_touched
    from meridian.lib.state.artifact_store import LocalStore
    from meridian.lib.types import SpawnId

    artifacts = LocalStore(resolve_state_paths(repo_root).artifacts_dir)
    return extract_files_touched(artifacts, SpawnId(spawn_id))


def _detail_from_row(
    *,
    repo_root: Path,
    row: spawn_store.SpawnRecord,
    report: bool,
    include_files: bool,
    space_id: str | None = None,
) -> SpawnDetailOutput:
    resolved_space_id = _resolve_space_id(space_id)
    report_path, report_text = _read_report_text(repo_root, row.id, resolved_space_id)
    report_summary = report_text[:500] if report_text else None

    files_touched: tuple[str, ...] | None = None
    if include_files:
        files_touched = _read_files_touched(repo_root, row.id, resolved_space_id)

    return SpawnDetailOutput(
        spawn_id=row.id,
        status=row.status,
        model=row.model or "",
        harness=row.harness or "",
        space_id=resolved_space_id,
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
    )
