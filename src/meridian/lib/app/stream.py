"""SSE streaming endpoint for multiplexed spawn and work updates.

Streaming Architecture
----------------------
Meridian has two streaming paths:

**SSE (/api/stream)** - Low-rate lifecycle events
- Spawn lifecycle (created, started, finalized, terminated)
- Work item status changes
- Multi-spawn overview for dashboard/list views
- Read-only; no bidirectional control
- Uses StreamBroadcaster for app-global event fan-out

**WebSocket (/api/spawns/{id}/ws)** - High-rate per-spawn events
- Real-time AG-UI protocol events (messages, tool calls, results)
- Bidirectional control (user_message, interrupt, cancel)
- Single-spawn focus for chat/detail views
- Uses SpawnMultiSubscriberManager for per-spawn fan-out

When adding new streaming features:
- Lifecycle/status events -> SSE
- Interactive spawn events -> WebSocket
- High-volume kernel output -> WebSocket (per-spawn fan-out)
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from pathlib import Path
from typing import Generic, Protocol, TypeVar, cast

from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.streaming.spawn_manager import SpawnManager

_T = TypeVar("_T")


class _FastAPIAppState(Protocol):
    stream_broadcaster: StreamBroadcaster


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    state: _FastAPIAppState

    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...


class BroadcastHub(Generic[_T]):
    """Generic multi-subscriber broadcast primitive.

    Manages multiple asyncio.Queue subscribers and broadcasts events to all
    of them with backpressure handling (drops oldest on full queues).
    Thread-safe through asyncio primitives.

    Used as the fan-out mechanism for both SSE lifecycle events
    (``BroadcastHub[dict[str, object]]``) and per-spawn harness event
    streams (``BroadcastHub[HarnessEvent]``).
    """

    def __init__(self, maxsize: int = 1000) -> None:
        self._subscribers: dict[int, asyncio.Queue[_T | None]] = {}
        self._next_id = 0
        self._lock = asyncio.Lock()
        self._maxsize = maxsize

    async def subscribe(self) -> tuple[int, asyncio.Queue[_T | None]]:
        """Create a new subscriber queue and return (subscriber_id, queue)."""
        async with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            queue: asyncio.Queue[_T | None] = asyncio.Queue(maxsize=self._maxsize)
            self._subscribers[sub_id] = queue
            return sub_id, queue

    async def unsubscribe(self, subscriber_id: int) -> None:
        """Remove a subscriber."""
        async with self._lock:
            self._subscribers.pop(subscriber_id, None)

    def broadcast(self, event: _T) -> None:
        """Send event to all subscribers, dropping oldest if queue is full."""
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


# SSE lifecycle events use dict payloads.
StreamBroadcaster = BroadcastHub[dict[str, object]]


class SpawnMultiSubscriberManager:
    """Wraps SpawnManager to support multiple subscribers per spawn.
    
    SpawnManager's native subscribe() only allows one subscriber per spawn.
    This manager creates a single subscription to SpawnManager and broadcasts
    raw HarnessEvent objects to multiple subscribers.
    """

    def __init__(self, spawn_manager: SpawnManager) -> None:
        self._spawn_manager = spawn_manager
        self._broadcasters: dict[SpawnId, BroadcastHub[HarnessEvent]] = {}
        self._pump_tasks: dict[SpawnId, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(
        self, spawn_id: SpawnId
    ) -> tuple[int, asyncio.Queue[HarnessEvent | None]] | None:
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
                broadcaster: BroadcastHub[HarnessEvent] = BroadcastHub()
                self._broadcasters[spawn_id] = broadcaster
                self._pump_tasks[spawn_id] = asyncio.create_task(
                    self._pump_loop(spawn_id, queue)
                )
            
            return await self._broadcasters[spawn_id].subscribe()

    async def unsubscribe(self, spawn_id: SpawnId, subscriber_id: int) -> None:
        """Unsubscribe from spawn events."""
        pump_task: asyncio.Task[None] | None = None

        async with self._lock:
            broadcaster = self._broadcasters.get(spawn_id)
            if broadcaster is not None:
                await broadcaster.unsubscribe(subscriber_id)
                # Clean up if no more subscribers
                if broadcaster.subscriber_count == 0:
                    self._spawn_manager.unsubscribe(spawn_id)
                    self._broadcasters.pop(spawn_id, None)
                    pump_task = self._pump_tasks.pop(spawn_id, None)
                    if pump_task is not None:
                        pump_task.cancel()

        # Never await the pump while holding self._lock:
        # _pump_loop() also acquires this lock in its finally block.
        if pump_task is not None:
            with suppress(asyncio.CancelledError):
                await pump_task

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
                broadcaster.broadcast(event)
        except asyncio.CancelledError:
            broadcaster.broadcast_close()
            raise
        finally:
            async with self._lock:
                # Only the currently-registered pump may clear state.
                # This prevents a canceled old pump from clobbering a newer
                # broadcaster/task installed by a concurrent re-subscribe.
                if self._pump_tasks.get(spawn_id) is asyncio.current_task():
                    self._broadcasters.pop(spawn_id, None)
                    self._pump_tasks.pop(spawn_id, None)


async def sse_event_generator(
    broadcaster: StreamBroadcaster,
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


def get_or_create_stream_broadcaster(app: object) -> StreamBroadcaster:
    """Return app-global SSE broadcaster, creating it on first access."""
    typed_app = cast("_FastAPIApp", app)
    existing = getattr(typed_app.state, "stream_broadcaster", None)
    if isinstance(existing, BroadcastHub):
        return cast("StreamBroadcaster", existing)
    broadcaster: StreamBroadcaster = BroadcastHub()
    typed_app.state.stream_broadcaster = broadcaster
    return broadcaster


def broadcast_stream_event(
    app: object,
    event_type: str,
    payload: dict[str, object] | None = None,
) -> None:
    """Broadcast one app event to all SSE subscribers."""
    event: dict[str, object] = {
        "type": event_type,
        "timestamp": time.time(),
    }
    if payload:
        event.update(payload)
    get_or_create_stream_broadcaster(app).broadcast(event)


def register_stream_routes(
    app: object,
    spawn_manager: SpawnManager,
    *,
    runtime_root: Path,
    multi_sub_manager: SpawnMultiSubscriberManager | None = None,
) -> StreamBroadcaster:
    """Register SSE streaming route for app-global lifecycle events.

    Returns the app-global StreamBroadcaster for event fan-out.

    Note: The multi_sub_manager, spawn_manager, and runtime_root parameters are
    accepted for API consistency but not used by SSE routes. Per-spawn streaming
    uses WebSocket endpoints registered separately via register_ws_routes().
    """
    from importlib import import_module
    
    typed_app = cast("_FastAPIApp", app)

    _ = multi_sub_manager
    _ = spawn_manager
    _ = runtime_root
    global_broadcaster = get_or_create_stream_broadcaster(app)
    
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
        sub_id, queue = await global_broadcaster.subscribe()

        async def cleanup() -> None:
            await global_broadcaster.unsubscribe(sub_id)
        
        async def event_generator() -> AsyncIterator[str]:
            # Send initial keepalive
            yield "event: connected\ndata: {}\n\n"

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

    return global_broadcaster


__all__ = [
    "BroadcastHub",
    "SpawnMultiSubscriberManager",
    "StreamBroadcaster",
    "broadcast_stream_event",
    "get_or_create_stream_broadcaster",
    "register_stream_routes",
    "sse_event_generator",
]
