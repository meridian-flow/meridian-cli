"""Telemetry status reporting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meridian.lib.core.util import FormatContext
from meridian.lib.state.liveness import is_process_alive
from meridian.lib.telemetry.reader import discover_segments
from meridian.lib.telemetry.retention import parse_segment_pid

ROOTLESS_LIMITATION_NOTE = (
    "Rootless processes (MCP stdio server) emit telemetry to stderr only "
    "and are outside the scope of local segment readers."
)


@dataclass(frozen=True)
class TelemetryStatus:
    """Health summary of the local telemetry sink."""

    telemetry_dir: Path
    segment_count: int
    total_bytes: int
    active_pids: list[int]
    rootless_note: str = ROOTLESS_LIMITATION_NOTE

    @property
    def total_size_human(self) -> str:
        """Human-readable total size."""
        if self.total_bytes < 1024:
            return f"{self.total_bytes} B"
        if self.total_bytes < 1024 * 1024:
            return f"{self.total_bytes / 1024:.1f} KB"
        return f"{self.total_bytes / (1024 * 1024):.1f} MB"

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Render a human-readable telemetry health summary."""
        _ = ctx
        active = ", ".join(str(pid) for pid in self.active_pids) or "none"
        return "\n".join(
            [
                f"Telemetry directory: {self.telemetry_dir}",
                f"Segment count: {self.segment_count}",
                f"Total size: {self.total_size_human}",
                f"Active writer PIDs: {active}",
                f"Note: {self.rootless_note}",
            ]
        )


def compute_status(runtime_root: Path) -> TelemetryStatus:
    """Compute telemetry sink status from disk state."""
    telemetry_dir = runtime_root / "telemetry"
    segments = discover_segments(telemetry_dir)
    total_bytes = 0
    pids: set[int] = set()
    for segment in segments:
        try:
            total_bytes += segment.stat().st_size
        except OSError:
            continue
        pid = parse_segment_pid(segment)
        if pid is not None and is_process_alive(pid):
            pids.add(pid)

    return TelemetryStatus(
        telemetry_dir=telemetry_dir,
        segment_count=len(segments),
        total_bytes=total_bytes,
        active_pids=sorted(pids),
    )
