"""HTTP-backed bidirectional OpenCode harness connection."""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import socket
import time
from collections.abc import AsyncIterator, Mapping
from io import BufferedWriter
from typing import Any, ClassVar, cast

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    ConnectionNotReady,
    ConnectionState,
    HarnessEvent,
)
from meridian.lib.launch.env import inherit_child_env
from meridian.lib.state.paths import resolve_spawn_log_dir

logger = logging.getLogger(__name__)


class OpenCodeConnection:
    """Bidirectional OpenCode connection over the OpenCode HTTP API."""

    _CAPABILITIES: ClassVar[ConnectionCapabilities] = ConnectionCapabilities(
        mid_turn_injection="http_post",
        supports_steer=False,
        supports_interrupt=True,
        supports_cancel=True,
        runtime_model_switch=False,
        structured_reasoning=True,
    )
    _STATE_TRANSITIONS: ClassVar[dict[ConnectionState, frozenset[ConnectionState]]] = {
        "created": frozenset(("starting", "stopping", "failed")),
        "starting": frozenset(("connected", "stopping", "failed")),
        "connected": frozenset(("stopping", "failed")),
        "stopping": frozenset(("stopped", "failed")),
        "stopped": frozenset(),
        "failed": frozenset(("stopping", "stopped")),
    }
    _HEALTH_PATHS: ClassVar[tuple[str, ...]] = ("/global/health", "/health", "/api/health")
    _CREATE_SESSION_PATHS: ClassVar[tuple[str, ...]] = ("/session", "/sessions")
    _MESSAGE_PATH_TEMPLATES: ClassVar[tuple[str, ...]] = (
        "/session/{session_id}/message",
        "/sessions/{session_id}/message",
    )
    _EVENT_PATHS: ClassVar[tuple[str, ...]] = (
        "/event",
        "/global/event",
        "/session/{session_id}/events",
    )
    _INTERRUPT_PATH_TEMPLATES: ClassVar[tuple[str, ...]] = (
        "/session/{session_id}/abort",
        "/sessions/{session_id}/abort",
        "/session/{session_id}/interrupt",
        "/sessions/{session_id}/interrupt",
        "/session/{session_id}/cancel",
        "/sessions/{session_id}/cancel",
    )
    _CANCEL_PATH_TEMPLATES: ClassVar[tuple[str, ...]] = (
        "/session/{session_id}/abort",
        "/sessions/{session_id}/abort",
        "/session/{session_id}/cancel",
        "/sessions/{session_id}/cancel",
        "/session/{session_id}/stop",
        "/sessions/{session_id}/stop",
    )
    _PATH_RETRY_STATUSES: ClassVar[frozenset[int]] = frozenset((404, 405))
    _PAYLOAD_RETRY_STATUSES: ClassVar[frozenset[int]] = frozenset((400, 415, 422))
    _SUCCESS_STATUSES: ClassVar[frozenset[int]] = frozenset((200, 201, 202, 204))
    _INTERRUPT_SUCCESS_STATUSES: ClassVar[frozenset[int]] = frozenset((200, 201, 202, 204, 409))
    _EVENT_RETRY_DELAY_SECONDS: ClassVar[float] = 0.25
    _STARTUP_TIMEOUT_SECONDS: ClassVar[float] = 30.0
    _STOP_GRACE_SECONDS: ClassVar[float] = 5.0
    _EVENT_ACCEPT_HEADER: ClassVar[dict[str, str]] = {"Accept": "text/event-stream"}

    def __init__(self) -> None:
        self._state: ConnectionState = "created"
        self._spawn_id: SpawnId | None = None
        self._config: ConnectionConfig | None = None
        self._process: asyncio.subprocess.Process | None = None
        self._client: Any | None = None
        self._aiohttp_module: Any | None = None
        self._stderr_handle: BufferedWriter | None = None
        self._base_url: str | None = None
        self._session_id: str | None = None
        self._event_path: str | None = None
        self._last_health_ok = False

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def harness_id(self) -> HarnessId:
        return HarnessId.OPENCODE

    @property
    def spawn_id(self) -> SpawnId:
        if self._spawn_id is None:
            raise RuntimeError("OpenCode connection has not been started")
        return self._spawn_id

    @property
    def capabilities(self) -> ConnectionCapabilities:
        return self._CAPABILITIES

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def subprocess_pid(self) -> int | None:
        process = self._process
        if process is None:
            return None
        return process.pid

    async def start(self, config: ConnectionConfig, params: SpawnParams) -> None:
        if self._state != "created":
            raise RuntimeError(f"Cannot start OpenCode connection from state '{self._state}'")

        self._config = config
        self._spawn_id = config.spawn_id
        self._transition("starting")

        startup_timeout = (
            config.timeout_seconds
            if config.timeout_seconds is not None
            else self._STARTUP_TIMEOUT_SECONDS
        )

        try:
            await self._launch_process(config, params)
            self._session_id = await self._create_session_with_retry(
                config,
                params,
                timeout_seconds=startup_timeout,
            )
            await self._post_session_message(config.prompt)
        except Exception:
            self._set_failed()
            await self._cleanup_runtime()
            raise

        self._transition("connected")
        self._last_health_ok = True

    async def stop(self) -> None:
        if self._state == "stopped":
            return
        if self._state != "stopping":
            self._transition("stopping")

        await self._cleanup_runtime()
        self._transition("stopped")

    def health(self) -> bool:
        if self._state not in {"starting", "connected"}:
            return False
        process_running = self._process is not None and self._process.returncode is None
        return process_running and self._last_health_ok

    async def send_user_message(self, text: str) -> None:
        self._require_connected()
        await self._post_session_message(text)

    async def send_interrupt(self) -> None:
        self._require_connected()
        await self._post_session_action(
            path_templates=self._INTERRUPT_PATH_TEMPLATES,
            payload_variants=(
                {"response": "abort"},
                {"reason": "interrupt"},
                {"type": "interrupt"},
                {},
            ),
            accepted_statuses=self._INTERRUPT_SUCCESS_STATUSES,
        )

    async def send_cancel(self) -> None:
        self._require_connected()
        self._transition("stopping")
        await self._post_session_action(
            path_templates=self._CANCEL_PATH_TEMPLATES,
            payload_variants=(
                {"response": "abort"},
                {"reason": "cancel"},
                {"type": "cancel"},
                {},
            ),
            accepted_statuses=self._INTERRUPT_SUCCESS_STATUSES,
        )

    async def events(self) -> AsyncIterator[HarnessEvent]:
        if self._state not in ("connected", "stopping"):
            return
        if self._session_id is None:
            return

        sse_event_type: str | None = None
        sse_data_lines: list[str] = []

        while self._state in ("connected", "stopping"):
            if self._process_exited():
                self._set_failed()
                return

            try:
                response = await self._open_event_stream()
            except Exception as exc:
                if self._state in ("stopping", "stopped"):
                    return
                if self._process_exited():
                    self._set_failed()
                    return
                logger.warning("OpenCode event stream dropped; reconnecting: %s", exc)
                await asyncio.sleep(self._EVENT_RETRY_DELAY_SECONDS)
                continue

            buffer = ""
            try:
                async for chunk in response.content.iter_chunked(4096):
                    if self._state in ("stopping", "stopped", "failed"):
                        break
                    if not chunk:
                        continue
                    buffer += chunk.decode("utf-8", errors="replace")
                    while True:
                        newline_index = buffer.find("\n")
                        if newline_index < 0:
                            break
                        raw_line = buffer[:newline_index]
                        buffer = buffer[newline_index + 1 :]
                        event, sse_event_type = self._consume_stream_line(
                            raw_line.rstrip("\r"),
                            sse_event_type=sse_event_type,
                            sse_data_lines=sse_data_lines,
                        )
                        if event is not None:
                            yield event

                if buffer.strip():
                    event = self._event_from_json_line(buffer.strip(), raw_text=buffer.strip())
                    if event is not None:
                        yield event
                final_sse_event = self._flush_sse_event(
                    sse_event_type=sse_event_type,
                    sse_data_lines=sse_data_lines,
                )
                if final_sse_event is not None:
                    yield final_sse_event
                sse_event_type = None
            finally:
                response.close()

            if self._state in ("stopping", "stopped", "failed"):
                return
            await asyncio.sleep(self._EVENT_RETRY_DELAY_SECONDS)

    async def _launch_process(self, config: ConnectionConfig, params: SpawnParams) -> None:
        port = _find_free_port()
        self._base_url = f"http://127.0.0.1:{port}"
        command = ["opencode", "serve", "--port", str(port), *params.extra_args]
        env = inherit_child_env(os.environ, config.env_overrides)
        spawn_dir = resolve_spawn_log_dir(config.repo_root, config.spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        self._stderr_handle = (spawn_dir / "stderr.log").open("ab")
        self._process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(config.repo_root),
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=self._stderr_handle,
        )

    async def _create_session_with_retry(
        self,
        config: ConnectionConfig,
        params: SpawnParams,
        *,
        timeout_seconds: float,
    ) -> str:
        deadline = time.monotonic() + max(timeout_seconds, 0.1)
        last_error: Exception | None = None
        while True:
            if self._process_exited():
                raise RuntimeError("OpenCode process exited before becoming healthy")
            try:
                session_id = await self._create_session(config, params)
                self._last_health_ok = True
                return session_id
            except Exception as exc:
                last_error = exc
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"OpenCode session endpoint did not become ready within "
                    f"{timeout_seconds:.1f}s"
                ) from last_error
            await asyncio.sleep(0.2)

    async def _create_session(self, config: ConnectionConfig, params: SpawnParams) -> str:
        payload: dict[str, object] = {}
        if config.model is not None:
            payload["model"] = config.model
            payload["modelID"] = config.model
        if params.agent is not None:
            payload["agent"] = params.agent
        if params.skills:
            payload["skills"] = list(params.skills)
        if params.continue_harness_session_id is not None:
            payload["session_id"] = params.continue_harness_session_id
            payload["continue_session_id"] = params.continue_harness_session_id

        payload_variants: tuple[dict[str, object], ...] = (payload, {}) if payload else ({},)

        last_error: str | None = None
        for path in self._CREATE_SESSION_PATHS:
            for variant in payload_variants:
                status, body = await self._post_json(path, variant)
                if status in self._SUCCESS_STATUSES:
                    session_id = _extract_session_id(body)
                    if session_id is None:
                        detail = _summarize_body(body)
                        if _looks_like_html(detail):
                            last_error = (
                                f"OpenCode session endpoint returned HTML on {path}: "
                                f"status={status}"
                            )
                            break
                        raise RuntimeError(
                            f"OpenCode session creation response missing session id on {path}: "
                            f"{detail}"
                        )
                    return session_id
                if status in self._PAYLOAD_RETRY_STATUSES:
                    last_error = (
                        f"OpenCode session create rejected payload on {path}: "
                        f"status={status} body={_summarize_body(body)}"
                    )
                    continue
                if status in self._PATH_RETRY_STATUSES:
                    last_error = (
                        f"OpenCode session endpoint unavailable on {path}: "
                        f"status={status} body={_summarize_body(body)}"
                    )
                    break
                raise RuntimeError(
                    f"OpenCode session creation failed on {path}: "
                    f"status={status} body={_summarize_body(body)}"
                )

        raise RuntimeError(last_error or "OpenCode session creation failed")

    async def _post_session_message(self, text: str) -> None:
        part_payload: dict[str, object] = {
            "parts": [{"type": "text", "text": text}],
        }
        await self._post_session_action(
            path_templates=self._MESSAGE_PATH_TEMPLATES,
            payload_variants=(
                part_payload,
                {**part_payload, "noReply": False},
                {"text": text},
                {"message": text},
                {"content": text},
            ),
            accepted_statuses=self._SUCCESS_STATUSES,
        )

    async def _post_session_action(
        self,
        *,
        path_templates: tuple[str, ...],
        payload_variants: tuple[dict[str, object], ...],
        accepted_statuses: frozenset[int],
    ) -> None:
        session_id = self._require_session_id()
        last_error: str | None = None

        for template in path_templates:
            path = template.format(session_id=session_id)
            for payload in payload_variants:
                status, body = await self._post_json(path, payload)
                if status in accepted_statuses:
                    if _looks_like_html(_summarize_body(body)):
                        last_error = (
                            f"OpenCode session endpoint returned HTML on {path}: "
                            f"status={status}"
                        )
                        continue
                    return
                if status in self._PAYLOAD_RETRY_STATUSES:
                    last_error = (
                        f"OpenCode session action rejected payload on {path}: "
                        f"status={status} body={_summarize_body(body)}"
                    )
                    continue
                if status in self._PATH_RETRY_STATUSES:
                    last_error = (
                        f"OpenCode session endpoint unavailable on {path}: "
                        f"status={status} body={_summarize_body(body)}"
                    )
                    break
                raise RuntimeError(
                    f"OpenCode session action failed on {path}: "
                    f"status={status} body={_summarize_body(body)}"
                )

        raise RuntimeError(last_error or "OpenCode session action failed")

    async def _post_json(
        self, path: str, payload: Mapping[str, object]
    ) -> tuple[int, object | None]:
        client = await self._ensure_http_client()
        async with client.post(self._url(path), json=dict(payload)) as response:
            status = int(response.status)
            text_body = await response.text()
        parsed_body = _parse_response_body(text_body)
        return status, parsed_body

    async def _open_event_stream(self) -> Any:
        client = await self._ensure_http_client()
        session_id = self._require_session_id()
        paths: list[str] = []
        if self._event_path is not None:
            paths.append(self._event_path)
        for template in self._EVENT_PATHS:
            path = template.format(session_id=session_id)
            if path not in paths:
                paths.append(path)

        last_error: str | None = None
        for path in paths:
            response = await client.get(
                self._url(path),
                headers=self._EVENT_ACCEPT_HEADER,
                timeout=None,
            )
            status = int(response.status)
            if status in self._SUCCESS_STATUSES:
                content_type = str(response.headers.get("Content-Type", "")).lower()
                if "text/html" in content_type:
                    body = await response.text()
                    response.release()
                    last_error = (
                        f"OpenCode event endpoint returned HTML on {path}: "
                        f"status={status} body={_summarize_body(body)}"
                    )
                    continue
                self._event_path = path
                return response

            body = await response.text()
            response.release()

            if status in self._PATH_RETRY_STATUSES:
                last_error = (
                    f"OpenCode event endpoint unavailable on {path}: "
                    f"status={status} body={_summarize_body(body)}"
                )
                continue
            raise RuntimeError(
                f"OpenCode event stream failed on {path}: "
                f"status={status} body={_summarize_body(body)}"
            )

        raise RuntimeError(last_error or "OpenCode event stream endpoint unavailable")

    def _consume_stream_line(
        self,
        line: str,
        *,
        sse_event_type: str | None,
        sse_data_lines: list[str],
    ) -> tuple[HarnessEvent | None, str | None]:
        if not line:
            event = self._flush_sse_event(
                sse_event_type=sse_event_type,
                sse_data_lines=sse_data_lines,
            )
            return event, None

        if line.startswith(":"):
            return None, sse_event_type

        if line.startswith("event:"):
            event_name = line.split(":", maxsplit=1)[1].strip()
            return None, event_name or sse_event_type

        if line.startswith("data:"):
            sse_data_lines.append(line.split(":", maxsplit=1)[1].lstrip())
            return None, sse_event_type

        event = self._event_from_json_line(
            line,
            raw_text=line,
            event_type_hint=sse_event_type,
        )
        return event, sse_event_type

    def _flush_sse_event(
        self,
        *,
        sse_event_type: str | None,
        sse_data_lines: list[str],
    ) -> HarnessEvent | None:
        if not sse_data_lines:
            return None
        payload_text = "\n".join(sse_data_lines)
        sse_data_lines.clear()
        return self._event_from_json_line(
            payload_text,
            raw_text=payload_text,
            event_type_hint=sse_event_type,
        )

    def _event_from_json_line(
        self,
        json_text: str,
        *,
        raw_text: str,
        event_type_hint: str | None = None,
    ) -> HarnessEvent | None:
        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed OpenCode stream line: %s", raw_text)
            return None

        payload: dict[str, object]
        if isinstance(parsed, dict):
            payload = cast("dict[str, object]", parsed)
        else:
            payload = {"value": cast("object", parsed)}

        nested_payload = payload.get("payload")
        if isinstance(nested_payload, dict):
            payload = cast("dict[str, object]", nested_payload)

        raw_event_type = payload.get("type", event_type_hint or "unknown")
        event_type = raw_event_type if isinstance(raw_event_type, str) else "unknown"
        return HarnessEvent(
            event_type=event_type,
            payload=payload,
            harness_id=HarnessId.OPENCODE.value,
            raw_text=raw_text,
        )

    async def _ensure_http_client(self) -> Any:
        if self._client is not None:
            return self._client
        aiohttp = self._ensure_aiohttp()
        timeout = aiohttp.ClientTimeout(total=None)
        self._client = aiohttp.ClientSession(timeout=timeout)
        return self._client

    def _ensure_aiohttp(self) -> Any:
        if self._aiohttp_module is not None:
            return self._aiohttp_module
        self._aiohttp_module = importlib.import_module("aiohttp")
        return self._aiohttp_module

    async def _cleanup_runtime(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            try:
                await client.close()
            except Exception:
                logger.warning("Failed to close OpenCode HTTP client", exc_info=True)

        process = self._process
        self._process = None
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=self._STOP_GRACE_SECONDS)
            except TimeoutError:
                process.kill()
                await process.wait()

        self._base_url = None
        self._session_id = None
        self._event_path = None
        self._last_health_ok = False
        self._close_log_handles()

    def _url(self, path: str) -> str:
        if self._base_url is None:
            raise RuntimeError("OpenCode base URL is not initialized")
        return f"{self._base_url}{path}"

    def _require_session_id(self) -> str:
        if self._session_id is None:
            raise ConnectionNotReady("OpenCode session has not been created yet")
        return self._session_id

    def _require_connected(self) -> None:
        if self._state != "connected":
            raise ConnectionNotReady(
                f"OpenCode connection is not ready (current state: {self._state})"
            )

    def _process_exited(self) -> bool:
        process = self._process
        if process is None:
            return False
        return process.returncode is not None

    def _set_failed(self) -> None:
        if self._state == "failed":
            return
        if self._state == "stopped":
            return
        self._transition("failed")

    def _close_log_handles(self) -> None:
        if self._stderr_handle is not None:
            self._stderr_handle.close()
            self._stderr_handle = None

    def _transition(self, next_state: ConnectionState) -> None:
        if next_state == self._state:
            return
        allowed = self._STATE_TRANSITIONS[self._state]
        if next_state not in allowed:
            raise RuntimeError(f"Invalid OpenCode state transition: {self._state} -> {next_state}")
        self._state = next_state


def _parse_response_body(text_body: str) -> object | None:
    stripped = text_body.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return stripped


def _extract_session_id(body: object | None) -> str | None:
    if body is None:
        return None
    if isinstance(body, str):
        normalized = body.strip()
        return normalized or None
    if isinstance(body, Mapping):
        mapping_body = cast("Mapping[str, object]", body)
        return _extract_session_id_from_mapping(mapping_body)
    return None


def _extract_session_id_from_mapping(data: Mapping[str, object]) -> str | None:
    direct_keys = ("session_id", "sessionId", "sessionID", "id")
    for key in direct_keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested = data.get("session")
    if isinstance(nested, Mapping):
        nested_mapping = cast("Mapping[str, object]", nested)
        for key in direct_keys:
            value = nested_mapping.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _summarize_body(body: object | None) -> str:
    if body is None:
        return "<empty>"
    if isinstance(body, str):
        trimmed = body.strip()
        if not trimmed:
            return "<empty>"
        return trimmed[:200]
    try:
        serialized = json.dumps(body, ensure_ascii=True)
    except TypeError:
        return repr(body)[:200]
    return serialized[:200]


def _looks_like_html(body_summary: str) -> bool:
    normalized = body_summary.strip().lower()
    return normalized.startswith("<!doctype html") or normalized.startswith("<html")
