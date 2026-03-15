"""Filesystem heartbeat writers for spawn liveness."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager, suppress
from pathlib import Path

from meridian.lib.state.atomic import atomic_write_text


def _touch_heartbeat(path: Path) -> None:
    """Atomically write current timestamp to heartbeat file."""

    atomic_write_text(path, f"{time.time()}\n")


async def _heartbeat_loop(path: Path, interval_secs: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        _touch_heartbeat(path)
        await asyncio.sleep(interval_secs)


@asynccontextmanager
async def heartbeat_scope(path: Path, *, interval_secs: int = 30) -> AsyncIterator[None]:
    """Write a heartbeat file periodically to prove the spawn is alive."""

    task = asyncio.create_task(_heartbeat_loop(path, interval_secs))
    try:
        yield
    finally:
        task.cancel()
        with suppress(BaseException):
            await task


@contextmanager
def threaded_heartbeat_scope(path: Path, *, interval_secs: int = 30) -> Iterator[None]:
    """Synchronous context manager that runs heartbeat in a daemon thread."""

    stop_event = threading.Event()

    def _writer() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        _touch_heartbeat(path)
        while not stop_event.wait(interval_secs):
            _touch_heartbeat(path)

    thread = threading.Thread(target=_writer, daemon=True, name="meridian-heartbeat")
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=5.0)
