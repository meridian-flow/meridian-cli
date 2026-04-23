from __future__ import annotations

import asyncio
from typing import Any

import pytest

from meridian.lib.app.stream import BroadcastHub, SpawnMultiSubscriberManager, StreamBroadcaster
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
async def test_broadcast_hub_works_with_arbitrary_type() -> None:
    """BroadcastHub should broadcast any type, not just dicts or HarnessEvents."""

    hub: BroadcastHub[str] = BroadcastHub(maxsize=10)
    sub_id, queue = await hub.subscribe()

    hub.broadcast("hello")
    hub.broadcast("world")

    assert await asyncio.wait_for(queue.get(), timeout=1) == "hello"
    assert await asyncio.wait_for(queue.get(), timeout=1) == "world"

    hub.broadcast_close()
    assert await asyncio.wait_for(queue.get(), timeout=1) is None

    await hub.unsubscribe(sub_id)


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
    spawn_manager_any: Any = spawn_manager
    manager = SpawnMultiSubscriberManager(spawn_manager_any)

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

    first_event = await asyncio.wait_for(first_queue.get(), timeout=1)
    second_event = await asyncio.wait_for(second_queue.get(), timeout=1)

    assert first_event == HarnessEvent(
        event_type="token",
        payload={"delta": "hi"},
        harness_id="codex",
    )
    assert second_event == HarnessEvent(
        event_type="token",
        payload={"delta": "hi"},
        harness_id="codex",
    )

    await manager.unsubscribe(spawn_id, first_id)
    assert spawn_manager.unsubscribe_calls == []

    await manager.unsubscribe(spawn_id, second_id)
    assert spawn_manager.unsubscribe_calls == [spawn_id]


@pytest.mark.asyncio
async def test_spawn_multi_subscriber_manager_cleans_up_after_terminal_event() -> None:
    spawn_id = SpawnId("p2")
    spawn_manager = _FakeManager()
    spawn_manager.connections[spawn_id] = object()
    spawn_manager_any: Any = spawn_manager
    manager = SpawnMultiSubscriberManager(spawn_manager_any)

    first = await manager.subscribe(spawn_id)
    assert first is not None
    first_id, first_queue = first

    spawn_manager.queues[spawn_id].put_nowait(None)

    assert await asyncio.wait_for(first_queue.get(), timeout=1) is None
    await asyncio.sleep(0)

    second = await manager.subscribe(spawn_id)
    assert second is not None
    second_id, _second_queue = second
    assert spawn_manager.subscribe_calls == [spawn_id, spawn_id]

    await manager.unsubscribe(spawn_id, first_id)
    await manager.unsubscribe(spawn_id, second_id)
