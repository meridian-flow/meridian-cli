from __future__ import annotations

import asyncio

import pytest

from meridian.lib.app.stream import SpawnMultiSubscriberManager, StreamBroadcaster
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import HarnessEvent


class _FakeManager:
    def __init__(self) -> None:
        self.connections: dict[SpawnId, object] = {}
        self.queues: dict[SpawnId, asyncio.Queue[HarnessEvent | None]] = {}
        self.subscribe_calls: list[SpawnId] = []
        self.unsubscribe_calls: list[SpawnId] = []

    def subscribe(self, spawn_id: SpawnId) -> asyncio.Queue[HarnessEvent | None] | None:
        self.subscribe_calls.append(spawn_id)
        queue: asyncio.Queue[HarnessEvent | None] = asyncio.Queue()
        self.queues[spawn_id] = queue
        return queue

    def unsubscribe(self, spawn_id: SpawnId) -> None:
        self.unsubscribe_calls.append(spawn_id)

    def get_connection(self, spawn_id: SpawnId) -> object | None:
        return self.connections.get(spawn_id)


@pytest.mark.asyncio
async def test_stream_broadcaster_drops_oldest_event_when_queue_is_full() -> None:
    """Backpressured subscribers should keep the newest event."""

    broadcaster = StreamBroadcaster(maxsize=1)
    subscriber_id, queue = await broadcaster.subscribe()

    broadcaster.broadcast({"type": "first"})
    broadcaster.broadcast({"type": "second"})

    assert await asyncio.wait_for(queue.get(), timeout=1) == {"type": "second"}

    await broadcaster.unsubscribe(subscriber_id)


@pytest.mark.asyncio
async def test_stream_broadcaster_close_overrides_backpressure() -> None:
    """Closing should force terminal None through a full subscriber queue."""

    broadcaster = StreamBroadcaster(maxsize=1)
    subscriber_id, queue = await broadcaster.subscribe()

    broadcaster.broadcast({"type": "stale"})
    broadcaster.broadcast_close()

    assert await asyncio.wait_for(queue.get(), timeout=1) is None

    await broadcaster.unsubscribe(subscriber_id)


@pytest.mark.asyncio
async def test_spawn_multi_subscriber_manager_shares_underlying_subscription() -> None:
    """Multiple subscribers for one spawn should share a single pump lifecycle."""

    spawn_id = SpawnId("p1")
    spawn_manager = _FakeManager()
    spawn_manager.connections[spawn_id] = object()
    manager = SpawnMultiSubscriberManager(spawn_manager)

    first = await manager.subscribe(spawn_id)
    second = await manager.subscribe(spawn_id)

    assert first is not None
    assert second is not None
    assert spawn_manager.subscribe_calls == [spawn_id]

    first_id, first_queue = first
    second_id, second_queue = second

    spawn_manager.queues[spawn_id].put_nowait(
        HarnessEvent(
            event_type="token",
            payload={"delta": "hi"},
            harness_id="codex",
        )
    )

    expected = {
        "type": "spawn.event",
        "spawn_id": "p1",
        "event_type": "token",
        "harness_id": "codex",
        "payload": {"delta": "hi"},
    }

    first_event = await asyncio.wait_for(first_queue.get(), timeout=1)
    second_event = await asyncio.wait_for(second_queue.get(), timeout=1)

    assert {key: first_event[key] for key in expected} == expected
    assert {key: second_event[key] for key in expected} == expected

    await manager.unsubscribe(spawn_id, first_id)
    assert spawn_manager.unsubscribe_calls == []

    await manager.unsubscribe(spawn_id, second_id)
    assert spawn_manager.unsubscribe_calls == [spawn_id]
