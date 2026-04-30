from __future__ import annotations

import asyncio
import logging

import pytest

from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.streaming.event_observers import EventObserverRegistry, QueuedObserver


def _event(event_type: str) -> HarnessEvent:
    return HarnessEvent(event_type=event_type, harness_id="codex", payload={})


class RecordingObserver:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.completed = asyncio.Event()

    async def on_event(self, spawn_id: SpawnId, event: HarnessEvent) -> None:
        _ = spawn_id
        self.events.append(event.event_type)

    async def on_complete(self, spawn_id: SpawnId) -> None:
        _ = spawn_id
        self.completed.set()


@pytest.mark.asyncio
async def test_observer_events_flow_through_queue() -> None:
    spawn_id = SpawnId("s-observer")
    observer = RecordingObserver()
    registry = EventObserverRegistry()

    registry.register(spawn_id, observer)
    registry.dispatch(spawn_id, _event("turn/started"))

    await registry.shutdown(spawn_id)

    assert observer.events == ["turn/started"]
    assert observer.completed.is_set()


@pytest.mark.asyncio
async def test_queue_full_drops_events_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    spawn_id = SpawnId("s-full")
    observer = RecordingObserver()
    queued = QueuedObserver(observer, spawn_id, max_buffer=1)

    with caplog.at_level(logging.WARNING):
        queued.enqueue(_event("first"))
        queued.enqueue(_event("dropped"))

    queued.complete()
    await queued.task

    assert "Observer queue full for spawn s-full, dropping event dropped" in caplog.text
    assert observer.completed.is_set()


@pytest.mark.asyncio
async def test_completion_sentinel_arrives_when_queue_full() -> None:
    spawn_id = SpawnId("s-complete")
    observer = RecordingObserver()
    queued = QueuedObserver(observer, spawn_id, max_buffer=1)

    queued.enqueue(_event("fills-buffer"))
    queued.complete()
    await asyncio.wait_for(observer.completed.wait(), timeout=1.0)
    await queued.task

    assert observer.completed.is_set()


@pytest.mark.asyncio
async def test_observer_exceptions_are_logged_without_propagating(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spawn_id = SpawnId("s-failing")

    class FailingObserver(RecordingObserver):
        async def on_event(self, spawn_id: SpawnId, event: HarnessEvent) -> None:
            _ = spawn_id, event
            raise RuntimeError("boom")

    observer = FailingObserver()
    queued = QueuedObserver(observer, spawn_id)

    with caplog.at_level(logging.ERROR):
        queued.enqueue(_event("bad"))
        queued.complete()
        await queued.task

    assert "Observer failed for spawn s-failing" in caplog.text
    assert observer.completed.is_set()


@pytest.mark.asyncio
async def test_registry_dispatches_to_multiple_observers() -> None:
    spawn_id = SpawnId("s-many")
    first = RecordingObserver()
    second = RecordingObserver()
    registry = EventObserverRegistry()

    registry.register(spawn_id, first)
    registry.register(spawn_id, second)
    registry.dispatch(spawn_id, _event("item.completed"))

    await registry.shutdown(spawn_id)

    assert first.events == ["item.completed"]
    assert second.events == ["item.completed"]


@pytest.mark.asyncio
async def test_registry_unregister_removes_only_requested_observer() -> None:
    spawn_id = SpawnId("s-unregister")
    removed = RecordingObserver()
    kept = RecordingObserver()
    registry = EventObserverRegistry()

    registry.register(spawn_id, removed)
    registry.register(spawn_id, kept)
    registry.unregister(spawn_id, removed)
    registry.dispatch(spawn_id, _event("after-unregister"))

    await registry.shutdown(spawn_id)

    assert removed.events == []
    assert kept.events == ["after-unregister"]
