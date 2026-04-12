"""Spawn reconciliation: detect orphaned spawns via process liveness."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path

import structlog

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.core.spawn_lifecycle import (
    has_durable_report_completion,
    is_active_spawn_status,
    resolve_reconciled_terminal_state,
)
from meridian.lib.core.types import SpawnId
from meridian.lib.state.liveness import is_process_alive
from meridian.lib.state.spawn_store import SpawnRecord, finalize_spawn

logger = structlog.get_logger(__name__)

_STARTUP_GRACE_SECS = 15


def _started_at_epoch(started_at: str | None) -> float | None:
    """Parse started_at ISO string to epoch seconds."""
    normalized = (started_at or "").strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _read_completion_report(state_root: Path, spawn_id: str) -> str | None:
    """Read report.md for durable completion check."""
    report_path = state_root / "spawns" / spawn_id / "report.md"
    if not report_path.is_file():
        return None
    try:
        return report_path.read_text(encoding="utf-8", errors="ignore").strip() or None
    except OSError:
        return None


def _finalize_and_log(
    state_root: Path, record: SpawnRecord, *, status: SpawnStatus, exit_code: int,
    error: str | None, reason: str
) -> SpawnRecord:
    if not finalize_spawn(
        state_root, SpawnId(record.id), status=status, exit_code=exit_code, error=error
    ):
        return record
    logger.info("Reconciled active spawn.", spawn_id=record.id, status=status, reason=reason)
    return record.model_copy(update={"status": status, "exit_code": exit_code, "error": error})


def _finalize_failed(state_root: Path, record: SpawnRecord, error: str) -> SpawnRecord:
    return _finalize_and_log(
        state_root, record, status="failed", exit_code=1, error=error, reason=error
    )


def _finalize_completed_report(state_root: Path, record: SpawnRecord) -> SpawnRecord:
    status, exit_code, error = resolve_reconciled_terminal_state(
        durable_report_completion=True,
        fallback_error="harness_completed",
    )
    return _finalize_and_log(
        state_root,
        record,
        status=status,
        exit_code=exit_code,
        error=error,
        reason="report_completed",
    )


def _in_startup_grace(started_epoch: float | None, now: float) -> bool:
    return started_epoch is not None and now - started_epoch < _STARTUP_GRACE_SECS


def reconcile_active_spawn(state_root: Path, record: SpawnRecord) -> SpawnRecord:
    """Reconcile one active spawn. Is the responsible process alive?"""
    if not is_active_spawn_status(record.status):
        return record

    now = time.time()
    started_epoch = _started_at_epoch(record.started_at)
    runner_pid = record.runner_pid
    if runner_pid is None or runner_pid <= 0:
        if _in_startup_grace(started_epoch, now):
            return record
        return _finalize_failed(state_root, record, "missing_worker_pid")

    orphan_reason = "orphan_finalization" if record.exited_at is not None else "orphan_run"
    if is_process_alive(runner_pid, created_after_epoch=started_epoch):
        return record
    if orphan_reason == "orphan_run" and _in_startup_grace(started_epoch, now):
        return record

    report_text = _read_completion_report(state_root, record.id)
    if has_durable_report_completion(report_text):
        return _finalize_completed_report(state_root, record)
    return _finalize_failed(state_root, record, orphan_reason)


def reconcile_spawns(state_root: Path, spawns: list[SpawnRecord]) -> list[SpawnRecord]:
    """Batch reconciliation. Only touches active spawns."""
    return [
        reconcile_active_spawn(state_root, spawn) if is_active_spawn_status(spawn.status) else spawn
        for spawn in spawns
    ]
