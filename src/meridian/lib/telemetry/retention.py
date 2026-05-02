"""Retention cleanup for local telemetry JSONL segments."""

from __future__ import annotations

import os
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from meridian.lib.telemetry.router import emit_telemetry

_DEFAULT_MAX_AGE_DAYS = 7
_DEFAULT_MAX_TOTAL_BYTES = 100_000_000


@dataclass(frozen=True)
class SegmentInfo:
    path: Path
    pid: int
    size: int
    mtime: float
    live: bool

    @property
    def orphaned(self) -> bool:
        return not self.live


def parse_segment_pid(path: Path) -> int | None:
    """Parse the PID from a <pid>-<seq>.jsonl segment filename."""
    if path.suffix != ".jsonl":
        return None
    parts = path.stem.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        int(parts[1])
        return int(parts[0])
    except ValueError:
        return None


def run_retention_cleanup(
    telemetry_dir: Path,
    *,
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
    max_total_bytes: int = _DEFAULT_MAX_TOTAL_BYTES,
) -> None:
    """Delete eligible telemetry segments by age and total-size cap."""
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    now = time.time()
    current_pid = os.getpid()
    segments = _list_segments(telemetry_dir)
    max_age_secs = max_age_days * 24 * 60 * 60

    for segment in list(segments):
        if segment.pid == current_pid or segment.live:
            continue
        if now - segment.mtime > max_age_secs and _delete_segment(segment.path):
            segments.remove(segment)

    total_size = sum(segment.size for segment in segments if segment.path.exists())
    if total_size <= max_total_bytes:
        return

    # Prefer orphaned segments when enforcing the hard cap.
    for segment in sorted((s for s in segments if s.orphaned), key=lambda s: s.mtime):
        if total_size <= max_total_bytes:
            return
        if _delete_segment(segment.path):
            total_size -= segment.size

    # Last resort: closed files not owned by the current or any live process.
    for segment in sorted(
        (s for s in segments if s.pid != current_pid and not s.live and s.path.exists()),
        key=lambda s: s.mtime,
    ):
        if total_size <= max_total_bytes:
            return
        if _delete_segment(segment.path):
            total_size -= segment.size
            emit_telemetry(
                "runtime",
                "runtime.telemetry.consumer_data_lost",
                scope="telemetry.retention",
                severity="warning",
                data={"segment": segment.path.name, "bytes_lost": segment.size},
            )


def _list_segments(telemetry_dir: Path) -> list[SegmentInfo]:
    # Import lazily to avoid telemetry/core lifecycle import cycles at module load time.
    from meridian.lib.state.liveness import is_process_alive

    segments: list[SegmentInfo] = []
    for path in telemetry_dir.glob("*.jsonl"):
        pid = parse_segment_pid(path)
        if pid is None:
            continue
        with suppress(OSError):
            stat = path.stat()
            segments.append(
                SegmentInfo(
                    path=path,
                    pid=pid,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    live=is_process_alive(pid),
                )
            )
    return segments


def _delete_segment(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
