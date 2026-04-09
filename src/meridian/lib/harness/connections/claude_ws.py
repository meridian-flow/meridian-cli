"""Claude bidirectional connection adapter via local WebSocket server."""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import signal
import socket
from asyncio.subprocess import PIPE, Process
from collections.abc import AsyncIterator, Sequence
from io import BufferedWriter
from typing import Any, Final, Protocol, cast

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    ConnectionNotReady,
    ConnectionState,
    HarnessConnection,
    HarnessEvent,
)
from meridian.lib.state.paths import resolve_spawn_log_dir

logger = logging.getLogger(__name__)

_DEFAULT_CONNECT_TIMEOUT_SECONDS: Final[float] = 30.0
_PROCESS_KILL_GRACE_SECONDS: Final[float] = 10.0
_VERSION_CHECK_TIMEOUT_SECONDS: Final[float] = 5.0
_TESTED_VERSION_PREFIXES: Final[tuple[str, ...]] = ("1.",)
_NORMAL_CLOSE_CODES: Final[set[int]] = {1000, 1001}
_HARNESS_NAME: Final[str] = HarnessId.CLAUDE.value

_websockets_module_cache: Any | None = None


class _WsTransport(Protocol):
    closed: bool

    async def recv(self) -> str | bytes: ...

    async def send(self, message: str) -> None: ...

    async def close(self, *, code: int | None = None, reason: str | None = None) -> None: ...

    async def wait_closed(self) -> None: ...


class _WsServer(Protocol):
    sockets: Sequence[socket.socket] | None

    def close(self) -> None: ...

    async def wait_closed(self) -> None: ...


def _websockets_module() -> Any:
    global _websockets_module_cache
    if _websockets_module_cache is not None:
        return _websockets_module_cache

    try:
        _websockets_module_cache = importlib.import_module("websockets")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "The `websockets` package is required for bidirectional harness connections."
        ) from exc
    return _websockets_module_cache


class ClaudeConnection(HarnessConnection):
    """Bidirectional Claude harness connection over one local WebSocket."""

    _CAPABILITIES = ConnectionCapabilities(
        mid_turn_injection="queue",
        supports_steer=False,
        supports_interrupt=True,
        supports_cancel=True,
        runtime_model_switch=False,
        structured_reasoning=True,
    )
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
        self._server: _WsServer | None = None
        self._ws: _WsTransport | None = None
        self._process: Process | None = None
        self._send_lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        self._accept_lock = asyncio.Lock()
        self._connected_event = asyncio.Event()
        self._stdout_handle: BufferedWriter | None = None
        self._stderr_handle: BufferedWriter | None = None
        self._protocol_validated = False
        self._event_stream_started = False

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def harness_id(self) -> HarnessId:
        return HarnessId.CLAUDE

    @property
    def spawn_id(self) -> SpawnId:
        return self._spawn_id

    @property
    def capabilities(self) -> ConnectionCapabilities:
        return self._CAPABILITIES

    async def start(self, config: ConnectionConfig) -> None:
        """Start WS server, launch Claude subprocess, and send initial user prompt."""

        if self._state != "created":
            raise RuntimeError(f"Connection can only start from 'created', got '{self._state}'")

        self._config = config
        self._spawn_id = config.spawn_id
        self._set_state("starting")

        try:
            await self._check_claude_version()
            await self._start_server(config)
            port = self._resolve_server_port()
            await self._start_subprocess(config, port)
            await self._wait_for_initial_connection(config.timeout_seconds)
            await self._send_json({"type": "user", "content": config.prompt})
            self._set_state("connected")
        except Exception:
            self._mark_failed("Claude connection startup failed.")
            await self._cleanup_resources(terminate_process=True)
            raise

    async def stop(self) -> None:
        """Stop WS transport and subprocess. Safe to call multiple times."""

        async with self._stop_lock:
            if self._state == "stopped":
                return

            if self._state not in {"stopping", "failed"}:
                self._set_state("stopping")

            await self._cleanup_resources(terminate_process=True)
            self._set_state("stopped")

    def health(self) -> bool:
        return self._state == "connected"

    async def send_user_message(self, text: str) -> None:
        self._ensure_connected()
        await self._send_json({"type": "user", "content": text})

    async def send_interrupt(self) -> None:
        self._ensure_connected()
        await self._send_json({"type": "interrupt"})

    async def send_cancel(self) -> None:
        self._ensure_connected()
        self._set_state("stopping")
        try:
            await self._send_json({"type": "cancel"})
        except Exception:
            await self._signal_process(signal.SIGINT)
            raise

    async def events(self) -> AsyncIterator[HarnessEvent]:
        ws = self._ws
        if ws is None:
            return
        if self._event_stream_started:
            raise RuntimeError("events() iterator already consumed")
        self._event_stream_started = True

        process_wait: asyncio.Task[int] | None = None
        if self._process is not None:
            process_wait = asyncio.create_task(self._process.wait())

        try:
            while True:
                recv_task: asyncio.Task[str | bytes] = asyncio.create_task(ws.recv())
                wait_targets: set[asyncio.Task[Any]] = {recv_task}
                if process_wait is not None:
                    wait_targets.add(cast("asyncio.Task[Any]", process_wait))

                done, _ = await asyncio.wait(wait_targets, return_when=asyncio.FIRST_COMPLETED)

                if process_wait is not None and process_wait in done:
                    recv_task.cancel()
                    return_code = process_wait.result()
                    if return_code != 0 and self._state not in {"stopping", "stopped"}:
                        detail = f"Claude subprocess exited unexpectedly with code {return_code}."
                        self._mark_failed(detail)
                        yield self._error_event(detail)
                    return

                try:
                    raw_message = recv_task.result()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    if self._is_ws_close_exception(exc):
                        if not self._is_normal_close(exc) and self._state not in {
                            "stopping",
                            "stopped",
                        }:
                            detail = self._close_detail(exc)
                            self._mark_failed(detail)
                            yield self._error_event(detail)
                        return

                    if self._state not in {"stopping", "stopped"}:
                        detail = f"Failed to read Claude WebSocket event: {exc}"
                        self._mark_failed(detail)
                        yield self._error_event(detail)
                    return

                raw_text = (
                    raw_message.decode("utf-8", errors="replace")
                    if isinstance(raw_message, bytes)
                    else raw_message
                )

                parsed_events = self._parse_ndjson_message(raw_text)
                if not self._protocol_validated:
                    if not parsed_events:
                        detail = (
                            "Protocol mismatch: first Claude message did not contain "
                            "valid typed JSON."
                        )
                        self._mark_failed(detail)
                        yield self._error_event(detail, raw_text=raw_text)
                        return
                    self._protocol_validated = True

                for event in parsed_events:
                    yield event
        finally:
            if process_wait is not None:
                process_wait.cancel()

    def _ensure_connected(self) -> None:
        if self._state != "connected":
            raise ConnectionNotReady(
                f"Claude connection is not ready (state={self._state}); expected 'connected'."
            )

    def _set_state(self, next_state: ConnectionState) -> None:
        if next_state == self._state:
            return
        allowed = self._ALLOWED_TRANSITIONS[self._state]
        if next_state not in allowed:
            raise RuntimeError(
                "Invalid connection state transition: "
                f"{self._state} -> {next_state}"
            )
        self._state = next_state

    def _mark_failed(self, reason: str) -> None:
        if self._state not in {"failed", "stopped"}:
            try:
                self._set_state("failed")
            except RuntimeError:
                logger.exception("Failed to transition Claude connection into failed state")
        logger.warning("Claude connection failed: %s", reason)

    async def _check_claude_version(self) -> None:
        try:
            process = await asyncio.create_subprocess_exec(
                "claude",
                "--version",
                stdout=PIPE,
                stderr=PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=_VERSION_CHECK_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.warning("Timed out while checking Claude CLI version.")
            return
        except OSError:
            logger.warning("Could not execute `claude --version`; skipping version gate.")
            return

        output = (stdout + stderr).decode("utf-8", errors="ignore").strip()
        version = self._extract_semver(output)
        if version is None:
            logger.warning("Unknown Claude version output: %s", output or "<empty>")
            return
        if not version.startswith(_TESTED_VERSION_PREFIXES):
            logger.warning(
                "Claude version may be untested for bidirectional sdk-url protocol: %s",
                version,
            )

    @staticmethod
    def _extract_semver(text: str) -> str | None:
        for token in text.split():
            parts = token.strip().split(".")
            if len(parts) < 2:
                continue
            if all(part.isdigit() for part in parts[:2]):
                return token.strip()
        return None

    async def _start_server(self, config: ConnectionConfig) -> None:
        self._connected_event.clear()
        websockets_module = _websockets_module()
        server_obj = await websockets_module.serve(
            self._accept_connection,
            config.ws_bind_host,
            config.ws_port,
        )
        self._server = cast("_WsServer", server_obj)

    def _resolve_server_port(self) -> int:
        if self._server is None or not self._server.sockets:
            raise RuntimeError("Claude WebSocket server did not expose a listening socket.")
        socket_address = self._server.sockets[0].getsockname()
        return int(socket_address[1])

    async def _start_subprocess(self, config: ConnectionConfig, port: int) -> None:
        spawn_dir = resolve_spawn_log_dir(config.repo_root, config.spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)

        stdout_path = spawn_dir / "output.jsonl"
        stderr_path = spawn_dir / "stderr.log"
        self._stdout_handle = stdout_path.open("ab")
        self._stderr_handle = stderr_path.open("ab")

        command = [
            "claude",
            "--sdk-url",
            f"ws://{config.ws_bind_host}:{port}",
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        if config.model:
            command.extend(["--model", config.model])
        if config.extra_args:
            command.extend(config.extra_args)

        env = os.environ.copy()
        env.update(config.env_overrides)

        self._process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(config.repo_root),
            env=env,
            stdout=self._stdout_handle,
            stderr=self._stderr_handle,
        )

    async def _wait_for_initial_connection(self, timeout_seconds: float | None) -> None:
        timeout = (
            timeout_seconds
            if timeout_seconds is not None and timeout_seconds > 0
            else _DEFAULT_CONNECT_TIMEOUT_SECONDS
        )
        process = self._process
        if process is None:
            raise RuntimeError("Claude subprocess was not started.")

        connect_wait = asyncio.create_task(self._connected_event.wait())
        process_wait = asyncio.create_task(process.wait())
        try:
            done, _pending = await asyncio.wait(
                {connect_wait, process_wait},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not done:
                raise TimeoutError(
                    f"Timed out waiting {timeout:.1f}s for Claude WebSocket connection."
                )

            if process_wait in done:
                return_code = process_wait.result()
                raise RuntimeError(
                    "Claude subprocess exited before establishing WebSocket "
                    f"connection (exit={return_code})."
                )

            await connect_wait
        finally:
            connect_wait.cancel()
            process_wait.cancel()

    async def _accept_connection(self, websocket: _WsTransport) -> None:
        async with self._accept_lock:
            if self._ws is not None and not self._ws.closed:
                await websocket.close(code=1013, reason="Connection already active")
                return
            self._ws = websocket
            self._connected_event.set()
        await websocket.wait_closed()

    async def _send_json(self, payload: dict[str, object]) -> None:
        ws = self._ws
        if ws is None or ws.closed:
            raise ConnectionNotReady("Claude WebSocket is not connected.")

        wire_payload = json.dumps(payload, separators=(",", ":"))
        async with self._send_lock:
            await ws.send(wire_payload)

    async def _signal_process(self, sig: signal.Signals) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        process.send_signal(sig)

    async def _cleanup_resources(self, *, terminate_process: bool) -> None:
        ws = self._ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                logger.debug("Failed closing Claude WebSocket connection", exc_info=True)
            self._ws = None

        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                logger.debug("Failed closing Claude WebSocket server", exc_info=True)
            self._server = None

        if terminate_process:
            await self._terminate_process()

        self._close_log_handles()

    async def _terminate_process(self) -> None:
        process = self._process
        if process is None:
            return
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=_PROCESS_KILL_GRACE_SECONDS)
            except TimeoutError:
                process.kill()
                await process.wait()
        self._process = None

    def _close_log_handles(self) -> None:
        if self._stdout_handle is not None:
            self._stdout_handle.close()
            self._stdout_handle = None
        if self._stderr_handle is not None:
            self._stderr_handle.close()
            self._stderr_handle = None

    def _parse_ndjson_message(self, raw_text: str) -> list[HarnessEvent]:
        events: list[HarnessEvent] = []
        for line in raw_text.splitlines():
            payload_text = line.strip()
            if not payload_text:
                continue
            try:
                payload_obj = json.loads(payload_text)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed Claude WS message line: %s", payload_text)
                continue
            if not isinstance(payload_obj, dict):
                logger.warning("Skipping non-object Claude WS message line: %s", payload_text)
                continue

            payload = cast("dict[str, object]", payload_obj)
            event_type = payload.get("type")
            if not isinstance(event_type, str) or not event_type.strip():
                logger.warning(
                    "Skipping Claude WS message without string 'type': %s",
                    payload_text,
                )
                continue

            events.append(
                HarnessEvent(
                    event_type=event_type,
                    payload=payload,
                    harness_id=_HARNESS_NAME,
                    raw_text=raw_text,
                )
            )
        return events

    @staticmethod
    def _is_ws_close_exception(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        class_name = exc.__class__.__name__.lower()
        return isinstance(code, int) or "connectionclosed" in class_name

    @staticmethod
    def _is_normal_close(exc: Exception) -> bool:
        code = getattr(exc, "code", None)
        return isinstance(code, int) and code in _NORMAL_CLOSE_CODES

    @staticmethod
    def _close_detail(exc: Exception) -> str:
        code = getattr(exc, "code", "?")
        reason = getattr(exc, "reason", "")
        return f"WebSocket closed unexpectedly (code={code}, reason={reason})"

    def _error_event(self, message: str, raw_text: str | None = None) -> HarnessEvent:
        payload: dict[str, object] = {"type": "error", "message": message}
        return HarnessEvent(
            event_type="error",
            payload=payload,
            harness_id=_HARNESS_NAME,
            raw_text=raw_text,
        )


__all__ = ["ClaudeConnection"]
