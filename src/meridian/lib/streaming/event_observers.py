"""Post-persist harness event observer delivery."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Protocol

from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import HarnessEvent

logger = logging.getLogger(__name__)

HarnessEventCallback = Callable[[HarnessEvent], Awaitable[None] | None]


class EventObserver(Protocol):
    """Post-persist observer for one spawn's harness events."""

    async def on_event(self, spawn_id: SpawnId, event: HarnessEvent) -> None:
        """Observe one persisted harness event."""
        ...

    async def on_complete(self, spawn_id: SpawnId) -> None:
        """Observe drain completion for one spawn."""
        ...


class CallbackObserver:
    """Compatibility adapter for the legacy single-event callback hook."""

    def __init__(self, callback: HarnessEventCallback) -> None:
        self._callback = callback

    async def on_event(self, spawn_id: SpawnId, event: HarnessEvent) -> None:
        """Dispatch one event to the wrapped callback."""

        _ = spawn_id
        result = self._callback(event)
        if result is not None:
            await result

    async def on_complete(self, spawn_id: SpawnId) -> None:
        """No-op completion hook for callback compatibility."""

        _ = spawn_id


class QueuedObserver:
    """Bounded non-blocking observer delivery for one spawn.

    The SpawnManager drain loop calls :meth:`enqueue` synchronously after
    persistence. Delivery to the observer happens on this object's background
    task so slow or failing observers do not block event persistence or
    subscriber fan-out.
    """

    def __init__(
        self,
        observer: EventObserver,
        spawn_id: SpawnId,
        max_buffer: int = 1000,
    ) -> None:
        self._observer = observer
        self._spawn_id = spawn_id
        self._queue: asyncio.Queue[HarnessEvent | None] = asyncio.Queue(maxsize=max_buffer)
        self._task = asyncio.create_task(self._drain())

    @property
    def task(self) -> asyncio.Task[None]:
        """Return the background drain task."""

        return self._task

    def enqueue(self, event: HarnessEvent) -> None:
        """Queue one event without blocking; drop and warn if full."""

        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(
                "Observer queue full for spawn %s, dropping event %s",
                self._spawn_id,
                event.event_type,
            )

    def complete(self) -> None:
        """Signal completion, preserving the sentinel under backpressure."""

        while True:
            try:
                self._queue.put_nowait(None)
                return
            except asyncio.QueueFull:
                with suppress(asyncio.QueueEmpty):
                    self._queue.get_nowait()

    async def _drain(self) -> None:
        while True:
            event = await self._queue.get()
            if event is None:
                break
            try:
                await self._observer.on_event(self._spawn_id, event)
            except Exception:
                logger.exception("Observer failed for spawn %s", self._spawn_id)
        try:
            await self._observer.on_complete(self._spawn_id)
        except Exception:
            logger.exception("Observer completion failed for spawn %s", self._spawn_id)


class EventObserverRegistry:
    """Per-spawn observer registry with enqueue-and-continue dispatch."""

    def __init__(self, *, max_buffer: int = 1000) -> None:
        self._max_buffer = max_buffer
        self._observers: dict[SpawnId, list[QueuedObserver]] = {}

    def register(self, spawn_id: SpawnId, observer: EventObserver) -> None:
        """Register one observer for a spawn."""

        queued = QueuedObserver(observer, spawn_id, max_buffer=self._max_buffer)
        self._observers.setdefault(spawn_id, []).append(queued)

    def dispatch(self, spawn_id: SpawnId, event: HarnessEvent) -> None:
        """Non-blocking enqueue to all observers registered for a spawn."""

        for queued in self._observers.get(spawn_id, []):
            queued.enqueue(event)

    def complete(self, spawn_id: SpawnId) -> None:
        """Signal completion to all observers for a spawn without waiting."""

        for queued in self._observers.get(spawn_id, []):
            queued.complete()

    async def shutdown(self, spawn_id: SpawnId) -> None:
        """Signal completion and wait for observer delivery tasks to finish."""

        queued_observers = self._observers.pop(spawn_id, [])
        for queued in queued_observers:
            queued.complete()
        for queued in queued_observers:
            with suppress(asyncio.CancelledError):
                await queued.task


__all__ = [
    "CallbackObserver",
    "EventObserver",
    "EventObserverRegistry",
    "HarnessEventCallback",
    "QueuedObserver",
]
