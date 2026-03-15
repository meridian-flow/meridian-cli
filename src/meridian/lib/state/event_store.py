"""Shared JSONL event store helpers for Meridian state files."""

from __future__ import annotations

import fcntl
import json
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, TypeVar, cast

from pydantic import BaseModel, ValidationError

from meridian.lib.state.atomic import append_text_line

T = TypeVar("T")
_THREAD_LOCAL = threading.local()
EventObserver = Callable[[str, dict[str, Any]], None]  # (store_name, event_payload)
_observers: list[EventObserver] = []


def register_observer(observer: EventObserver) -> None:
    _observers.append(observer)


def unregister_observer(observer: EventObserver) -> None:
    with suppress(ValueError):
        _observers.remove(observer)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _held_locks() -> dict[Path, tuple[IO[bytes], int]]:
    held = cast("dict[Path, tuple[IO[bytes], int]] | None", getattr(_THREAD_LOCAL, "held", None))
    if held is None:
        held = {}
        _THREAD_LOCAL.held = held
    return held


@contextmanager
def lock_file(lock_path: Path) -> Iterator[IO[bytes]]:
    key = lock_path.resolve()
    held = _held_locks()
    existing = held.get(key)
    if existing is not None:
        handle, depth = existing
        held[key] = (handle, depth + 1)
        try:
            yield handle
        finally:
            current_handle, current_depth = held[key]
            if current_depth <= 1:
                held.pop(key, None)
            else:
                held[key] = (current_handle, current_depth - 1)
        return

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        held[key] = (handle, 1)
        try:
            yield handle
        finally:
            held.pop(key, None)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_event(
    data_path: Path,
    lock_path: Path,
    event: BaseModel,
    *,
    store_name: str,
    exclude_none: bool = False,
) -> None:
    payload = event.model_dump(exclude_none=exclude_none)
    line = json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
    with lock_file(lock_path):
        append_text_line(data_path, line)

    # Notify observers after durable write, outside the lock.
    # Snapshot the list so mutations during dispatch are safe.
    for observer in list(_observers):
        with suppress(Exception):
            observer(store_name, payload)


def read_events(
    data_path: Path,
    parse_event: Callable[[dict[str, Any]], T | None],
) -> list[T]:
    if not data_path.exists():
        return []

    rows: list[T] = []
    with data_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                # Self-healing: ignore malformed/truncated lines.
                continue
            if not isinstance(payload, dict):
                continue
            try:
                parsed = parse_event(cast("dict[str, Any]", payload))
            except ValidationError:
                continue
            if parsed is not None:
                rows.append(parsed)
    return rows
