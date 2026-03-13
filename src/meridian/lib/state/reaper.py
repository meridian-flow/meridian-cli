"""Spawn reconciliation: detect and clean up orphaned/stuck spawns.

This module is the single place where stuck-spawn policy lives. It runs on
every user-facing read path (list, show, wait, dashboard) so that stale or
orphaned spawns are repaired transparently — no separate "gc" command needed.
"""

from __future__ import annotations

import fcntl
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import structlog

from meridian.lib.core.spawn_lifecycle import (
    has_durable_report_completion,
    is_active_spawn_status,
    resolve_reconciled_terminal_state,
)
from meridian.lib.core.domain import SpawnStatus
from meridian.lib.state.spawn_store import (
    BACKGROUND_LAUNCH_MODE,
    FOREGROUND_LAUNCH_MODE,
    LaunchMode,
    SpawnRecord,
    finalize_spawn,
    mark_spawn_running,
)
from meridian.lib.core.types import SpawnId

logger = structlog.get_logger(__name__)

_STALE_THRESHOLD_SECS = 300  # 5 minutes of no output = stale
_STARTUP_GRACE_SECS = 15  # allow launcher/runner a brief window to materialize PID files
# ---------------------------------------------------------------------------
# PID helpers
# ---------------------------------------------------------------------------


def _read_pid_file(spawn_dir: Path, filename: str) -> int | None:
    """Read and parse a .pid file. Return None if missing/invalid."""
    pid_path = spawn_dir / filename
    if not pid_path.is_file():
        return None
    try:
        value = int(pid_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
    return value if value > 0 else None


def _get_boot_time() -> float:
    """Read system boot time from /proc/stat (Linux only)."""
    try:
        with open("/proc/stat", "r") as f:
            for line in f:
                if line.startswith("btime "):
                    return float(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def _pid_is_alive(pid: int, pid_file: Path) -> bool:
    """Check if a PID is alive, with /proc start-time guard for PID reuse."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Exists but we can't signal it

    # Guard against PID reuse on Linux via /proc start time
    try:
        stat_path = Path(f"/proc/{pid}/stat")
        if stat_path.exists():
            # Field 22 (0-indexed: 21) is starttime in clock ticks
            fields = stat_path.read_text().split()
            start_ticks = int(fields[21])
            boot_time = _get_boot_time()
            clock_hz = os.sysconf("SC_CLK_TCK")
            proc_start = boot_time + start_ticks / clock_hz
            pid_file_mtime = pid_file.stat().st_mtime
            # If process started after PID file was written, it's a reused PID
            if proc_start > pid_file_mtime + 2:  # 2s tolerance
                return False
    except (OSError, ValueError, IndexError):
        pass  # Non-Linux or can't check — assume alive

    return True


def _spawn_is_stale(spawn_dir: Path, pid_file: Path) -> bool:
    """Check if a spawn has stopped producing output for >5 minutes."""
    now = time.time()
    # Check output files and heartbeat first
    for name in ("output.jsonl", "stderr.log", "heartbeat"):
        path = spawn_dir / name
        try:
            if now - path.stat().st_mtime < _STALE_THRESHOLD_SECS:
                return False  # Recent activity
        except OSError:
            continue
    # If no output files exist, check pid file age as spawn start proxy
    try:
        if now - pid_file.stat().st_mtime < _STALE_THRESHOLD_SECS:
            return False  # Spawn started recently
    except OSError:
        pass
    return True


def _started_at_epoch(started_at: str | None) -> float | None:
    if started_at is None:
        return None
    normalized = started_at.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _recent_spawn_activity(spawn_dir: Path, *, now: float) -> bool:
    for name in ("output.jsonl", "stderr.log", "report.md", "prompt.md", "params.json", "heartbeat"):
        path = spawn_dir / name
        try:
            if now - path.stat().st_mtime < _STARTUP_GRACE_SECS:
                return True
        except OSError:
            continue
    return False


def _primary_launch_lock_is_held(state_root: Path) -> bool:
    lock_path = state_root / "active-primary.lock"
    if not lock_path.is_file():
        return False
    try:
        with lock_path.open("a+", encoding="utf-8") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        return False
    return False


def _startup_grace_elapsed(record: SpawnRecord, spawn_dir: Path, *, now: float) -> bool:
    if _recent_spawn_activity(spawn_dir, now=now):
        return False

    started_at = _started_at_epoch(record.started_at)
    if started_at is not None:
        return now - started_at >= _STARTUP_GRACE_SECS

    try:
        return now - spawn_dir.stat().st_mtime >= _STARTUP_GRACE_SECS
    except OSError:
        return True


ResolvedLaunchMode = LaunchMode | Literal[""]


def _resolve_launch_mode(record: SpawnRecord, spawn_dir: Path) -> ResolvedLaunchMode:
    explicit = (record.launch_mode or "").strip().lower()
    if explicit == BACKGROUND_LAUNCH_MODE:
        return BACKGROUND_LAUNCH_MODE
    if explicit == FOREGROUND_LAUNCH_MODE:
        return FOREGROUND_LAUNCH_MODE
    if record.wrapper_pid is not None and record.wrapper_pid > 0:
        return BACKGROUND_LAUNCH_MODE
    if record.worker_pid is not None and record.worker_pid > 0:
        return FOREGROUND_LAUNCH_MODE
    if (spawn_dir / "background.pid").is_file():
        return BACKGROUND_LAUNCH_MODE
    if (spawn_dir / "harness.pid").is_file():
        return FOREGROUND_LAUNCH_MODE
    return ""


def _read_completion_report(spawn_dir: Path) -> str | None:
    report_path = spawn_dir / "report.md"
    if not report_path.is_file():
        return None
    try:
        text = report_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    return text.strip() or None


# ---------------------------------------------------------------------------
# Reconciliation — runs on every user-facing read
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _SpawnInspection:
    record: SpawnRecord
    spawn_dir: Path
    launch_mode: ResolvedLaunchMode
    grace_elapsed: bool
    spawn_dir_exists: bool
    wrapper_pid: int | None = None
    wrapper_alive: bool = False
    harness_pid: int | None = None
    harness_alive: bool = False
    report_text: str | None = None
    stale: bool = False


def _inspect_spawn_runtime(state_root: Path, record: SpawnRecord, *, now: float) -> _SpawnInspection:
    spawn_dir = state_root / "spawns" / record.id
    launch_mode = _resolve_launch_mode(record, spawn_dir)
    spawn_dir_exists = spawn_dir.exists()
    grace_elapsed = _startup_grace_elapsed(record, spawn_dir, now=now)

    wrapper_pid: int | None = None
    wrapper_alive = False
    harness_pid: int | None = None
    harness_alive = False
    report_text: str | None = None
    stale = False

    if spawn_dir_exists:
        if launch_mode == BACKGROUND_LAUNCH_MODE:
            wrapper_pid = record.wrapper_pid if record.wrapper_pid and record.wrapper_pid > 0 else None
            if wrapper_pid is None:
                wrapper_pid = _read_pid_file(spawn_dir, "background.pid")
            if wrapper_pid is not None:
                wrapper_alive = _pid_is_alive(wrapper_pid, spawn_dir / "background.pid")

        harness_pid = record.worker_pid if record.worker_pid and record.worker_pid > 0 else None
        if harness_pid is None:
            harness_pid = _read_pid_file(spawn_dir, "harness.pid")
        if harness_pid is not None:
            harness_alive = _pid_is_alive(harness_pid, spawn_dir / "harness.pid")

        report_text = _read_completion_report(spawn_dir)

        pid_anchor_name = (
            "background.pid"
            if launch_mode == BACKGROUND_LAUNCH_MODE and wrapper_pid is not None
            else "harness.pid"
        )
        pid_anchor = spawn_dir / pid_anchor_name
        if pid_anchor.exists() or any((spawn_dir / name).exists() for name in ("output.jsonl", "stderr.log")):
            stale = _spawn_is_stale(spawn_dir, pid_anchor)

    return _SpawnInspection(
        record=record,
        spawn_dir=spawn_dir,
        launch_mode=launch_mode,
        grace_elapsed=grace_elapsed,
        spawn_dir_exists=spawn_dir_exists,
        wrapper_pid=wrapper_pid,
        wrapper_alive=wrapper_alive,
        harness_pid=harness_pid,
        harness_alive=harness_alive,
        report_text=report_text,
        stale=stale,
    )


def _finalize_and_log(
    state_root: Path,
    record: SpawnRecord,
    *,
    status: SpawnStatus,
    exit_code: int,
    error: str | None,
    reason: str,
) -> SpawnRecord:
    """Finalize an active spawn during reconciliation and return the updated record."""
    finalized = finalize_spawn(
        state_root,
        SpawnId(record.id),
        status=status,
        exit_code=exit_code,
        error=error,
    )
    if finalized:
        logger.info(
            "Reconciled active spawn.",
            spawn_id=record.id,
            status=status,
            reason=reason,
        )
        return record.model_copy(update={"status": status, "exit_code": exit_code, "error": error})
    return record


def _finalize_failed(state_root: Path, record: SpawnRecord, error: str) -> SpawnRecord:
    return _finalize_and_log(
        state_root,
        record,
        status="failed",
        exit_code=1,
        error=error,
        reason=error,
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


def _mark_running(
    state_root: Path,
    record: SpawnRecord,
    *,
    launch_mode: LaunchMode,
    wrapper_pid: int | None = None,
    worker_pid: int | None = None,
) -> SpawnRecord:
    if (
        record.status == "running"
        and record.launch_mode == launch_mode
        and record.wrapper_pid == wrapper_pid
        and record.worker_pid == worker_pid
    ):
        return record
    mark_spawn_running(
        state_root,
        SpawnId(record.id),
        launch_mode=launch_mode,
        wrapper_pid=wrapper_pid,
        worker_pid=worker_pid,
    )
    logger.info(
        "Recovered active spawn to running.",
        spawn_id=record.id,
        launch_mode=launch_mode,
        wrapper_pid=wrapper_pid,
        worker_pid=worker_pid,
    )
    return record.model_copy(
        update={
            "status": "running",
            "launch_mode": launch_mode,
            "wrapper_pid": wrapper_pid,
            "worker_pid": worker_pid,
        }
    )


def _reconcile_background_spawn(state_root: Path, inspection: _SpawnInspection) -> SpawnRecord:
    record = inspection.record
    if not inspection.spawn_dir_exists:
        if inspection.grace_elapsed:
            return _finalize_failed(state_root, record, "missing_spawn_dir")
        return record

    if inspection.wrapper_pid is None:
        if inspection.grace_elapsed:
            return _finalize_failed(state_root, record, "missing_wrapper_pid")
        return record

    if record.status == "queued":
        if not inspection.wrapper_alive:
            return _finalize_failed(state_root, record, "orphan_launch")
        record = _mark_running(
            state_root,
            record,
            launch_mode=BACKGROUND_LAUNCH_MODE,
            wrapper_pid=inspection.wrapper_pid,
            worker_pid=inspection.harness_pid,
        )

    if not inspection.wrapper_alive:
        # Wrapper is the coordinator — if it's dead, it won't finalize.
        if has_durable_report_completion(inspection.report_text):
            return _finalize_completed_report(state_root, record)
        if not inspection.harness_alive:
            return _finalize_failed(state_root, record, "orphan_run")
        # Wrapper dead, harness alive, no report yet.
        # If harness is stale (quiet >5min), it's stuck — fail.
        if inspection.stale:
            return _finalize_failed(state_root, record, "orphan_stale_harness")
        return record  # Harness still active — may still produce a report.

    # Wrapper alive — it will finalize. Just sync PID metadata.
    if (
        inspection.wrapper_pid == record.wrapper_pid
        and inspection.harness_pid == record.worker_pid
    ):
        return record
    return _mark_running(
        state_root,
        record,
        launch_mode=BACKGROUND_LAUNCH_MODE,
        wrapper_pid=inspection.wrapper_pid,
        worker_pid=inspection.harness_pid,
    )


def _reconcile_foreground_spawn(state_root: Path, inspection: _SpawnInspection) -> SpawnRecord:
    record = inspection.record
    primary_launch_lock_held = (
        record.kind == "primary"
        and record.status == "queued"
        and _primary_launch_lock_is_held(state_root)
    )
    if not inspection.spawn_dir_exists:
        if inspection.grace_elapsed:
            if primary_launch_lock_held:
                return record
            return _finalize_failed(state_root, record, "missing_spawn_dir")
        return record

    if inspection.harness_pid is None:
        if inspection.grace_elapsed:
            if primary_launch_lock_held:
                return record
            return _finalize_failed(state_root, record, "missing_worker_pid")
        return record

    if record.status == "queued" and inspection.harness_alive:
        record = _mark_running(
            state_root,
            record,
            launch_mode=FOREGROUND_LAUNCH_MODE,
            worker_pid=inspection.harness_pid,
        )

    if has_durable_report_completion(inspection.report_text):
        if not inspection.harness_alive:
            return _finalize_completed_report(state_root, record)
        # Harness alive with report — runner will finalize naturally.
        return record

    if not inspection.harness_alive and inspection.grace_elapsed:
        if primary_launch_lock_held:
            return record
        return _finalize_failed(state_root, record, "orphan_run")

    # Harness alive — runner will finalize. Just sync PID metadata.
    if inspection.harness_pid == record.worker_pid:
        return record
    return _mark_running(
        state_root,
        record,
        launch_mode=FOREGROUND_LAUNCH_MODE,
        worker_pid=inspection.harness_pid,
    )


def _reconcile_legacy_spawn(state_root: Path, inspection: _SpawnInspection) -> SpawnRecord:
    record = inspection.record
    if not inspection.spawn_dir_exists and inspection.grace_elapsed:
        return _finalize_failed(state_root, record, "missing_spawn_dir")
    if inspection.spawn_dir_exists:
        if inspection.wrapper_pid is None and inspection.harness_pid is None and inspection.grace_elapsed:
            return _finalize_failed(state_root, record, "missing_worker_pid")
        if has_durable_report_completion(inspection.report_text):
            if not inspection.wrapper_alive and not inspection.harness_alive:
                return _finalize_completed_report(state_root, record)
            return record
    return record


def reconcile_active_spawn(state_root: Path, record: SpawnRecord) -> SpawnRecord:
    """Reconcile one active spawn using persisted launch metadata."""
    if not is_active_spawn_status(record.status):
        return record

    inspection = _inspect_spawn_runtime(state_root, record, now=time.time())
    if inspection.launch_mode == BACKGROUND_LAUNCH_MODE:
        return _reconcile_background_spawn(state_root, inspection)
    if inspection.launch_mode == FOREGROUND_LAUNCH_MODE:
        return _reconcile_foreground_spawn(state_root, inspection)
    return _reconcile_legacy_spawn(state_root, inspection)


def reconcile_spawns(state_root: Path, spawns: list[SpawnRecord]) -> list[SpawnRecord]:
    """Batch reconciliation. Only touches active spawns."""
    return [
        reconcile_active_spawn(state_root, spawn) if is_active_spawn_status(spawn.status) else spawn
        for spawn in spawns
    ]
