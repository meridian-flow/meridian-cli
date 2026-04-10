"""Bidirectional Codex websocket connection adapter."""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import importlib.util
import json
import os
import socket
from asyncio.subprocess import Process
from collections.abc import AsyncIterator
from io import BufferedWriter
from typing import TYPE_CHECKING, Any, Final, cast

if TYPE_CHECKING:
    from meridian.lib.observability.debug_tracer import DebugTracer

from aiohttp import ClientSession, WSMsgType

from meridian import __version__
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    ConnectionNotReady,
    ConnectionState,
    HarnessConnection,
    HarnessEvent,
)
from meridian.lib.harness.launch_spec import ResolvedLaunchSpec
from meridian.lib.launch.env import inherit_child_env
from meridian.lib.observability.trace_helpers import (
    trace_parse_error,
    trace_state_change,
    trace_wire_send,
)
from meridian.lib.state.paths import resolve_spawn_log_dir

_MAX_INITIAL_PROMPT_BYTES = 50 * 1024
_DEFAULT_CONNECT_TIMEOUT_SECONDS = 10.0
_DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
_STOP_WAIT_TIMEOUT_SECONDS = 5.0


def _load_websockets_module() -> Any | None:
    if importlib.util.find_spec("websockets") is None:
        return None
    return importlib.import_module("websockets")


_WEBSOCKETS_MODULE: Any | None = _load_websockets_module()


def _ws_is_open(ws: object) -> bool:
    """Handle websockets state checks across API versions."""
    state = getattr(ws, "state", None)
    if state is not None:
        state_name = getattr(state, "name", None)
        if isinstance(state_name, str):
            return state_name == "OPEN"

        state_value = getattr(state, "value", None)
        if isinstance(state_value, int):
            return state_value == 1

        if isinstance(state, int):
            return state == 1

    closed = getattr(ws, "closed", None)
    if isinstance(closed, bool):
        return not closed

    return False


class _AiohttpWebSocketCompat:
    """Compatibility layer matching the subset of the websockets API we use."""

    def __init__(self, session: ClientSession, ws: Any) -> None:
        self._session = session
        self._ws = ws

    @property
    def closed(self) -> bool:
        return bool(self._ws.closed)

    async def send(self, data: str) -> None:
        await self._ws.send_str(data)

    async def close(self) -> None:
        with contextlib.suppress(Exception):
            await self._ws.close()
        await self._session.close()

    def __aiter__(self) -> _AiohttpWebSocketCompat:
        return self

    async def __anext__(self) -> str | bytes:
        while True:
            message = await self._ws.receive()
            msg_type = message.type
            if msg_type is WSMsgType.TEXT:
                return cast("str", message.data)
            if msg_type is WSMsgType.BINARY:
                return cast("bytes", message.data)
            if msg_type in {WSMsgType.CLOSE, WSMsgType.CLOSED}:
                raise StopAsyncIteration
            if msg_type is WSMsgType.ERROR:
                raise RuntimeError("Aiohttp websocket reported an error")


async def _aiohttp_connect(ws_url: str) -> _AiohttpWebSocketCompat:
    session = ClientSession()
    try:
        ws = await session.ws_connect(ws_url)
    except Exception:
        await session.close()
        raise
    return _AiohttpWebSocketCompat(session, ws)


class CodexConnection(HarnessConnection):
    """JSON-RPC 2.0 bridge between Meridian and Codex app-server."""

    _ALLOWED_TRANSITIONS: Final[dict[ConnectionState, set[ConnectionState]]] = {
        "created": {"starting", "stopping", "stopped", "failed"},
        "starting": {"connected", "stopping", "stopped", "failed"},
        "connected": {"stopping", "failed"},
        "stopping": {"stopped", "failed"},
        "failed": {"stopped"},
        "stopped": set(),
    }

    def __init__(self) -> None:
        self._state: ConnectionState = "created"
        self._spawn_id: SpawnId = SpawnId("")
        self._config: ConnectionConfig | None = None

        self._process: Process | None = None
        self._ws: Any | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._send_lock = asyncio.Lock()
        self._stderr_handle: BufferedWriter | None = None

        self._next_request_id = 1
        self._pending_requests: dict[int, asyncio.Future[dict[str, object]]] = {}
        self._event_queue: asyncio.Queue[HarnessEvent | None] = asyncio.Queue()

        self._current_turn_id: str | None = None
        self._thread_id: str | None = None
        self._tracer: DebugTracer | None = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def harness_id(self) -> HarnessId:
        return HarnessId.CODEX

    @property
    def spawn_id(self) -> SpawnId:
        return self._spawn_id

    @property
    def capabilities(self) -> ConnectionCapabilities:
        return ConnectionCapabilities(
            mid_turn_injection="interrupt_restart",
            supports_steer=True,
            supports_interrupt=True,
            supports_cancel=True,
            runtime_model_switch=False,
            structured_reasoning=True,
        )

    @property
    def session_id(self) -> str | None:
        return self._thread_id

    @property
    def subprocess_pid(self) -> int | None:
        process = self._process
        if process is None:
            return None
        return process.pid

    async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
        if self._state not in {"created", "stopped", "failed"}:
            raise RuntimeError(f"Cannot start CodexConnection from state '{self._state}'")

        self._transition("starting")
        self._spawn_id = config.spawn_id
        self._tracer = config.debug_tracer
        self._config = config
        self._next_request_id = 1
        self._pending_requests = {}
        self._event_queue = asyncio.Queue()
        self._current_turn_id = None
        self._thread_id = None

        host = config.ws_bind_host
        port = config.ws_port if config.ws_port > 0 else _reserve_port(host)
        ws_url = f"ws://{host}:{port}"

        env = inherit_child_env(os.environ, config.env_overrides)
        spawn_dir = resolve_spawn_log_dir(config.repo_root, config.spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        self._stderr_handle = (spawn_dir / "stderr.log").open("ab")

        try:
            self._process = await asyncio.create_subprocess_exec(
                "codex",
                "app-server",
                "--listen",
                ws_url,
                *spec.extra_args,
                cwd=str(config.repo_root),
                env=env,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=self._stderr_handle,
            )

            self._ws = await self._connect_with_retry(
                ws_url,
                timeout_seconds=self._connect_timeout(),
            )
            self._reader_task = asyncio.create_task(self._read_messages_loop())

            await self._request(
                "initialize",
                {
                    "capabilities": {},
                    "clientInfo": {
                        "name": "meridian",
                        "version": __version__,
                    },
                },
                timeout_seconds=self._connect_timeout(),
            )
            await self._notify("initialized")

            thread_result = await self._bootstrap_thread(config, spec)
            self._thread_id = _extract_thread_id(thread_result)

            initial_prompt = _truncate_utf8(config.prompt, _MAX_INITIAL_PROMPT_BYTES)
            if initial_prompt != config.prompt:
                await self._event_queue.put(
                    HarnessEvent(
                        event_type="warning/promptTruncated",
                        payload={
                            "maxBytes": _MAX_INITIAL_PROMPT_BYTES,
                            "originalBytes": len(config.prompt.encode("utf-8")),
                            "truncatedBytes": len(initial_prompt.encode("utf-8")),
                        },
                        harness_id=self.harness_id.value,
                        raw_text=None,
                    )
                )

            await self._request(
                "turn/start",
                {
                    "threadId": self._require_thread_id("turn/start"),
                    "input": _build_text_user_input(initial_prompt),
                },
            )

            self._transition("connected")
        except Exception:
            self._transition("failed")
            await self._cleanup_resources(mark_stopped=False)
            raise

    async def stop(self) -> None:
        if self._state in {"stopped"}:
            return

        if self._state != "failed":
            self._transition("stopping")

        await self._cleanup_resources(mark_stopped=self._state != "failed")

    def health(self) -> bool:
        process_running = self._process is not None and self._process.returncode is None
        ws_open = self._ws is not None and _ws_is_open(self._ws)
        return self._state == "connected" and process_running and ws_open

    async def send_user_message(self, text: str) -> None:
        self._require_connected("send_user_message")

        if self._current_turn_id:
            await self._request(
                "turn/steer",
                {
                    "threadId": self._require_thread_id("turn/steer"),
                    "input": _build_text_user_input(text),
                    "expectedTurnId": self._current_turn_id,
                },
            )
            return

        await self._request(
            "turn/start",
            {
                "threadId": self._require_thread_id("turn/start"),
                "input": _build_text_user_input(text),
            },
        )

    async def send_interrupt(self) -> None:
        self._require_connected("send_interrupt")

        if not self._current_turn_id:
            return

        await self._request(
            "turn/interrupt",
            {
                "threadId": self._require_thread_id("turn/interrupt"),
                "turnId": self._current_turn_id,
            },
        )

    async def send_cancel(self) -> None:
        self._require_connected("send_cancel")

        self._transition("stopping")
        await self._close_ws()

    async def events(self) -> AsyncIterator[HarnessEvent]:
        while True:
            event = await self._event_queue.get()
            if event is None:
                return
            yield event

    async def _connect_with_retry(self, ws_url: str, timeout_seconds: float) -> Any:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds
        last_error: Exception | None = None

        while loop.time() < deadline:
            if self._process is not None and self._process.returncode is not None:
                raise RuntimeError(
                    "Codex app-server exited before websocket connect "
                    f"(exit={self._process.returncode})"
                )

            try:
                if _WEBSOCKETS_MODULE is not None:
                    return await _WEBSOCKETS_MODULE.connect(ws_url)
                return await _aiohttp_connect(ws_url)
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(0.1)

        raise TimeoutError(f"Timed out connecting to Codex websocket at {ws_url}") from last_error

    async def _request(
        self,
        method: str,
        params: dict[str, object] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        request_id = self._next_request_id
        self._next_request_id += 1

        ws = self._ws
        if ws is None:
            raise RuntimeError("Codex websocket is not connected")

        payload: dict[str, object] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        loop = asyncio.get_running_loop()
        response_future: asyncio.Future[dict[str, object]] = loop.create_future()
        self._pending_requests[request_id] = response_future

        trace_wire_send(
            self._tracer,
            "ws_send_request",
            json.dumps(payload),
            method=method,
            request_id=request_id,
        )
        try:
            await self._send_json(payload)
            response = await asyncio.wait_for(
                response_future,
                timeout=timeout_seconds or _DEFAULT_REQUEST_TIMEOUT_SECONDS,
            )
        finally:
            self._pending_requests.pop(request_id, None)

        error_obj = response.get("error")
        if isinstance(error_obj, dict):
            error_payload = cast("dict[str, object]", error_obj)
            code = error_payload.get("code")
            message = error_payload.get("message")
            raise RuntimeError(f"Codex JSON-RPC error for {method}: code={code} message={message}")

        result_obj = response.get("result")
        result = cast("dict[str, object]", result_obj) if isinstance(result_obj, dict) else {}
        self._update_turn_state(method=method, payload=result)
        return result

    async def _notify(self, method: str, params: dict[str, object] | None = None) -> None:
        ws = self._ws
        if ws is None:
            raise RuntimeError("Codex websocket is not connected")

        payload: dict[str, object] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            payload["params"] = params
        trace_wire_send(self._tracer, "ws_send_notify", json.dumps(payload), method=method)
        await self._send_json(payload)

    async def _read_messages_loop(self) -> None:
        ws = self._ws
        if ws is None:
            return

        try:
            async for raw_message in ws:
                raw_text = _coerce_text(raw_message)
                if self._tracer is not None:
                    self._tracer.emit(
                        "wire", "ws_recv", direction="inbound",
                        data={"raw_text": raw_text, "bytes": len(raw_text.encode("utf-8"))},
                    )
                parsed = _parse_jsonrpc(raw_text)
                if parsed is None:
                    trace_parse_error(self._tracer, "codex", raw_text, error="malformed_json_rpc")
                    continue

                method = parsed.get("method")
                if "id" in parsed and isinstance(method, str):
                    await self._handle_server_request(parsed)
                    continue

                if "id" in parsed:
                    response_id = _coerce_int(parsed.get("id"))
                    if response_id is None:
                        continue
                    if self._tracer is not None:
                        self._tracer.emit(
                            "wire", "ws_recv_response", direction="inbound",
                            data={"request_id": response_id, "has_error": "error" in parsed},
                        )
                    future = self._pending_requests.get(response_id)
                    if future is not None and not future.done():
                        future.set_result(parsed)
                    continue

                if not isinstance(method, str):
                    continue

                if self._tracer is not None:
                    self._tracer.emit(
                        "wire", "ws_recv_notification", direction="inbound",
                        data={"method": method},
                    )

                params_obj = parsed.get("params")
                payload = (
                    cast("dict[str, object]", params_obj)
                    if isinstance(params_obj, dict)
                    else {}
                )
                self._update_turn_state(method=method, payload=payload)

                await self._event_queue.put(
                    HarnessEvent(
                        event_type=method,
                        payload=payload,
                        harness_id=self.harness_id.value,
                        raw_text=raw_text,
                    )
                )
        except Exception as exc:
            if self._state in {"starting", "connected"}:
                self._transition("failed")
                await self._event_queue.put(
                    HarnessEvent(
                        event_type="error/connectionClosed",
                        payload={"message": str(exc)},
                        harness_id=self.harness_id.value,
                        raw_text=None,
                    )
                )
        finally:
            self._fail_pending_requests(RuntimeError("Codex websocket closed"))
            await self._event_queue.put(None)

    async def _cleanup_resources(self, *, mark_stopped: bool) -> None:
        await self._close_ws()

        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None

        process = self._process
        if process is not None:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=_STOP_WAIT_TIMEOUT_SECONDS)
                except TimeoutError:
                    process.kill()
                    await process.wait()
            self._process = None

        self._fail_pending_requests(RuntimeError("Codex connection stopped"))
        self._current_turn_id = None
        self._thread_id = None
        self._close_log_handles()

        if mark_stopped:
            self._transition("stopped")
            await self._event_queue.put(None)

    async def _close_ws(self) -> None:
        ws = self._ws
        if ws is None:
            return

        self._ws = None
        with contextlib.suppress(Exception):
            await ws.close()

    async def _send_json(self, payload: dict[str, object]) -> None:
        ws = self._ws
        if ws is None:
            raise RuntimeError("Codex websocket is not connected")
        async with self._send_lock:
            await ws.send(json.dumps(payload))

    async def _send_jsonrpc_result(self, request_id: object, result: dict[str, object]) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }
        trace_wire_send(
            self._tracer,
            "ws_send_result",
            json.dumps(payload),
            request_id=request_id,
        )
        await self._send_json(payload)

    async def _send_jsonrpc_error(
        self,
        request_id: object,
        *,
        code: int,
        message: str,
    ) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": code,
                "message": message,
            },
        }
        trace_wire_send(
            self._tracer,
            "ws_send_error",
            json.dumps(payload),
            request_id=request_id,
            error_code=code,
        )
        await self._send_json(payload)

    async def _handle_server_request(self, message: dict[str, object]) -> None:
        request_id = message.get("id")
        method = message.get("method")
        params_obj = message.get("params")
        payload = cast("dict[str, object]", params_obj) if isinstance(params_obj, dict) else {}

        if not isinstance(method, str):
            return

        if self._tracer is not None:
            self._tracer.emit(
                "wire",
                "ws_recv_server_request",
                direction="inbound",
                data={"method": method},
            )

        if method == "item/commandExecution/requestApproval":
            await self._send_jsonrpc_result(request_id, {"decision": "accept"})
            return

        if method == "item/fileChange/requestApproval":
            await self._send_jsonrpc_result(request_id, {"decision": "accept"})
            return

        if method == "item/tool/requestUserInput":
            await self._send_jsonrpc_result(request_id, {"answers": {}})
            return

        await self._event_queue.put(
            HarnessEvent(
                event_type="warning/unsupportedServerRequest",
                payload={"method": method, "params": payload},
                harness_id=self.harness_id.value,
                raw_text=None,
            )
        )
        await self._send_jsonrpc_error(
            request_id,
            code=-32601,
            message=f"Meridian codex_ws adapter does not support server request '{method}'",
        )

    def _fail_pending_requests(self, error: Exception) -> None:
        for request_id in list(self._pending_requests.keys()):
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.set_exception(error)

    def _close_log_handles(self) -> None:
        if self._stderr_handle is not None:
            self._stderr_handle.close()
            self._stderr_handle = None

    def _transition(self, next_state: ConnectionState) -> None:
        """Validate and apply a state transition."""
        if next_state == self._state:
            return
        allowed = self._ALLOWED_TRANSITIONS.get(self._state, set())
        if next_state not in allowed:
            raise RuntimeError(
                f"Invalid CodexConnection transition: {self._state!r} -> {next_state!r}"
            )
        trace_state_change(self._tracer, "codex", self._state, next_state)
        self._state = next_state

    def _require_connected(self, operation: str) -> None:
        if self._state != "connected":
            raise ConnectionNotReady(
                f"Codex connection is not connected; cannot {operation} from state '{self._state}'"
            )

    def _require_thread_id(self, operation: str) -> str:
        thread_id = self._thread_id
        if thread_id is None:
            raise RuntimeError(f"Codex thread ID is unavailable; cannot {operation}")
        return thread_id

    def _connect_timeout(self) -> float:
        timeout_seconds = self._config.timeout_seconds if self._config is not None else None
        if timeout_seconds is not None and timeout_seconds > 0:
            return timeout_seconds
        return _DEFAULT_CONNECT_TIMEOUT_SECONDS

    async def _bootstrap_thread(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> dict[str, object]:
        method, payload = self._thread_bootstrap_request(config, spec)
        return await self._request(method, payload)

    def _thread_bootstrap_request(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> tuple[str, dict[str, object]]:
        payload: dict[str, object] = {"cwd": str(config.repo_root)}
        if config.model:
            payload["model"] = config.model

        resume_thread_id = (spec.continue_session_id or "").strip()
        if not resume_thread_id:
            return ("thread/start", payload)

        payload["threadId"] = resume_thread_id
        if spec.continue_fork:
            return ("thread/fork", payload)
        return ("thread/resume", payload)

    def _update_turn_state(self, *, method: str, payload: dict[str, object]) -> None:
        if method == "turn/completed":
            self._current_turn_id = None
            return

        if method in {"thread/start", "thread/started"}:
            thread_id = _extract_thread_id(payload)
            if thread_id is not None:
                self._thread_id = thread_id

        turn_id = _extract_turn_id(payload)
        if turn_id is not None:
            self._current_turn_id = turn_id


def _reserve_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _coerce_text(raw_message: object) -> str:
    if isinstance(raw_message, bytes):
        return raw_message.decode("utf-8", errors="replace")
    return str(raw_message)


def _build_text_user_input(text: str) -> list[dict[str, str]]:
    return [{"type": "text", "text": text}]


def _extract_thread_id(payload: dict[str, object]) -> str | None:
    thread_id = _extract_str(payload, "threadId")
    if thread_id is not None:
        return thread_id
    thread_obj = payload.get("thread")
    if isinstance(thread_obj, dict):
        return _extract_str(cast("dict[str, object]", thread_obj), "id")
    return None


def _extract_turn_id(payload: dict[str, object]) -> str | None:
    turn_id = _extract_str(payload, "turnId")
    if turn_id is not None:
        return turn_id
    turn_obj = payload.get("turn")
    if isinstance(turn_obj, dict):
        return _extract_str(cast("dict[str, object]", turn_obj), "id")
    return None


def _parse_jsonrpc(raw_text: str) -> dict[str, object] | None:
    try:
        parsed_obj = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_obj, dict):
        return None
    return cast("dict[str, object]", parsed_obj)


def _coerce_int(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _extract_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


__all__ = ["CodexConnection"]
