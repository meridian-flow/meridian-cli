"""WebSocket endpoint for streaming one spawn over AG-UI event messages."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from typing import TYPE_CHECKING, NotRequired, Protocol, TypedDict, cast

from starlette.websockets import WebSocket

from ag_ui.core import BaseEvent, RunErrorEvent
from meridian.lib.app.agui_mapping import get_agui_mapper
from meridian.lib.app.agui_mapping.base import AGUIMapper
from meridian.lib.app.agui_mapping.extensions import make_capabilities_event
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.streaming.signal_canceller import SignalCanceller
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


async def spawn_websocket(websocket: WebSocketClient, spawn_id: str, manager: SpawnManager) -> None:
    """Bridge one active spawn's fan-out stream to one WebSocket client."""

    await websocket.accept()

    connection = manager.get_connection(SpawnId(spawn_id))
    if connection is None:
        await _send_error(websocket, f"spawn {spawn_id} not found")
        await websocket.close()
        return

    event_queue = manager.subscribe(SpawnId(spawn_id))
    if event_queue is None:
        await _send_error(websocket, "another client is already connected")
        await websocket.close()
        return

    mapper = get_agui_mapper(connection.harness_id)
    tracer = manager.get_tracer(SpawnId(spawn_id))

    try:
        await _send_event(websocket, mapper.make_run_started(spawn_id))
        await _send_event(websocket, make_capabilities_event(connection.capabilities))

        outbound_task = asyncio.create_task(
            _outbound_loop(websocket, event_queue, mapper, spawn_id, tracer)
        )
        inbound_task = asyncio.create_task(
            _inbound_loop(websocket, SpawnId(spawn_id), manager, tracer)
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
        manager.unsubscribe(SpawnId(spawn_id))


async def _outbound_loop(
    websocket: WebSocketClient,
    event_queue: asyncio.Queue[HarnessEvent | None],
    mapper: AGUIMapper,
    spawn_id: str,
    tracer: DebugTracer | None = None,
) -> None:
    error_emitted = False
    while True:
        event = await event_queue.get()
        if event is None:
            if not error_emitted:
                await _send_event(websocket, mapper.make_run_finished(spawn_id))
            return

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

        if message_type == "user_message":
            text = payload.get("text")
            if not isinstance(text, str):
                await _send_error(websocket, "user_message requires text")
                continue
            result = await manager.inject(spawn_id, message=text, source="app_ws")
        elif message_type == "interrupt":
            result = await manager.interrupt(spawn_id, source="app_ws")
        elif message_type == "cancel":
            try:
                outcome = await SignalCanceller(
                    state_root=manager.state_root,
                    manager=manager,
                ).cancel(spawn_id)
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
    validate_spawn_id: Callable[[str], SpawnId] | None = None,
) -> None:
    """Register WebSocket routes for app streaming APIs."""

    typed_app = cast("FastAPIApp", app)

    async def _spawn_ws_route(websocket: WebSocket, spawn_id: str) -> None:
        origin = websocket.headers.get("origin")
        if origin is not None and not _ALLOWED_ORIGIN_RE.match(origin):
            await websocket.close(code=4403)
            return

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
            await spawn_websocket(typed_websocket, str(typed_spawn_id), manager)
        except Exception as exc:
            if _is_websocket_disconnect(exc):
                logger.debug("WebSocket disconnected", extra={"spawn_id": spawn_id})
                return
            raise

    typed_app.websocket("/api/spawns/{spawn_id}/ws")(_spawn_ws_route)


__all__ = ["register_ws_routes", "spawn_websocket"]
