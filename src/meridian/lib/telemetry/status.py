"""Telemetry status reporting."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

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
        return format_status_dict(status_to_dict(self))


def status_to_dict(status: TelemetryStatus) -> dict[str, Any]:
    """Return a JSON-serializable telemetry status payload."""
    result = asdict(status)
    result["telemetry_dir"] = str(result["telemetry_dir"])
    result["total_size_human"] = status.total_size_human
    return result


def format_status_dict(status: dict[str, Any]) -> str:
    """Render a telemetry status payload as human-readable text."""
    active_pids = status.get("active_pids", [])
    if isinstance(active_pids, list):
        pid_values = cast("list[object]", active_pids)
        active = ", ".join(str(pid) for pid in pid_values) or "none"
    else:
        active = "none"
    return "\n".join(
        [
            f"Telemetry directory: {status.get('telemetry_dir', '')}",
            f"Segment count: {status.get('segment_count', 0)}",
            f"Total size: {status.get('total_size_human', '')}",
            f"Active writer PIDs: {active}",
            f"Note: {status.get('rootless_note', ROOTLESS_LIMITATION_NOTE)}",
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
