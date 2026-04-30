"""FastAPI transport surface for the headless chat backend."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict

from meridian.lib.chat.commands import ChatCommand, CommandResult
from meridian.lib.chat.protocol import utc_now_iso
from meridian.lib.chat.replay import ReplayService
from meridian.lib.chat.runtime import ChatRuntime
from meridian.lib.state.user_paths import get_user_home

if TYPE_CHECKING:
    from meridian.lib.chat.backend_acquisition import BackendAcquisition


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await _runtime.start()
    try:
        yield
    finally:
        await _runtime.stop()


app = FastAPI(lifespan=lifespan)


class CreateChatRequest(BaseModel):
    """Create-chat transport shape."""

    model_config = ConfigDict(extra="forbid")


class CreateChatResponse(BaseModel):
    chat_id: str
    state: str


class PromptRequest(BaseModel):
    text: str


class ApprovalRequest(BaseModel):
    request_id: str
    decision: str
    payload: dict[str, object] | None = None


class InputRequest(BaseModel):
    request_id: str
    answers: dict[str, object]


class RevertRequest(BaseModel):
    commit_sha: str


class StateResponse(BaseModel):
    chat_id: str
    state: str


class _UnavailableAcquisition:
    async def acquire(
        self,
        chat_id: str,
        initial_prompt: str,
        *,
        execution_generation: int = 0,
    ):
        _ = (chat_id, initial_prompt, execution_generation)
        raise RuntimeError("chat backend acquisition is not configured")


_runtime = ChatRuntime(
    runtime_root=get_user_home(),
    project_root=Path.cwd(),
    backend_acquisition=_UnavailableAcquisition(),
)


def configure(
    *,
    runtime: ChatRuntime | None = None,
    runtime_root: Path | None = None,
    backend_acquisition: BackendAcquisition | None = None,
    project_root: Path | None = None,
) -> None:
    """Configure process-local chat server dependencies."""

    global _runtime
    if runtime is not None:
        _runtime = runtime
        return
    _runtime = ChatRuntime(
        runtime_root=runtime_root or get_user_home(),
        project_root=project_root or Path.cwd(),
        backend_acquisition=backend_acquisition or _UnavailableAcquisition(),
    )


@app.post("/chat", response_model=CreateChatResponse)
async def create_chat(body: CreateChatRequest) -> CreateChatResponse:
    _ = body
    view = await _runtime.create_chat()
    return CreateChatResponse(chat_id=view.chat_id, state=view.state)


@app.post("/chat/{chat_id}/msg", response_model=CommandResult)
async def prompt_chat(chat_id: str, body: PromptRequest) -> CommandResult:
    return await _dispatch_rest(chat_id, "prompt", {"text": body.text})


@app.post("/chat/{chat_id}/cancel", response_model=CommandResult)
async def cancel_chat(chat_id: str) -> CommandResult:
    return await _dispatch_rest(chat_id, "cancel", {})


@app.post("/chat/{chat_id}/approve", response_model=CommandResult)
async def approve_request(chat_id: str, body: ApprovalRequest) -> CommandResult:
    payload: dict[str, Any] = {"request_id": body.request_id, "decision": body.decision}
    if body.payload is not None:
        payload["payload"] = body.payload
    return await _dispatch_rest(chat_id, "approve", payload)


@app.post("/chat/{chat_id}/input", response_model=CommandResult)
async def answer_input(chat_id: str, body: InputRequest) -> CommandResult:
    return await _dispatch_rest(
        chat_id, "answer_input", {"request_id": body.request_id, "answers": body.answers}
    )


@app.post("/chat/{chat_id}/revert", response_model=CommandResult)
async def revert_checkpoint(chat_id: str, body: RevertRequest) -> CommandResult:
    return await _dispatch_rest(chat_id, "revert", {"commit_sha": body.commit_sha})


@app.post("/chat/{chat_id}/close", response_model=CommandResult)
async def close_chat(chat_id: str) -> CommandResult:
    return await _dispatch_rest(chat_id, "close", {})


@app.get("/chat/{chat_id}/state", response_model=StateResponse)
async def get_chat_state(chat_id: str) -> StateResponse:
    state = _runtime.get_state(chat_id)
    if state is not None:
        return StateResponse(chat_id=chat_id, state=state)
    raise HTTPException(status_code=404, detail="chat_not_found")


@app.websocket("/ws/chat/{chat_id}")
async def ws_chat(websocket: WebSocket, chat_id: str) -> None:
    await websocket.accept()
    stream_source = _runtime.get_stream_source(chat_id)
    if stream_source is None:
        await websocket.close(code=4004, reason="chat_not_found")
        return
    send_lock = asyncio.Lock()
    last_seq = _parse_last_seq(websocket)
    replay = ReplayService(stream_source.event_log, stream_source.fanout, send_lock)

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
    return await _runtime.dispatch(command)


async def _handle_ws_command(raw: dict[str, object], path_chat_id: str) -> dict[str, str]:
    command_id = str(raw.get("command_id") or "unknown")
    try:
        command = _parse_chat_command(raw, path_chat_id)
    except ValueError as exc:
        return {"ack": command_id, "status": "rejected", "error": str(exc)}
    result = await _runtime.dispatch(command)
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


def _parse_last_seq(websocket: WebSocket) -> int | None:
    raw = websocket.query_params.get("last_seq")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


__all__ = ["app", "configure"]
