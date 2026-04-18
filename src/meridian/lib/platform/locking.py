"""Cross-platform file locking primitives for Meridian state stores."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Any, cast

from meridian.lib.platform import IS_WINDOWS

_THREAD_LOCAL = threading.local()


def _held_locks() -> dict[Path, tuple[IO[bytes], int]]:
    """Return thread-local map of lock path -> (handle, reentrant depth)."""
    held = cast("dict[Path, tuple[IO[bytes], int]] | None", getattr(_THREAD_LOCAL, "held", None))
    if held is None:
        held = {}
        _THREAD_LOCAL.held = held
    return held


@contextmanager
def lock_file(lock_path: Path) -> Iterator[IO[bytes]]:
    """Acquire an exclusive file lock with thread-local reentrancy support."""
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
        if IS_WINDOWS:
            _acquire_windows_lock(handle)
        else:
            _acquire_posix_lock(handle)
        held[key] = (handle, 1)
        try:
            yield handle
        finally:
            held.pop(key, None)
            if IS_WINDOWS:
                _release_windows_lock(handle)
            else:
                _release_posix_lock(handle)


def _acquire_posix_lock(handle: IO[bytes]) -> None:
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)


def _release_posix_lock(handle: IO[bytes]) -> None:
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _acquire_windows_lock(handle: IO[bytes]) -> None:
    import msvcrt as _msvcrt

    msvcrt = cast("Any", _msvcrt)

    # msvcrt locks byte ranges, so pin a 1-byte region at offset 0.
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)
    while True:
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        except OSError:
            time.sleep(0.05)


def _release_windows_lock(handle: IO[bytes]) -> None:
    import msvcrt as _msvcrt

    msvcrt = cast("Any", _msvcrt)

    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


__all__ = ["lock_file"]
