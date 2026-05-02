"""Local JSONL telemetry segment reader."""

from __future__ import annotations

import json
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any


def discover_segments(telemetry_dir: Path) -> list[Path]:
    """Return all JSONL segments sorted by mtime ascending."""
    if not telemetry_dir.is_dir():
        return []
    segments: list[Path] = []
    for path in telemetry_dir.glob("*.jsonl"):
        try:
            path.stat()
        except OSError:
            continue
        segments.append(path)
    return sorted(segments, key=lambda p: p.stat().st_mtime)


def _matches_filters(
    envelope: dict[str, Any],
    *,
    since_ts: str | None = None,
    domain: str | None = None,
    ids_filter: dict[str, str] | None = None,
) -> bool:
    if since_ts and envelope.get("ts", "") < since_ts:
        return False
    if domain and envelope.get("domain") != domain:
        return False
    if ids_filter:
        event_ids = envelope.get("ids") or {}
        if not isinstance(event_ids, dict):
            return False
        return all(event_ids.get(key) == value for key, value in ids_filter.items())
    return True


def read_events(
    path: Path,
    *,
    since_ts: str | None = None,
    domain: str | None = None,
    ids_filter: dict[str, str] | None = None,
) -> Generator[dict[str, Any], None, None]:
    """Yield parsed telemetry envelopes from a segment, applying optional filters.

    Truncation-tolerant: silently skips lines that fail JSON parsing.
    """
    try:
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                try:
                    envelope = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(envelope, dict):
                    continue
                if _matches_filters(
                    envelope,
                    since_ts=since_ts,
                    domain=domain,
                    ids_filter=ids_filter,
                ):
                    yield envelope
    except OSError:
        return


def tail_events(
    telemetry_dir: Path,
    *,
    domain: str | None = None,
    ids_filter: dict[str, str] | None = None,
    poll_interval: float = 1.0,
) -> Generator[dict[str, Any], None, None]:
    """Follow telemetry segments, yielding new events as they arrive.

    Watches for new lines in existing segments and new segments appearing.
    Like ``tail -f`` but across rotating JSONL segment files.
    """
    seen_files: dict[Path, int] = {}

    for segment in discover_segments(telemetry_dir):
        try:
            seen_files[segment] = segment.stat().st_size
        except OSError:
            continue

    while True:
        found_new = False
        for segment in discover_segments(telemetry_dir):
            offset = seen_files.get(segment, 0)
            try:
                size = segment.stat().st_size
            except OSError:
                continue
            if size <= offset:
                continue
            try:
                with segment.open("r", encoding="utf-8") as file:
                    file.seek(offset)
                    for line in file:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            envelope = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if not isinstance(envelope, dict):
                            continue
                        if _matches_filters(envelope, domain=domain, ids_filter=ids_filter):
                            found_new = True
                            yield envelope
                    seen_files[segment] = file.tell()
            except OSError:
                continue
        if not found_new:
            time.sleep(poll_interval)
