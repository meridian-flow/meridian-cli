"""Primary attach launcher for managed-backend primary sessions.

Orchestrates: backend connection (owner: connection class) + TUI subprocess + metadata sidecar.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import socket
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field, replace
from io import BufferedWriter
from pathlib import Path
from threading import Lock
from typing import Any, Literal, cast
from urllib.parse import urlparse

from meridian.lib.core.types import SpawnId
from meridian.lib.harness.connections.base import ConnectionConfig, HarnessConnection, HarnessEvent
from meridian.lib.launch.constants import (
    OUTPUT_FILENAME,
    PRIMARY_META_FILENAME,
)
from meridian.lib.launch.launch_types import ResolvedLaunchSpec
from meridian.lib.state.atomic import atomic_write_text

from .ports import ProcessLauncher

ActivityState = Literal["starting", "idle", "turn_active", "finalizing"]
TuiCommandBuilder = Callable[[str], tuple[str, ...]]
MAX_PORT_RETRY_ATTEMPTS = 3


class PrimaryAttachError(Exception):
    """Managed backend startup failed; caller should fall back to black-box path."""


class PortBindError(Exception):
    """Backend failed to bind pre-reserved loopback port (TOCTOU race)."""


@dataclass
class PrimaryMetadata:
    """Metadata sidecar for managed-backend primaries."""

    managed_backend: bool = True
    launcher_pid: int = field(default_factory=os.getpid)
    backend_pid: int | None = None
    tui_pid: int | None = None
    backend_port: int | None = None
    activity: ActivityState = "starting"
    harness_session_id: str | None = None


@dataclass(frozen=True)
class PrimaryAttachOutcome:
    """Result of a primary attach launch."""

    exit_code: int
    session_id: str | None
    tui_pid: int | None


class PrimaryAttachLauncher:
    """Manages lifecycle: connection (owns backend) + TUI process + metadata."""

    def __init__(
        self,
        *,
        spawn_id: SpawnId,
        spawn_dir: Path,
        connection: HarnessConnection[Any],
        tui_command_builder: TuiCommandBuilder,
        process_launcher: ProcessLauncher,
        on_running: Callable[[int], None] | None = None,
    ) -> None:
        self._spawn_id = spawn_id
        self._spawn_dir = spawn_dir
        self._connection = connection
        self._tui_command_builder = tui_command_builder
        self._process_launcher = process_launcher
        self._on_running = on_running
        self._metadata = PrimaryMetadata()
        self._metadata_lock = Lock()
        self._output_handle: BufferedWriter | None = None
        self._event_writer_task: asyncio.Task[None] | None = None

    async def run(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
        cwd: Path,
        env: dict[str, str],
        on_running: Callable[[int], None] | None = None,
    ) -> PrimaryAttachOutcome:
        """Execute the full primary attach lifecycle."""

        self._spawn_dir.mkdir(parents=True, exist_ok=True)
        connection_started = False
        session_id: str | None = None

        try:
            config = await self._start_primary_observer_connection_with_retry(
                config=config,
                spec=spec,
            )
            connection_started = True
            session_id = self._connection.session_id

            with self._metadata_lock:
                self._metadata.backend_pid = self._connection.subprocess_pid
                self._metadata.backend_port = self._resolve_backend_port(config=config)
            self._write_metadata()

            self._event_writer_task = asyncio.create_task(self._run_event_writer())
            self._set_harness_session_id(session_id)
            self._set_activity("idle")

            if session_id is None or not session_id.strip():
                raise RuntimeError(
                    f"Managed primary attach requires a harness session id "
                    f"(spawn_id={self._spawn_id})"
                )

            command = tuple(self._tui_command_builder(session_id))
            loop = asyncio.get_running_loop()
            running_callback = on_running if on_running is not None else self._on_running

            def _handle_running(pid: int) -> None:
                self._set_tui_pid(pid)
                if running_callback is not None:
                    running_callback(pid)

            def _on_child_started(pid: int) -> None:
                loop.call_soon_threadsafe(_handle_running, pid)

            launched = await asyncio.to_thread(
                self._process_launcher.launch,
                command=command,
                cwd=cwd,
                env=env,
                output_log_path=None,
                on_child_started=_on_child_started,
            )

            return PrimaryAttachOutcome(
                exit_code=launched.exit_code,
                session_id=session_id,
                tui_pid=launched.pid,
            )
        finally:
            if connection_started:
                self._set_activity("finalizing")
            writer_task = self._event_writer_task
            if writer_task is not None:
                writer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await writer_task
            if connection_started:
                await self._connection.stop()

    async def _start_primary_observer_connection_with_retry(
        self,
        *,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> ConnectionConfig:
        current_config = config
        for attempt in range(MAX_PORT_RETRY_ATTEMPTS):
            try:
                await self._start_primary_observer_connection(config=current_config, spec=spec)
                return current_config
            except PortBindError as exc:
                if attempt + 1 >= MAX_PORT_RETRY_ATTEMPTS:
                    raise PrimaryAttachError(
                        "Port bind failed after "
                        f"{MAX_PORT_RETRY_ATTEMPTS} attempts; falling back to black-box launch"
                    ) from exc
                current_config = self._with_fresh_retry_port(current_config)
        raise PrimaryAttachError("Managed primary attach startup did not converge")

    async def _start_primary_observer_connection(
        self,
        *,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> None:
        start_fn = self._connection.start
        try:
            parameters = inspect.signature(start_fn).parameters
        except (TypeError, ValueError):
            parameters = {}

        if "primary_observer_mode" in parameters:
            await cast("Any", start_fn)(config, spec, primary_observer_mode=True)
            return

        await start_fn(config, spec)

    def _write_metadata(self) -> None:
        """Atomic write primary_meta.json to spawn_dir."""

        with self._metadata_lock:
            payload = {
                "managed_backend": self._metadata.managed_backend,
                "launcher_pid": self._metadata.launcher_pid,
                "backend_pid": self._metadata.backend_pid,
                "tui_pid": self._metadata.tui_pid,
                "backend_port": self._metadata.backend_port,
                "activity": self._metadata.activity,
                "harness_session_id": self._metadata.harness_session_id,
            }
        atomic_write_text(
            self._spawn_dir / PRIMARY_META_FILENAME,
            json.dumps(payload, separators=(",", ":")) + "\n",
        )

    async def _run_event_writer(self) -> None:
        """Stream connection events to output.jsonl."""

        output_path = self._spawn_dir / OUTPUT_FILENAME
        output_handle = output_path.open("ab")
        self._output_handle = output_handle
        try:
            async for event in self._connection.events():
                self._update_activity_from_event(event)
                payload = {
                    "type": event.event_type,
                    "payload": event.payload,
                    "ts": time.time(),
                }
                line = json.dumps(payload, separators=(",", ":"), default=str) + "\n"
                output_handle.write(line.encode("utf-8"))
                output_handle.flush()
        finally:
            output_handle.close()
            self._output_handle = None

    def _update_activity_from_event(self, event: HarnessEvent) -> None:
        """Update activity state based on connection events."""

        event_type = event.event_type
        if event_type in {"turn/started"}:
            self._set_activity("turn_active")
        elif event_type in {"turn/completed", "session.idle"}:
            self._set_activity("idle")

    def _set_activity(self, activity: ActivityState) -> None:
        should_write = False
        with self._metadata_lock:
            if self._metadata.activity == "finalizing" and activity != "finalizing":
                return
            if self._metadata.activity != activity:
                self._metadata.activity = activity
                should_write = True
        if should_write:
            self._write_metadata()

    def _set_harness_session_id(self, session_id: str | None) -> None:
        if session_id is None:
            return
        should_write = False
        with self._metadata_lock:
            if self._metadata.harness_session_id != session_id:
                self._metadata.harness_session_id = session_id
                should_write = True
        if should_write:
            self._write_metadata()

    def _set_tui_pid(self, pid: int) -> None:
        should_write = False
        with self._metadata_lock:
            if self._metadata.tui_pid != pid:
                self._metadata.tui_pid = pid
                should_write = True
        if should_write:
            self._write_metadata()

    def _resolve_backend_port(self, *, config: ConnectionConfig) -> int | None:
        if config.ws_port > 0:
            return config.ws_port

        base_url = getattr(self._connection, "_base_url", None)
        if not isinstance(base_url, str):
            return None
        parsed = urlparse(base_url)
        return parsed.port

    def _with_fresh_retry_port(self, config: ConnectionConfig) -> ConnectionConfig:
        return replace(
            config,
            ws_port=_reserve_local_port(host=config.ws_bind_host),
        )


def _reserve_local_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


__all__ = [
    "MAX_PORT_RETRY_ATTEMPTS",
    "ActivityState",
    "PortBindError",
    "PrimaryAttachError",
    "PrimaryAttachLauncher",
    "PrimaryAttachOutcome",
    "PrimaryMetadata",
    "TuiCommandBuilder",
]
