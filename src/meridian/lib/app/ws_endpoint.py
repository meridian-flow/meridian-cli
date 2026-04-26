"""WebSocket endpoint for streaming one spawn over AG-UI event messages.

This endpoint provides real-time streaming of AG-UI protocol events for a single
spawn, plus bidirectional control. For lifecycle overview across multiple
spawns, use the SSE endpoint at /api/stream instead.

Client Protocol
---------------
- Connect: WS /api/spawns/{spawn_id}/ws
- Server sends: AG-UI events (RunStartedEvent, TextMessageContentEvent, etc.)
- Server sends: keepalive every 30s ({type:keepalive})
- Client responds: pong ({type:pong}) or any control message to stay alive
- Client sends: control messages (user_message, cancel, pong)
- Timeout: 90s without any inbound message closes the connection

Control Messages
----------------
- {"type": "user_message", "text": "..."}  - inject user input
- {"type": "cancel"}                        - request spawn cancellation
- {"type": "pong"}                          - respond to keepalive
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, NotRequired, Protocol, TypedDict, cast

from starlette.websockets import WebSocket

from ag_ui.core import BaseEvent, RunErrorEvent
from meridian.lib.app.agui_mapping import get_agui_mapper
from meridian.lib.app.agui_mapping.base import AGUIMapper
from meridian.lib.app.agui_mapping.extensions import make_capabilities_event
from meridian.lib.app.stream import SpawnMultiSubscriberManager
from meridian.lib.core.spawn_service import SpawnApplicationService
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.streaming.drain_policy import TURN_BOUNDARY_EVENT_TYPE
from meridian.lib.streaming.spawn_manager import SpawnManager

if TYPE_CHECKING:
    from meridian.lib.observability.debug_tracer import DebugTracer


class WebSocketMessage(TypedDict):
    """Minimal receive() payload shape for text/binary WebSocket frames."""

    type: str
    text: NotRequired[str | None]
    bytes: NotRequired[bytes | None]


class WebSocketClient(Protocol):
    """Minimal WebSocket interface used by this module."""

    async def accept(self) -> None: ...

    async def close(self) -> None: ...

    async def send_text(self, data: str) -> None: ...

    async def receive(self) -> WebSocketMessage: ...


WebSocketRouteHandler = Callable[[WebSocket, str], Awaitable[None]]
WebSocketRouteDecorator = Callable[[WebSocketRouteHandler], object]


class FastAPIApp(Protocol):
    """Minimal FastAPI route registration surface for WS endpoints."""

    def websocket(self, path: str) -> WebSocketRouteDecorator: ...

logger = logging.getLogger(__name__)
_ALLOWED_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")
_WS_HEARTBEAT_INTERVAL_SECONDS = 30.0
_WS_HEARTBEAT_TIMEOUT_SECONDS = 90.0
_WS_KEEPALIVE_MESSAGE = '{"type":"keepalive"}'


@dataclass
class _HeartbeatState:
    """Track last pong timestamp for stale WS connection detection."""

    last_pong: float = field(default_factory=time.monotonic)

    def record_pong(self) -> None:
        self.last_pong = time.monotonic()

    def is_stale(self) -> bool:
        return (time.monotonic() - self.last_pong) >= _WS_HEARTBEAT_TIMEOUT_SECONDS




_REPLAY_ACK_TIMEOUT_SECONDS = 10.0


@dataclass
class _ReplayState:
    """Track replay protocol state for Connect-Then-Replay."""

    enabled: bool = False
    ack_future: asyncio.Future[int] = field(
        default_factory=lambda: asyncio.get_event_loop().create_future()
    )


async def spawn_websocket(
    websocket: WebSocketClient,
    spawn_id: str,
    manager: SpawnManager,
    multi_sub_manager: SpawnMultiSubscriberManager | None = None,
    on_user_message: Callable[[], None] | None = None,
    spawn_service: SpawnApplicationService | None = None,
    replay: bool = False,
) -> None:
    """Bridge one active spawn's fan-out stream to one WebSocket client."""

    await websocket.accept()
    typed_spawn_id = SpawnId(spawn_id)

    connection = manager.get_connection(typed_spawn_id)
    if connection is None:
        await _send_error(websocket, f"spawn {spawn_id} not found")
        await websocket.close()
        return

    unsubscribe_fn: Callable[[], Awaitable[None]]
    sub_start_seq: int = -1  # Will be set by multi_sub_manager or computed later

    if multi_sub_manager is not None:
        subscription = await multi_sub_manager.subscribe(typed_spawn_id)
        if subscription is None:
            await _send_error(websocket, f"spawn {spawn_id} not found or unavailable")
            await websocket.close()
            return
        subscriber_id, event_queue, sub_start_seq = subscription

        async def _unsubscribe_multi() -> None:
            await multi_sub_manager.unsubscribe(typed_spawn_id, subscriber_id)

        unsubscribe_fn = _unsubscribe_multi

    else:
        event_queue = manager.subscribe(typed_spawn_id)
        if event_queue is None:
            await _send_error(websocket, "another client is already connected")
            await websocket.close()
            return
        sub_start_seq = manager.get_history_seq(typed_spawn_id)

        async def _unsubscribe_single() -> None:
            manager.unsubscribe(typed_spawn_id)

        unsubscribe_fn = _unsubscribe_single

    mapper = get_agui_mapper(connection.harness_id)
    tracer = manager.get_tracer(typed_spawn_id)

    try:
        # Suppress synthetic RUN_STARTED when replay=True (replay snapshot includes it)
        # Always send capabilities (frontend needs them, not in replay output)
        if not replay:
            await _send_event(websocket, mapper.make_run_started(spawn_id))
        await _send_event(websocket, make_capabilities_event(connection.capabilities))
        heartbeat_state = _HeartbeatState()

        # Create replay state if replay mode is requested
        replay_state = _ReplayState(enabled=replay) if replay else None

        outbound_task = asyncio.create_task(
            _outbound_loop(
                websocket,
                event_queue,
                mapper,
                spawn_id,
                tracer,
                heartbeat_state=heartbeat_state,
                replay_state=replay_state,
                sub_start_seq=sub_start_seq,
            )
        )
        inbound_task = asyncio.create_task(
            _inbound_loop(
                websocket,
                typed_spawn_id,
                manager,
                tracer,
                heartbeat_state=heartbeat_state,
                on_user_message=on_user_message,
                spawn_service=spawn_service,
                replay_state=replay_state,
            )
        )

        done, pending = await asyncio.wait(
            {outbound_task, inbound_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        for task in done:
            with suppress(asyncio.CancelledError):
                try:
                    await task
                except Exception as exc:
                    if not _is_websocket_disconnect(exc):
                        logger.debug("WebSocket loop exited with error", exc_info=True)
    finally:
        await unsubscribe_fn()


async def _outbound_loop(
    websocket: WebSocketClient,
    event_queue: asyncio.Queue[HarnessEvent | None],
    mapper: AGUIMapper,
    spawn_id: str,
    tracer: DebugTracer | None = None,
    heartbeat_state: _HeartbeatState | None = None,
    replay_state: _ReplayState | None = None,
    sub_start_seq: int = -1,
) -> None:
    error_emitted = False
    turn_active = True  # RunStarted is emitted by spawn_websocket (unless replay=True).

    # Handle replay mode: wait for replay_ack, then skip already-delivered events
    skip_count = 0
    events_skipped = 0
    if replay_state is not None and replay_state.enabled:
        try:
            cursor = await asyncio.wait_for(
                asyncio.shield(replay_state.ack_future),
                timeout=_REPLAY_ACK_TIMEOUT_SECONDS,
            )
            # Compute how many queue events overlap with the replay snapshot
            # skip_count = cursor - (sub_start_seq + 1)
            # cursor = total history lines at fetch time
            # sub_start_seq = last history line at subscription time (-1 if none)
            skip_count = max(0, cursor - (sub_start_seq + 1))
        except TimeoutError:
            # No ack received — fall back to sending all events
            skip_count = 0
        # In replay mode, the RUN_STARTED was already in the replay snapshot
        # so we start with turn_active=True but no need to re-emit RUN_STARTED

    while True:
        try:
            event = await asyncio.wait_for(
                event_queue.get(),
                timeout=_WS_HEARTBEAT_INTERVAL_SECONDS,
            )
        except TimeoutError:
            await websocket.send_text(_WS_KEEPALIVE_MESSAGE)
            if tracer is not None:
                tracer.emit(
                    "websocket",
                    "ws_send",
                    direction="outbound",
                    data={"event_type": "keepalive"},
                )
            if heartbeat_state is not None and heartbeat_state.is_stale():
                logger.debug(
                    "WebSocket heartbeat timeout, closing stale connection",
                    extra={"spawn_id": spawn_id},
                )
                with suppress(Exception):
                    await websocket.close()
                return
            continue
        # Terminal sentinel always terminates, even during skip phase (EARS-R008a)
        if event is None:
            if turn_active and not error_emitted:
                await _send_event(websocket, mapper.make_run_finished(spawn_id))
            return

        # Skip events already delivered via replay snapshot (EARS-R007, EARS-R008)
        if events_skipped < skip_count:
            events_skipped += 1
            # Track turn state for skipped events (EARS-R008b)
            if event.event_type == TURN_BOUNDARY_EVENT_TYPE:
                turn_active = False
                error_emitted = False
            elif not turn_active:
                turn_active = True  # Would have emitted RUN_STARTED
            continue

        if event.event_type == TURN_BOUNDARY_EVENT_TYPE:
            if turn_active and not error_emitted:
                await _send_event(websocket, mapper.make_run_finished(spawn_id))
            turn_active = False
            error_emitted = False
            continue

        if not turn_active:
            await _send_event(websocket, mapper.make_run_started(spawn_id))
            turn_active = True

        if tracer is not None:
            tracer.emit(
                "mapper",
                "translate_input",
                direction="inbound",
                data={"event_type": event.event_type, "harness_id": event.harness_id},
            )
        translated_events = list(mapper.translate(event))
        if tracer is not None:
            tracer.emit(
                "mapper",
                "translate_output",
                data={
                    "input_event_type": event.event_type,
                    "output_count": len(translated_events),
                },
            )
        for translated in translated_events:
            await _send_event(websocket, translated)
            if tracer is not None:
                tracer.emit(
                    "websocket",
                    "ws_send",
                    direction="outbound",
                    data={"event_type": getattr(translated, "type", "unknown")},
                )
            if getattr(translated, "type", None) == "RUN_ERROR":
                error_emitted = True


async def _inbound_loop(
    websocket: WebSocketClient,
    spawn_id: SpawnId,
    manager: SpawnManager,
    tracer: DebugTracer | None = None,
    heartbeat_state: _HeartbeatState | None = None,
    on_user_message: Callable[[], None] | None = None,
    spawn_service: SpawnApplicationService | None = None,
    replay_state: _ReplayState | None = None,
) -> None:
    while True:
        message = await websocket.receive()
        frame_type = message.get("type")
        if frame_type == "websocket.disconnect":
            return

        if frame_type != "websocket.receive":
            continue

        raw_text = message.get("text")
        if raw_text is None:
            frame_bytes = message.get("bytes")
            if frame_bytes is None:
                continue
            try:
                raw_text = frame_bytes.decode("utf-8")
            except UnicodeDecodeError:
                await _send_error(websocket, "control frame bytes must be UTF-8")
                continue

        if tracer is not None:
            tracer.emit(
                "websocket", "ws_recv", direction="inbound",
                data={"raw_text": raw_text},
            )

        payload = _decode_json_object(raw_text)
        if payload is None:
            await _send_error(websocket, "control message must be a JSON object")
            continue

        message_type = payload.get("type")
        if not isinstance(message_type, str):
            await _send_error(websocket, "control message missing type")
            continue

        if tracer is not None:
            tracer.emit(
                "websocket", "control_dispatch", direction="inbound",
                data={"message_type": message_type},
            )

        # Any valid control message refreshes heartbeat liveness.
        if heartbeat_state is not None:
            heartbeat_state.record_pong()

        if message_type == "pong":
            continue

        if message_type == "replay_ack":
            # Handle replay acknowledgment with cursor position
            cursor = payload.get("cursor")
            if not isinstance(cursor, int) or cursor < 0:
                await _send_error(websocket, "replay_ack requires non-negative integer cursor")
                continue
            if replay_state is not None and not replay_state.ack_future.done():
                replay_state.ack_future.set_result(cursor)
            continue

        if message_type == "user_message":
            text = payload.get("text")
            if not isinstance(text, str):
                await _send_error(websocket, "user_message requires text")
                continue
            result = await manager.inject(spawn_id, message=text, source="app_ws")
            if result.success and on_user_message is not None:
                on_user_message()
        elif message_type == "cancel":
            if spawn_service is None:
                await _send_error(websocket, "cancel service unavailable")
                continue
            try:
                outcome = await spawn_service.cancel(spawn_id)
            except ValueError as exc:
                await _send_error(websocket, str(exc))
                continue
            if outcome.already_terminal:
                await _send_error(websocket, f"spawn already terminal: {outcome.status}")
            elif outcome.finalizing:
                await _send_error(websocket, "spawn is finalizing")
            continue
        else:
            await _send_error(websocket, f"unsupported control message type: {message_type}")
            continue

        if not result.success:
            await _send_error(websocket, result.error or "control message failed")


def _decode_json_object(raw_text: str) -> dict[str, object] | None:
    try:
        payload: object = json.loads(raw_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, Mapping):
        return None
    return {str(key): value for key, value in cast("Mapping[object, object]", payload).items()}


async def _send_error(websocket: WebSocketClient, message: str) -> None:
    await _send_event(websocket, RunErrorEvent(message=message))


async def _send_event(websocket: WebSocketClient, event: BaseEvent) -> None:
    await websocket.send_text(event.model_dump_json(by_alias=True, exclude_none=True))


def _is_websocket_disconnect(exc: BaseException) -> bool:
    return exc.__class__.__name__ == "WebSocketDisconnect"


def register_ws_routes(
    app: object,
    manager: SpawnManager,
    *,
    multi_sub_manager: SpawnMultiSubscriberManager | None = None,
    validate_spawn_id: Callable[[str], SpawnId] | None = None,
    extra_origins: list[str] | None = None,
    on_user_message: Callable[[], None] | None = None,
    spawn_service: SpawnApplicationService | None = None,
) -> None:
    """Register WebSocket routes for app streaming APIs."""

    typed_app = cast("FastAPIApp", app)
    allowed_origins_set: frozenset[str] = frozenset(extra_origins) if extra_origins else frozenset()

    async def _spawn_ws_route(websocket: WebSocket, spawn_id: str) -> None:
        origin = websocket.headers.get("origin")
        if (
            origin is not None
            and not _ALLOWED_ORIGIN_RE.match(origin)
            and origin not in allowed_origins_set
        ):
            await websocket.close(code=4403)
            return

        # Extract ?replay=1 query parameter (EARS-R006, EARS-R009)
        replay_param = websocket.query_params.get("replay", "")
        replay = replay_param == "1" or replay_param.lower() == "true"

        typed_websocket = cast("WebSocketClient", websocket)
        try:
            typed_spawn_id = (
                validate_spawn_id(spawn_id) if validate_spawn_id is not None else SpawnId(spawn_id)
            )
        except Exception as exc:
            if _is_websocket_disconnect(exc):
                logger.debug("WebSocket disconnected", extra={"spawn_id": spawn_id})
                return
            detail = getattr(exc, "detail", None)
            if isinstance(detail, str):
                await typed_websocket.accept()
                await _send_error(typed_websocket, detail)
                await typed_websocket.close()
                return
            raise
        try:
            await spawn_websocket(
                typed_websocket,
                str(typed_spawn_id),
                manager,
                multi_sub_manager=multi_sub_manager,
                on_user_message=on_user_message,
                spawn_service=spawn_service,
                replay=replay,
            )
        except Exception as exc:
            if _is_websocket_disconnect(exc):
                logger.debug("WebSocket disconnected", extra={"spawn_id": spawn_id})
                return
            raise

    typed_app.websocket("/api/spawns/{spawn_id}/ws")(_spawn_ws_route)


__all__ = ["register_ws_routes", "spawn_websocket"]
