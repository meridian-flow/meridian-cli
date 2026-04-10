"""Claude bidirectional connection adapter via stdin/stdout stream-json."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from asyncio.subprocess import PIPE, Process
from collections.abc import AsyncIterator
from io import BufferedWriter
from typing import Final, cast

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    ConnectionNotReady,
    ConnectionState,
    HarnessConnection,
    HarnessEvent,
)
from meridian.lib.launch.env import inherit_child_env
from meridian.lib.state.paths import resolve_spawn_log_dir

logger = logging.getLogger(__name__)

_PROCESS_KILL_GRACE_SECONDS: Final[float] = 10.0
_VERSION_CHECK_TIMEOUT_SECONDS: Final[float] = 5.0
_TESTED_VERSION_PREFIXES: Final[tuple[str, ...]] = ("1.", "2.")
_HARNESS_NAME: Final[str] = HarnessId.CLAUDE.value
_BLOCKED_CHILD_ENV_VARS: Final[frozenset[str]] = frozenset(
    {
        "CLAUDECODE",
        "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE",
    }
)


class ClaudeConnection(HarnessConnection):
    """Bidirectional Claude harness connection via stdin/stdout stream-json.

    Launches ``claude -p --input-format stream-json --output-format stream-json``
    and communicates bidirectionally through the subprocess pipes:
    - Outbound user messages are written to stdin as NDJSON.
    - Inbound harness events are read from stdout as NDJSON.

    This replaces the earlier ``--sdk-url`` WebSocket approach, which used a
    flag that does not exist in current Claude CLI releases.
    """

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
        self._process: Process | None = None
        self._send_lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
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
        """Launch Claude subprocess and send the initial user prompt via stdin."""

        if self._state != "created":
            raise RuntimeError(f"Connection can only start from 'created', got '{self._state}'")

        self._config = config
        self._spawn_id = config.spawn_id
        self._set_state("starting")

        try:
            await self._check_claude_version()
            await self._start_subprocess(config)
            await self._send_user_turn(config.prompt)
            self._set_state("connected")
        except Exception:
            self._mark_failed("Claude connection startup failed.")
            await self._cleanup_resources(terminate_process=True)
            raise

    async def stop(self) -> None:
        """Stop the subprocess. Safe to call multiple times."""

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
        await self._send_user_turn(text)

    async def send_interrupt(self) -> None:
        """Send SIGINT to the Claude subprocess to interrupt the current turn."""
        self._ensure_connected()
        await self._signal_process(signal.SIGINT)

    async def send_cancel(self) -> None:
        """Signal cancellation by transitioning state and sending SIGINT."""
        self._ensure_connected()
        self._set_state("stopping")
        await self._signal_process(signal.SIGINT)

    async def events(self) -> AsyncIterator[HarnessEvent]:
        """Yield HarnessEvent objects read line-by-line from Claude stdout."""

        process = self._process
        if process is None:
            return
        stdout = process.stdout
        if stdout is None:
            return
        if self._event_stream_started:
            raise RuntimeError("events() iterator already consumed")
        self._event_stream_started = True

        try:
            while True:
                try:
                    line_bytes = await stdout.readline()
                except Exception as exc:
                    if self._state not in {"stopping", "stopped"}:
                        detail = f"Failed to read Claude stdout: {exc}"
                        self._mark_failed(detail)
                        yield self._error_event(detail)
                    return

                if not line_bytes:
                    # EOF — subprocess has exited and all output has been drained.
                    return_code = process.returncode
                    if return_code is None:
                        return_code = await process.wait()
                    if return_code != 0 and self._state not in {"stopping", "stopped"}:
                        detail = f"Claude subprocess exited with code {return_code}."
                        self._mark_failed(detail)
                        yield self._error_event(detail)
                    return

                raw_text = line_bytes.decode("utf-8", errors="replace").rstrip("\n")
                if not raw_text.strip():
                    continue

                parsed_events = self._parse_stdout_line(raw_text)
                if not self._protocol_validated:
                    if not parsed_events:
                        detail = (
                            "Protocol mismatch: first Claude stdout line did not contain "
                            "valid typed JSON."
                        )
                        self._mark_failed(detail)
                        yield self._error_event(detail, raw_text=raw_text)
                        return
                    self._protocol_validated = True

                for event in parsed_events:
                    yield event
        finally:
            pass

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
                "Claude version may be untested for bidirectional stdin/stdout protocol: %s",
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

    async def _start_subprocess(self, config: ConnectionConfig) -> None:
        spawn_dir = resolve_spawn_log_dir(config.repo_root, config.spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)

        stderr_path = spawn_dir / "stderr.log"
        self._stderr_handle = stderr_path.open("ab")

        command = [
            "claude",
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        if config.model:
            command.extend(["--model", config.model])
        if config.extra_args:
            command.extend(config.extra_args)

        env = inherit_child_env(
            os.environ,
            config.env_overrides,
            blocked=_BLOCKED_CHILD_ENV_VARS,
        )

        self._process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(config.repo_root),
            env=env,
            stdin=PIPE,
            stdout=PIPE,
            stderr=self._stderr_handle,
        )

    async def _send_user_turn(self, text: str) -> None:
        """Send a user turn in the stream-json wire format Claude expects.

        Claude's ``--input-format stream-json`` protocol wraps each user message as::

            {"type":"user","message":{"role":"user","content":"<text>"}}
        """
        await self._send_json(
            {"type": "user", "message": {"role": "user", "content": text}}
        )

    async def _send_json(self, payload: dict[str, object]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise ConnectionNotReady("Claude subprocess stdin is not available.")

        wire = json.dumps(payload, separators=(",", ":")) + "\n"
        async with self._send_lock:
            process.stdin.write(wire.encode("utf-8"))
            await process.stdin.drain()

    async def _signal_process(self, sig: signal.Signals) -> None:
        process = self._process
        if process is None or process.returncode is not None:
            return
        process.send_signal(sig)

    async def _cleanup_resources(self, *, terminate_process: bool) -> None:
        if terminate_process:
            await self._terminate_process()
        self._close_log_handles()

    async def _terminate_process(self) -> None:
        process = self._process
        if process is None:
            return
        if process.returncode is None:
            # Close stdin to signal no more input; then terminate if needed.
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except Exception:
                    logger.debug("Failed to close Claude subprocess stdin", exc_info=True)
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=_PROCESS_KILL_GRACE_SECONDS)
            except TimeoutError:
                process.kill()
                await process.wait()
        self._process = None

    def _close_log_handles(self) -> None:
        if self._stderr_handle is not None:
            self._stderr_handle.close()
            self._stderr_handle = None

    def _parse_stdout_line(self, line: str) -> list[HarnessEvent]:
        """Parse one line of NDJSON from Claude stdout into HarnessEvent objects."""
        payload_text = line.strip()
        if not payload_text:
            return []
        try:
            payload_obj = json.loads(payload_text)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed Claude stdout line: %s", payload_text)
            return []
        if not isinstance(payload_obj, dict):
            logger.warning("Skipping non-object Claude stdout line: %s", payload_text)
            return []

        payload = cast("dict[str, object]", payload_obj)
        event_type = payload.get("type")
        if not isinstance(event_type, str) or not event_type.strip():
            logger.warning(
                "Skipping Claude stdout line without string 'type': %s",
                payload_text,
            )
            return []

        return [
            HarnessEvent(
                event_type=event_type,
                payload=payload,
                harness_id=_HARNESS_NAME,
                raw_text=line,
            )
        ]

    def _error_event(self, message: str, raw_text: str | None = None) -> HarnessEvent:
        payload: dict[str, object] = {"type": "error", "message": message}
        return HarnessEvent(
            event_type="error",
            payload=payload,
            harness_id=_HARNESS_NAME,
            raw_text=raw_text,
        )


__all__ = ["ClaudeConnection"]
