"""Telemetry query helpers for the CLI reader surface."""

from __future__ import annotations

import re
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from meridian.lib.telemetry.reader import discover_segments, read_events

_DURATION_RE = re.compile(r"^(\d+)([smhd])$")
_UNIT_MAP = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def parse_since(since: str) -> str:
    """Parse a duration string like ``1h`` into an ISO-8601 UTC timestamp."""
    match = _DURATION_RE.match(since.strip().lower())
    if not match:
        raise ValueError(f"Invalid duration format: {since!r}. Expected NNs, NNm, NNh, or NNd.")
    value = int(match.group(1))
    unit = _UNIT_MAP[match.group(2)]
    cutoff = datetime.now(UTC) - timedelta(**{unit: value})
    return cutoff.isoformat().replace("+00:00", "Z")


def query_events(
    telemetry_dir: Path,
    *,
    since: str | None = None,
    domain: str | None = None,
    ids_filter: dict[str, str] | None = None,
    limit: int | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Query historical telemetry events with optional filters.

    Reads all segments in mtime order, applying filters.
    """
    since_ts = parse_since(since) if since else None
    count = 0
    for segment in discover_segments(telemetry_dir):
        for event in read_events(segment, since_ts=since_ts, domain=domain, ids_filter=ids_filter):
            yield event
            count += 1
            if limit is not None and count >= limit:
                return
