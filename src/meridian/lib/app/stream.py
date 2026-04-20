"""SSE streaming endpoint for multiplexed spawn and work updates."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from pathlib import Path
from typing import Protocol, cast

from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.streaming.spawn_manager import SpawnManager

logger = logging.getLogger(__name__)


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...


class StreamBroadcaster:
    """Multi-subscriber broadcast manager for SSE streams.
    
    Manages multiple subscriber queues and broadcasts events to all of them.
    Thread-safe through asyncio primitives.
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._subscribers: dict[int, asyncio.Queue[dict[str, object] | None]] = {}
        self._next_id = 0
        self._lock = asyncio.Lock()
        self._maxsize = maxsize

    async def subscribe(self) -> tuple[int, asyncio.Queue[dict[str, object] | None]]:
        """Create a new subscriber queue and return (subscriber_id, queue)."""
        async with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue(
                maxsize=self._maxsize
            )
            self._subscribers[sub_id] = queue
            return sub_id, queue

    async def unsubscribe(self, subscriber_id: int) -> None:
        """Remove a subscriber."""
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)

    def broadcast(self, event: dict[str, object]) -> None:
        """Send event to all subscribers, dropping if queue is full."""
        for queue in list(self._subscribers.values()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest event and try again
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
                with suppress(asyncio.QueueFull):
                    queue.put_nowait(event)

    def broadcast_close(self) -> None:
        """Signal all subscribers to close."""
        for queue in list(self._subscribers.values()):
            # Force the terminal None through even under backpressure
            while True:
                try:
                    queue.put_nowait(None)
                    break
                except asyncio.QueueFull:
                    with suppress(asyncio.QueueEmpty):
                        queue.get_nowait()

    @property
    def subscriber_count(self) -> int:
        """Return current subscriber count."""
        return len(self._subscribers)


class SpawnMultiSubscriberManager:
    """Wraps SpawnManager to support multiple SSE/WS subscribers per spawn.
    
    SpawnManager's native subscribe() only allows one subscriber per spawn.
    This manager creates a single subscription to SpawnManager and broadcasts
    events to multiple StreamBroadcaster subscribers.
    """

    def __init__(self, spawn_manager: SpawnManager) -> None:
        self._spawn_manager = spawn_manager
        self._broadcasters: dict[SpawnId, StreamBroadcaster] = {}
        self._pump_tasks: dict[SpawnId, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self, spawn_id: SpawnId
    ) -> tuple[int, asyncio.Queue[dict[str, object] | None]] | None:
        """Subscribe to spawn events. Returns (subscriber_id, queue) or None if spawn not found."""
        async with self._lock:
            # Get or create broadcaster for this spawn
            if spawn_id not in self._broadcasters:
                # Try to subscribe to the underlying spawn
                queue = self._spawn_manager.subscribe(spawn_id)
                if queue is None:
                    # Check if another subscriber already exists
                    connection = self._spawn_manager.get_connection(spawn_id)
                    if connection is None:
                        return None
                    # Already subscribed - need to use our existing broadcaster
                    if spawn_id in self._broadcasters:
                        return await self._broadcasters[spawn_id].subscribe()
                    # Can't subscribe - another subscriber has the slot
                    return None
                
                # Create broadcaster and start pump task
                broadcaster = StreamBroadcaster()
                self._broadcasters[spawn_id] = broadcaster
                self._pump_tasks[spawn_id] = asyncio.create_task(
                    self._pump_loop(spawn_id, queue)
                )
            
            return await self._broadcasters[spawn_id].subscribe()

    async def unsubscribe(self, spawn_id: SpawnId, subscriber_id: int) -> None:
        """Unsubscribe from spawn events."""
        async with self._lock:
            broadcaster = self._broadcasters.get(spawn_id)
            if broadcaster is not None:
                await broadcaster.unsubscribe(subscriber_id)
                # Clean up if no more subscribers
                if broadcaster.subscriber_count == 0:
                    self._spawn_manager.unsubscribe(spawn_id)
                    task = self._pump_tasks.pop(spawn_id, None)
                    if task is not None:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
                    del self._broadcasters[spawn_id]

    async def _pump_loop(
        self,
        spawn_id: SpawnId,
        queue: asyncio.Queue[HarnessEvent | None],
    ) -> None:
        """Pump events from SpawnManager queue to broadcaster."""
        broadcaster = self._broadcasters.get(spawn_id)
        if broadcaster is None:
            return
        
        try:
            while True:
                event = await queue.get()
                if event is None:
                    broadcaster.broadcast_close()
                    return
                
                # Convert HarnessEvent to SSE-friendly dict
                sse_event: dict[str, object] = {
                    "type": "spawn.event",
                    "spawn_id": str(spawn_id),
                    "event_type": event.event_type,
                    "harness_id": event.harness_id,
                    "payload": event.payload,
                    "timestamp": time.time(),
                }
                broadcaster.broadcast(sse_event)
        except asyncio.CancelledError:
            broadcaster.broadcast_close()
            raise
        finally:
            async with self._lock:
                self._broadcasters.pop(spawn_id, None)
                self._pump_tasks.pop(spawn_id, None)


async def sse_event_generator(
    broadcaster: StreamBroadcaster,
    subscriber_id: int,
    queue: asyncio.Queue[dict[str, object] | None],
    unsubscribe_fn: Callable[[], object],
) -> AsyncIterator[str]:
    """Generate SSE events from a subscriber queue."""
    try:
        while True:
            event = await queue.get()
            if event is None:
                return
            
            # Format as SSE: event type + JSON data
            event_type = str(event.get("type", "message"))
            data = json.dumps(event, separators=(",", ":"))
            yield f"event: {event_type}\ndata: {data}\n\n"
    finally:
        result = unsubscribe_fn()
        if asyncio.iscoroutine(result):
            await result


def register_stream_routes(
    app: object,
    spawn_manager: SpawnManager,
    *,
    state_root: Path,
    multi_sub_manager: SpawnMultiSubscriberManager | None = None,
) -> SpawnMultiSubscriberManager:
    """Register SSE streaming routes on the FastAPI app.
    
    Returns the multi-subscriber manager for use by other routes.
    """
    from importlib import import_module
    
    typed_app = cast("_FastAPIApp", app)
    
    # Create or use provided multi-subscriber manager
    manager = multi_sub_manager or SpawnMultiSubscriberManager(spawn_manager)
    
    try:
        responses_module = import_module("starlette.responses")
        streaming_response_cls = responses_module.StreamingResponse
    except ModuleNotFoundError as exc:
        msg = "Starlette is required for SSE streaming"
        raise RuntimeError(msg) from exc

    async def stream_endpoint() -> object:
        """Multiplexed SSE stream for all spawn updates.
        
        Clients can filter by query params in future, but for now broadcasts all.
        """
        # Create a global broadcast queue for all spawn events
        global_broadcaster = StreamBroadcaster()
        sub_id, queue = await global_broadcaster.subscribe()
        
        async def cleanup() -> None:
            await global_broadcaster.unsubscribe(sub_id)
        
        async def event_generator() -> AsyncIterator[str]:
            # Send initial keepalive
            yield "event: connected\ndata: {}\n\n"
            
            # For now, just send keepalives since we don't have global spawn event subscription yet
            # Full implementation would watch all active spawns
            try:
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        if event is None:
                            return
                        event_type = str(event.get("type", "message"))
                        data = json.dumps(event, separators=(",", ":"))
                        yield f"event: {event_type}\ndata: {data}\n\n"
                    except TimeoutError:
                        # Send keepalive
                        yield "event: keepalive\ndata: {}\n\n"
            finally:
                await cleanup()
        
        return streaming_response_cls(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    typed_app.get("/api/stream")(stream_endpoint)
    
    return manager


__all__ = [
    "SpawnMultiSubscriberManager",
    "StreamBroadcaster",
    "register_stream_routes",
    "sse_event_generator",
]
