"""Spawn reconciliation: detect orphaned spawns via process liveness."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
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
_HEARTBEAT_WINDOW_SECS = 120
_ACTIVITY_ARTIFACTS: tuple[str, ...] = ("heartbeat", "output.jsonl", "stderr.log", "report.md")


@dataclass(frozen=True)
class ArtifactSnapshot:
    started_epoch: float | None
    last_activity_epoch: float | None
    recent_activity_artifact: str | None
    durable_report_completion: bool
    runner_pid_alive: bool


@dataclass(frozen=True)
class Skip:
    reason: str


@dataclass(frozen=True)
class FinalizeFailed:
    error: str


@dataclass(frozen=True)
class FinalizeSucceededFromReport:
    pass


type ReconciliationDecision = Skip | FinalizeFailed | FinalizeSucceededFromReport


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


def _artifact_mtime_epoch(path: Path) -> float | None:
    try:
        stat_result = path.stat()
    except OSError:
        return None
    return stat_result.st_mtime


def _recent_runner_activity(
    state_root: Path, spawn_id: str, now: float
) -> tuple[float | None, str | None]:
    """Return the freshest activity timestamp and the artifact that proved recency."""
    spawn_dir = state_root / "spawns" / spawn_id
    latest_activity_epoch: float | None = None
    for artifact_name in _ACTIVITY_ARTIFACTS:
        mtime_epoch = _artifact_mtime_epoch(spawn_dir / artifact_name)
        if mtime_epoch is None:
            continue
        if latest_activity_epoch is None or mtime_epoch > latest_activity_epoch:
            latest_activity_epoch = mtime_epoch
        if now - mtime_epoch <= _HEARTBEAT_WINDOW_SECS:
            return mtime_epoch, artifact_name
    return latest_activity_epoch, None


def _collect_artifact_snapshot(
    state_root: Path,
    record: SpawnRecord,
    now: float,
) -> ArtifactSnapshot:
    started_epoch = _started_at_epoch(record.started_at)
    last_activity_epoch, recent_activity_artifact = _recent_runner_activity(
        state_root,
        record.id,
        now,
    )
    report_text = _read_completion_report(state_root, record.id)
    runner_pid_alive = False
    if record.runner_pid is not None and record.runner_pid > 0:
        runner_pid_alive = is_process_alive(
            record.runner_pid,
            created_after_epoch=started_epoch,
        )
    return ArtifactSnapshot(
        started_epoch=started_epoch,
        last_activity_epoch=last_activity_epoch,
        recent_activity_artifact=recent_activity_artifact,
        durable_report_completion=has_durable_report_completion(report_text),
        runner_pid_alive=runner_pid_alive,
    )


def _has_recent_activity(snapshot: ArtifactSnapshot, *, require_heartbeat: bool) -> bool:
    """Return whether activity is recent enough for the caller's liveness context."""
    artifact_name = snapshot.recent_activity_artifact
    if artifact_name is None:
        return False
    if not require_heartbeat:
        return True
    return artifact_name == "heartbeat"


def decide_reconciliation(
    record: SpawnRecord,
    snapshot: ArtifactSnapshot,
    now: float,
) -> ReconciliationDecision:
    runner_pid = record.runner_pid
    if runner_pid is None or runner_pid <= 0:
        if _has_recent_activity(snapshot, require_heartbeat=True):
            return Skip(reason="recent_activity")
        if _in_startup_grace(snapshot.started_epoch, now):
            return Skip(reason="startup_grace")
        if snapshot.durable_report_completion:
            return FinalizeSucceededFromReport()
        return FinalizeFailed(error="missing_worker_pid")

    if snapshot.runner_pid_alive:
        if _has_recent_activity(snapshot, require_heartbeat=False):
            return Skip(reason="recent_activity")
        return Skip(reason="runner_alive")

    if _has_recent_activity(snapshot, require_heartbeat=True):
        return Skip(reason="recent_activity")

    orphan_reason = "orphan_finalization" if record.exited_at is not None else "orphan_run"
    if orphan_reason == "orphan_run" and _in_startup_grace(snapshot.started_epoch, now):
        return Skip(reason="startup_grace")
    if snapshot.durable_report_completion:
        return FinalizeSucceededFromReport()
    return FinalizeFailed(error=orphan_reason)


def _finalize_and_log(
    state_root: Path, record: SpawnRecord, *, status: SpawnStatus, exit_code: int,
    error: str | None, reason: str, snapshot: ArtifactSnapshot, now: float
) -> SpawnRecord:
    if not finalize_spawn(
        state_root,
        SpawnId(record.id),
        status=status,
        exit_code=exit_code,
        origin="reconciler",
        error=error,
    ):
        return record
    inactivity_secs = (
        max(0.0, now - snapshot.last_activity_epoch)
        if snapshot.last_activity_epoch is not None
        else None
    )
    logger.info(
        "Reconciled active spawn.",
        spawn_id=record.id,
        status=status,
        reason=reason,
        heartbeat_window_secs=_HEARTBEAT_WINDOW_SECS,
        last_activity_epoch=snapshot.last_activity_epoch,
        recent_activity_artifact=snapshot.recent_activity_artifact,
        inactivity_secs=inactivity_secs,
    )
    return record.model_copy(update={"status": status, "exit_code": exit_code, "error": error})


def _finalize_failed(
    state_root: Path, record: SpawnRecord, error: str, snapshot: ArtifactSnapshot, now: float
) -> SpawnRecord:
    return _finalize_and_log(
        state_root,
        record,
        status="failed",
        exit_code=1,
        error=error,
        reason=error,
        snapshot=snapshot,
        now=now,
    )


def _finalize_completed_report(
    state_root: Path, record: SpawnRecord, snapshot: ArtifactSnapshot, now: float
) -> SpawnRecord:
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
        snapshot=snapshot,
        now=now,
    )


def _in_startup_grace(started_epoch: float | None, now: float) -> bool:
    return started_epoch is not None and now - started_epoch < _STARTUP_GRACE_SECS


def reconcile_active_spawn(state_root: Path, record: SpawnRecord) -> SpawnRecord:
    """Reconcile one active spawn. Is the responsible process alive?"""
    if int(os.getenv("MERIDIAN_DEPTH", "0")) > 0:
        return record
    if not is_active_spawn_status(record.status):
        return record

    now = time.time()
    snapshot = _collect_artifact_snapshot(state_root, record, now)
    decision = decide_reconciliation(record, snapshot, now)
    if isinstance(decision, Skip):
        return record
    if isinstance(decision, FinalizeSucceededFromReport):
        return _finalize_completed_report(state_root, record, snapshot, now)
    return _finalize_failed(state_root, record, decision.error, snapshot, now)


def reconcile_spawns(state_root: Path, spawns: list[SpawnRecord]) -> list[SpawnRecord]:
    """Batch reconciliation. Only touches active spawns."""
    return [
        reconcile_active_spawn(state_root, spawn) if is_active_spawn_status(spawn.status) else spawn
        for spawn in spawns
    ]
