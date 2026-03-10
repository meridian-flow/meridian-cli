"""Spawn reconciliation: detect orphaned/stuck spawns and optionally clean them up."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Literal

import structlog

from meridian.lib.state.spawn_store import SpawnRecord, finalize_spawn_if_running
from meridian.lib.core.types import SpawnId

logger = structlog.get_logger(__name__)

_STALE_THRESHOLD_SECS = 300  # 5 minutes of no output = stale
_KILL_GRACE_SECS = 10

ReapReason = Literal["orphan_run", "harness_completed", "stale", "forced"]


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
    # Check output files first
    for name in ("output.jsonl", "stderr.log"):
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


def _kill_pid_escalate(pid: int) -> None:
    """SIGTERM → sleep → SIGKILL on a process group. Best-effort."""
    import signal as _signal

    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return

    try:
        os.killpg(pgid, _signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        logger.warning("Permission denied sending SIGTERM to pgid=%d", pgid)
        return

    # Wait briefly for clean exit
    deadline = time.monotonic() + _KILL_GRACE_SECS
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return  # Exited
        except PermissionError:
            return
        time.sleep(0.5)

    # Still alive — escalate to SIGKILL
    try:
        os.killpg(pgid, _signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        logger.warning("Permission denied sending SIGKILL to pgid=%d", pgid)


# ---------------------------------------------------------------------------
# Read-path reconciliation (lightweight, no killing)
# ---------------------------------------------------------------------------


def reconcile_running_spawn(state_root: Path, record: SpawnRecord) -> SpawnRecord:
    """Detect-only reconciliation for read paths.

    Repairs dead orphans (PID gone) by finalizing them. Does NOT kill
    processes — that's the job of reap_stuck_spawn() / gc.
    """
    if record.status != "running":
        return record

    spawn_dir = state_root / "spawns" / record.id
    bg_pid_file = spawn_dir / "background.pid"
    harness_pid_file = spawn_dir / "harness.pid"

    bg_pid = _read_pid_file(spawn_dir, "background.pid")
    harness_pid = _read_pid_file(spawn_dir, "harness.pid")

    if bg_pid is None and harness_pid is None:
        return record  # No PID files — can't determine state

    if bg_pid is None:
        # No background.pid — likely a foreground spawn. Foreground spawns are
        # managed by the runner process, so we can't safely reconcile from the
        # read path using harness.pid alone.
        return record

    # Check if ANY known process is still alive
    bg_alive = _pid_is_alive(bg_pid, bg_pid_file)
    harness_alive = harness_pid is not None and _pid_is_alive(harness_pid, harness_pid_file)

    if bg_alive or harness_alive:
        return record  # At least one process alive — don't touch

    # All known processes are dead — orphan
    error = "orphan_run"
    finalized = finalize_spawn_if_running(
        state_root,
        SpawnId(record.id),
        status="failed",
        exit_code=1,
        error=error,
    )
    if finalized:
        logger.info(
            "Reconciled orphaned spawn.",
            spawn_id=record.id,
            error=error,
        )
        return record.model_copy(update={"status": "failed", "exit_code": 1, "error": error})
    return record


def reconcile_spawns(state_root: Path, spawns: list[SpawnRecord]) -> list[SpawnRecord]:
    """Batch reconciliation. Only touches spawns with status=='running'."""
    return [
        reconcile_running_spawn(state_root, spawn) if spawn.status == "running" else spawn
        for spawn in spawns
    ]


# ---------------------------------------------------------------------------
# Active cleanup (gc / doctor)
# ---------------------------------------------------------------------------


def reap_stuck_spawn(state_root: Path, spawn_id: str, *, force: bool = False) -> ReapReason | None:
    """Active cleanup for gc/doctor. Kills processes and finalizes.

    Returns a reason string if the spawn was reaped, or None if nothing to do.
    When force=True, missing PID files are treated as forced finalization.
    """
    from meridian.lib.state.spawn_store import get_spawn

    record = get_spawn(state_root, spawn_id)
    if record is None or record.status != "running":
        return None

    spawn_dir = state_root / "spawns" / record.id
    bg_pid_file = spawn_dir / "background.pid"
    harness_pid_file = spawn_dir / "harness.pid"
    report_file = spawn_dir / "report.md"

    bg_pid = _read_pid_file(spawn_dir, "background.pid")
    harness_pid = _read_pid_file(spawn_dir, "harness.pid")

    bg_alive = bg_pid is not None and _pid_is_alive(bg_pid, bg_pid_file)
    harness_alive = harness_pid is not None and _pid_is_alive(harness_pid, harness_pid_file)
    has_report = report_file.exists()

    reason: ReapReason | None = None

    if not bg_alive and bg_pid is not None:
        # Dead background worker — orphan
        reason = "orphan_run"
    elif bg_alive and has_report:
        # Harness wrote report but process is still alive — hung wrapper
        reason = "harness_completed"
    elif bg_alive and not has_report and _spawn_is_stale(spawn_dir, bg_pid_file):
        # Alive but no output for 5 minutes — stale
        reason = "stale"
    elif bg_pid is None:
        if harness_pid is not None and not harness_alive:
            # Harness process is dead — orphan
            reason = "orphan_run"
        elif force:
            reason = "forced"
        # else: no PID file, can't determine state — skip

    if reason is None:
        return None  # Spawn looks healthy

    # Kill processes: harness child first, then background worker
    if harness_pid is not None and harness_alive:
        _kill_pid_escalate(harness_pid)
    if bg_pid is not None and bg_alive:
        _kill_pid_escalate(bg_pid)

    finalized = finalize_spawn_if_running(
        state_root,
        SpawnId(spawn_id),
        status="failed",
        exit_code=1,
        error=reason,
    )
    if finalized:
        logger.info(
            "Reaped stuck spawn.",
            spawn_id=spawn_id,
            reason=reason,
        )
    return reason
