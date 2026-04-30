"""FastAPI transport surface for the headless chat backend."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from meridian.lib.chat.backend_acquisition import BackendAcquisition
from meridian.lib.chat.command_handler import ChatCommandHandler
from meridian.lib.chat.commands import ChatCommand, CommandResult
from meridian.lib.chat.event_log import ChatEventLog
from meridian.lib.chat.event_pipeline import ChatEventPipeline
from meridian.lib.chat.protocol import CHAT_EXITED, CHAT_STARTED, ChatEvent, utc_now_iso
from meridian.lib.chat.replay import ReplayService
from meridian.lib.chat.session_service import ChatSessionService
from meridian.lib.chat.ws_fanout import WebSocketFanOut
from meridian.lib.state.paths import RuntimePaths
from meridian.lib.state.user_paths import get_user_home


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    recover_chats()
    for pipeline in _state.pipelines.values():
        pipeline.start()
    yield


app = FastAPI(lifespan=lifespan)


class CreateChatRequest(BaseModel):
    model: str | None = None
    harness: str | None = None


class CreateChatResponse(BaseModel):
    chat_id: str
    state: str


class PromptRequest(BaseModel):
    text: str


class StateResponse(BaseModel):
    chat_id: str
    state: str


class ErrorResponse(BaseModel):
    detail: str


class _UnavailableAcquisition:
    async def acquire(self, chat_id: str, initial_prompt: str):  # type: ignore[no-untyped-def]
        _ = (chat_id, initial_prompt)
        raise RuntimeError("chat backend acquisition is not configured")


class ChatServerState:
    def __init__(self, runtime_root: Path, backend_acquisition: BackendAcquisition) -> None:
        self.runtime_root = runtime_root
        self.paths = RuntimePaths.from_root_dir(runtime_root)
        self.backend_acquisition = backend_acquisition
        self.sessions: dict[str, ChatSessionService] = {}
        self.event_logs: dict[str, ChatEventLog] = {}
        self.fanouts: dict[str, WebSocketFanOut] = {}
        self.pipelines: dict[str, ChatEventPipeline] = {}

    @property
    def handler(self) -> ChatCommandHandler:
        return ChatCommandHandler(self.sessions, self.pipelines)


_state = ChatServerState(get_user_home(), _UnavailableAcquisition())


def configure(
    *,
    runtime_root: Path | None = None,
    backend_acquisition: BackendAcquisition | None = None,
) -> None:
    """Configure process-local chat server dependencies."""

    global _state
    _state = ChatServerState(
        runtime_root or get_user_home(),
        backend_acquisition or _UnavailableAcquisition(),
    )
    recover_chats()


def recover_chats() -> None:
    """Rebuild in-memory registry from persisted chat event logs."""

    chats_dir = _state.paths.chats_dir
    if not chats_dir.exists():
        return
    for history_path in chats_dir.glob("*/history.jsonl"):
        chat_id = history_path.parent.name
        if chat_id in _state.event_logs:
            continue
        event_log = ChatEventLog(history_path)
        events = list(event_log.read_all())
        if not events:
            continue
        _state.event_logs[chat_id] = event_log
        if any(event.type == CHAT_EXITED for event in events):
            continue
        session = ChatSessionService(chat_id, _state.backend_acquisition)
        _state.sessions[chat_id] = session
        fanout = WebSocketFanOut()
        _state.fanouts[chat_id] = fanout
        pipeline = ChatEventPipeline(chat_id, event_log, session, fanout=fanout)
        _start_pipeline_if_running_loop(pipeline)
        _state.pipelines[chat_id] = pipeline
        last_state = _state_from_events(events)
        if last_state in {"active", "draining"}:
            _ = event_log.append(
                ChatEvent(
                    type="runtime.error",
                    seq=0,
                    chat_id=chat_id,
                    execution_id=_last_execution_id(events),
                    timestamp=utc_now_iso(),
                    payload={"reason": "backend_lost_after_restart"},
                )
            )


@app.post("/chat", response_model=CreateChatResponse)
async def create_chat(body: CreateChatRequest) -> CreateChatResponse:
    _ = body
    chat_id = f"c-{uuid4().hex}"
    event_log = ChatEventLog(_state.paths.chat_history_path(chat_id))
    session = ChatSessionService(chat_id, _state.backend_acquisition)
    fanout = WebSocketFanOut()
    pipeline = ChatEventPipeline(chat_id, event_log, session, fanout=fanout)
    pipeline.start()

    _state.event_logs[chat_id] = event_log
    _state.sessions[chat_id] = session
    _state.fanouts[chat_id] = fanout
    _state.pipelines[chat_id] = pipeline

    await pipeline.ingest(
        ChatEvent(
            type=CHAT_STARTED,
            seq=0,
            chat_id=chat_id,
            execution_id="",
            timestamp=utc_now_iso(),
        )
    )
    await pipeline.drain()
    return CreateChatResponse(chat_id=chat_id, state=session.state)


@app.post("/chat/{chat_id}/msg", response_model=CommandResult)
async def prompt_chat(chat_id: str, body: PromptRequest) -> CommandResult:
    return await _dispatch_rest(chat_id, "prompt", {"text": body.text})


@app.post("/chat/{chat_id}/cancel", response_model=CommandResult)
async def cancel_chat(chat_id: str) -> CommandResult:
    return await _dispatch_rest(chat_id, "cancel", {})


@app.post("/chat/{chat_id}/close", response_model=CommandResult)
async def close_chat(chat_id: str) -> CommandResult:
    result = await _dispatch_rest(chat_id, "close", {})
    if result.status == "accepted":
        pipeline = _state.pipelines.get(chat_id)
        if pipeline is not None:
            await pipeline.drain()
        _state.fanouts.pop(chat_id, None)
    return result


@app.get("/chat/{chat_id}/state", response_model=StateResponse)
async def get_chat_state(chat_id: str) -> StateResponse:
    session = _state.sessions.get(chat_id)
    if session is not None:
        return StateResponse(chat_id=chat_id, state=session.state)
    event_log = _state.event_logs.get(chat_id) or _load_event_log(chat_id)
    if event_log is None:
        raise HTTPException(status_code=404, detail="chat_not_found")
    events = list(event_log.read_all())
    if any(event.type == CHAT_EXITED for event in events):
        return StateResponse(chat_id=chat_id, state="closed")
    return StateResponse(chat_id=chat_id, state="idle")


@app.websocket("/ws/chat/{chat_id}")
async def ws_chat(websocket: WebSocket, chat_id: str) -> None:
    await websocket.accept()
    event_log = _state.event_logs.get(chat_id) or _load_event_log(chat_id)
    if event_log is None:
        await websocket.close(code=4004, reason="chat_not_found")
        return
    send_lock = asyncio.Lock()
    fanout = _state.fanouts.get(chat_id)
    last_seq = _parse_last_seq(websocket)
    replay = ReplayService(event_log, fanout, send_lock)

    async def outbound() -> None:
        await replay.connect(websocket, last_seq)

    async def inbound() -> None:
        while True:
            try:
                raw_obj = await websocket.receive_json()
            except WebSocketDisconnect:
                return
            except ValueError:
                await websocket.close(code=1003, reason="invalid_json")
                return
            if not isinstance(raw_obj, dict) or "command_type" not in raw_obj:
                continue
            raw_mapping = cast("dict[object, object]", raw_obj)
            raw: dict[str, object] = {str(key): value for key, value in raw_mapping.items()}
            ack = await _handle_ws_command(raw, chat_id)
            async with send_lock:
                await websocket.send_json(ack)

    outbound_task = asyncio.create_task(outbound())
    inbound_task = asyncio.create_task(inbound())
    done, pending = await asyncio.wait(
        {outbound_task, inbound_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for task in done:
        with suppress(WebSocketDisconnect):
            task.result()
    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def _dispatch_rest(chat_id: str, command_type: str, payload: dict[str, Any]) -> CommandResult:
    command = ChatCommand(
        type=command_type,
        command_id=str(uuid4()),
        chat_id=chat_id,
        timestamp=utc_now_iso(),
        payload=payload,
    )
    return await _state.handler.dispatch(command)


async def _handle_ws_command(raw: dict[str, object], path_chat_id: str) -> dict[str, str]:
    command_id = str(raw.get("command_id") or "unknown")
    try:
        command = _parse_chat_command(raw, path_chat_id)
    except ValueError as exc:
        return {"ack": command_id, "status": "rejected", "error": str(exc)}
    result = await _state.handler.dispatch(command)
    payload = {"ack": command.command_id, "status": result.status}
    if result.error is not None:
        payload["error"] = result.error
    return payload


def _parse_chat_command(raw: dict[str, object], path_chat_id: str) -> ChatCommand:
    command_type = raw.get("command_type")
    command_id = raw.get("command_id")
    chat_id = raw.get("chat_id", path_chat_id)
    timestamp = raw.get("timestamp", utc_now_iso())
    payload = raw.get("payload", {})
    if not isinstance(command_type, str) or not command_type:
        raise ValueError("invalid_command:missing_command_type")
    if not isinstance(command_id, str) or not command_id:
        raise ValueError("invalid_command:missing_command_id")
    if chat_id != path_chat_id or not isinstance(chat_id, str):
        raise ValueError("invalid_command:chat_id_mismatch")
    if not isinstance(timestamp, str):
        raise ValueError("invalid_command:invalid_timestamp")
    if not isinstance(payload, dict):
        raise ValueError("invalid_command:payload_not_object")
    return ChatCommand(
        type=command_type,
        command_id=command_id,
        chat_id=chat_id,
        timestamp=timestamp,
        payload={str(key): value for key, value in cast("dict[object, object]", payload).items()},
    )


def _load_event_log(chat_id: str) -> ChatEventLog | None:
    path = _state.paths.chat_history_path(chat_id)
    if not path.exists():
        return None
    event_log = ChatEventLog(path)
    _state.event_logs[chat_id] = event_log
    return event_log


def _parse_last_seq(websocket: WebSocket) -> int | None:
    raw = websocket.query_params.get("last_seq")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _state_from_events(events: list[ChatEvent]) -> str:
    state = "idle"
    for event in events:
        if event.type == "turn.started":
            state = "active"
        elif event.type == "turn.completed":
            state = "idle"
        elif event.type == CHAT_EXITED:
            state = "closed"
    return state


def _last_execution_id(events: list[ChatEvent]) -> str:
    for event in reversed(events):
        if event.execution_id:
            return event.execution_id
    return ""


__all__ = ["app", "configure", "recover_chats"]


def _start_pipeline_if_running_loop(pipeline: ChatEventPipeline) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    pipeline.start()
