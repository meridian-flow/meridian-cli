"""Cached background doctor scan summaries for CLI startup warnings."""

from __future__ import annotations

import threading
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from meridian.lib.ops.diag import DoctorInput, DoctorOutput, doctor_sync
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.user_paths import get_user_home

SCAN_COOLDOWN = timedelta(hours=24)


class DoctorCache(BaseModel):
    model_config = ConfigDict(frozen=True)

    scanned_at: str
    stale_orphan_dirs: int = 0
    stale_spawn_artifacts: int = 0
    warning_count: int = 0
    message: str = ""
    displayed_at: str | None = Field(default=None)


def doctor_cache_path() -> Path:
    return get_user_home() / "doctor-cache.json"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def read_doctor_cache(path: Path | None = None) -> DoctorCache | None:
    cache_path = doctor_cache_path() if path is None else path
    try:
        return DoctorCache.model_validate_json(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return None


def write_doctor_cache(cache: DoctorCache, path: Path | None = None) -> None:
    cache_path = doctor_cache_path() if path is None else path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(cache_path, cache.model_dump_json(indent=2) + "\n")


def doctor_scan_is_stale(cache: DoctorCache | None, *, now: datetime | None = None) -> bool:
    scanned_at = _parse_timestamp(cache.scanned_at if cache is not None else None)
    if scanned_at is None:
        return True
    return (_utc_now() if now is None else now) - scanned_at >= SCAN_COOLDOWN


def doctor_cache_warning_due(cache: DoctorCache, *, now: datetime | None = None) -> bool:
    if cache.warning_count <= 0:
        return False
    displayed_at = _parse_timestamp(cache.displayed_at)
    if displayed_at is None:
        return True
    return (_utc_now() if now is None else now) - displayed_at >= SCAN_COOLDOWN


def _format_count(count: int, singular: str, plural: str) -> str | None:
    if count <= 0:
        return None
    label = singular if count == 1 else plural
    return f"{count} {label}"


def summarize_doctor_output(output: DoctorOutput, *, now: datetime | None = None) -> DoctorCache:
    stale_orphan_dirs = len(output.orphan_project_dirs)
    stale_spawn_artifacts = len(output.stale_spawn_artifacts)
    warning_count = len(output.warnings)
    parts = [
        part
        for part in (
            _format_count(stale_orphan_dirs, "stale project dir", "stale project dirs"),
            _format_count(
                stale_spawn_artifacts,
                "stale spawn artifact",
                "stale spawn artifacts",
            ),
            _format_count(
                max(0, warning_count - int(stale_orphan_dirs > 0) - int(stale_spawn_artifacts > 0)),
                "other warning",
                "other warnings",
            ),
        )
        if part is not None
    ]
    message = ""
    if parts:
        message = "meridian doctor: " + ", ".join(parts) + "."
        if stale_orphan_dirs > 0 or stale_spawn_artifacts > 0:
            message += " Run 'meridian doctor --prune --global' to clean up."
    return DoctorCache(
        scanned_at=(_utc_now() if now is None else now).isoformat(),
        stale_orphan_dirs=stale_orphan_dirs,
        stale_spawn_artifacts=stale_spawn_artifacts,
        warning_count=warning_count,
        message=message,
    )


def run_background_doctor_scan_once() -> None:
    output = doctor_sync(DoctorInput(global_=True))
    write_doctor_cache(summarize_doctor_output(output))


def _run_background_doctor_scan_silently() -> None:
    with suppress(Exception):
        run_background_doctor_scan_once()


def maybe_start_background_doctor_scan() -> bool:
    cache = read_doctor_cache()
    if not doctor_scan_is_stale(cache):
        return False
    thread = threading.Thread(
        target=_run_background_doctor_scan_silently,
        name="meridian-doctor-cache-scan",
        daemon=True,
    )
    thread.start()
    return True


def consume_doctor_cache_warning(path: Path | None = None) -> str | None:
    cache = read_doctor_cache(path)
    if cache is None or not doctor_cache_warning_due(cache):
        return None
    message = cache.message.strip()
    if not message:
        return None
    write_doctor_cache(
        cache.model_copy(update={"displayed_at": _utc_now().isoformat()}),
        path,
    )
    return message
