"""Runtime registry and durable drain for active harness connections."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

from meridian.lib.core.types import SpawnId
from meridian.lib.state.atomic import append_text_line
from meridian.lib.streaming.control_socket import ControlSocketServer
from meridian.lib.streaming.types import InjectResult

if TYPE_CHECKING:
    from meridian.lib.harness.connections.base import (
        ConnectionConfig,
        HarnessConnection,
        HarnessEvent,
        HarnessReceiver,
    )


@dataclass
class SpawnSession:
    """Live resources associated with one running spawn."""

    connection: HarnessConnection
    drain_task: asyncio.Task[None]
    subscriber: asyncio.Queue[HarnessEvent | None] | None
    control_server: ControlSocketServer


class SpawnManager:
    """Own active connections, durable drain loops, and control routing."""

    def __init__(self, state_root: Path, repo_root: Path):
        self._state_root = state_root
        self._repo_root = repo_root
        self._sessions: dict[SpawnId, SpawnSession] = {}

    @property
    def state_root(self) -> Path:
        """Return the resolved Meridian state root."""

        return self._state_root

    @property
    def repo_root(self) -> Path:
        """Return the repository root used for managed spawns."""

        return self._repo_root

    async def start_spawn(self, config: ConnectionConfig) -> HarnessConnection:
        """Start one connection and register durable drain/control resources."""

        spawn_id = config.spawn_id
        if spawn_id in self._sessions:
            msg = f"Spawn {spawn_id} is already active"
            raise ValueError(msg)

        from meridian.lib.harness.connections import get_connection_class

        connection_class = get_connection_class(config.harness_id)
        connection_factory = cast("Callable[[], HarnessConnection]", connection_class)
        connection = connection_factory()
        await connection.start(config)

        drain_task = asyncio.create_task(self._drain_loop(spawn_id, connection))
        control_server = ControlSocketServer(
            spawn_id=spawn_id,
            socket_path=self._spawn_dir(spawn_id) / "control.sock",
            manager=self,
        )

        try:
            await control_server.start()
        except Exception:
            drain_task.cancel()
            with suppress(asyncio.CancelledError):
                await drain_task
            with suppress(Exception):
                await connection.stop()
            raise

        self._sessions[spawn_id] = SpawnSession(
            connection=connection,
            drain_task=drain_task,
            subscriber=None,
            control_server=control_server,
        )
        return connection

    async def _drain_loop(self, spawn_id: SpawnId, receiver: HarnessReceiver) -> None:
        """Durably append each harness event and fan out to the active subscriber."""

        try:
            async for event in receiver.events():
                payload = {
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "harness_id": event.harness_id,
                    "ts": time.time(),
                }
                await self._append_jsonl(self._output_log_path(spawn_id), payload)
                self._fan_out_event(spawn_id, event)
        finally:
            self._fan_out_event(spawn_id, None)

    def subscribe(self, spawn_id: SpawnId) -> asyncio.Queue[HarnessEvent | None] | None:
        """Attach one subscriber queue to the spawn, or return None if unavailable."""

        session = self._sessions.get(spawn_id)
        if session is None or session.subscriber is not None:
            return None
        session.subscriber = asyncio.Queue(maxsize=1000)
        return session.subscriber

    def unsubscribe(self, spawn_id: SpawnId) -> None:
        """Detach the current subscriber for one spawn."""

        session = self._sessions.get(spawn_id)
        if session is not None:
            session.subscriber = None

    async def inject(
        self,
        spawn_id: SpawnId,
        message: str,
        source: str = "control_socket",
    ) -> InjectResult:
        """Record and route one user message injection to the target connection."""

        session = self._sessions.get(spawn_id)
        if session is None:
            return InjectResult(success=False, error=f"Spawn {spawn_id} is not active")

        try:
            await self._record_inbound(
                spawn_id,
                action="user_message",
                data={"text": message},
                source=source,
            )
            await session.connection.send_user_message(message)
        except Exception as exc:
            return InjectResult(success=False, error=str(exc))
        return InjectResult(success=True)

    async def interrupt(self, spawn_id: SpawnId, source: str) -> InjectResult:
        """Record and route one interrupt request to the target connection."""

        session = self._sessions.get(spawn_id)
        if session is None:
            return InjectResult(success=False, error=f"Spawn {spawn_id} is not active")

        try:
            await self._record_inbound(
                spawn_id,
                action="interrupt",
                data={},
                source=source,
            )
            await session.connection.send_interrupt()
        except Exception as exc:
            return InjectResult(success=False, error=str(exc))
        return InjectResult(success=True)

    async def cancel(self, spawn_id: SpawnId, source: str) -> InjectResult:
        """Record and route one cancellation request to the target connection."""

        session = self._sessions.get(spawn_id)
        if session is None:
            return InjectResult(success=False, error=f"Spawn {spawn_id} is not active")

        try:
            await self._record_inbound(
                spawn_id,
                action="cancel",
                data={},
                source=source,
            )
            await session.connection.send_cancel()
        except Exception as exc:
            return InjectResult(success=False, error=str(exc))
        return InjectResult(success=True)

    async def _record_inbound(
        self,
        spawn_id: SpawnId,
        action: str,
        data: dict[str, object],
        source: str,
    ) -> None:
        """Append one inbound action to the spawn write-ahead control log."""

        payload = {
            "action": action,
            "data": data,
            "ts": time.time(),
            "source": source,
        }
        await self._append_jsonl(self._inbound_log_path(spawn_id), payload)

    def get_connection(self, spawn_id: SpawnId) -> HarnessConnection | None:
        """Return the active connection for one spawn, if present."""

        session = self._sessions.get(spawn_id)
        if session is None:
            return None
        return session.connection

    async def stop_spawn(self, spawn_id: SpawnId) -> None:
        """Stop one managed spawn and clean up all associated resources."""

        session = self._sessions.get(spawn_id)
        if session is None:
            return

        with suppress(Exception):
            await session.connection.stop()

        session.drain_task.cancel()
        with suppress(asyncio.CancelledError):
            await session.drain_task

        with suppress(Exception):
            await session.control_server.stop()

        self._fan_out_event(spawn_id, None)
        self._sessions.pop(spawn_id, None)

    async def shutdown(self) -> None:
        """Stop every active spawn and clear the session registry."""

        for spawn_id in list(self._sessions):
            await self.stop_spawn(spawn_id)

    def list_spawns(self) -> list[SpawnId]:
        """List active spawn IDs."""

        return list(self._sessions)

    async def _append_jsonl(self, path: Path, payload: Mapping[str, object]) -> None:
        line = json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n"
        await asyncio.to_thread(append_text_line, path, line)

    def _fan_out_event(self, spawn_id: SpawnId, event: HarnessEvent | None) -> None:
        session = self._sessions.get(spawn_id)
        if session is None or session.subscriber is None:
            return
        if event is None:
            # Preserve the terminal sentinel even under backpressure.
            while True:
                try:
                    session.subscriber.put_nowait(None)
                    return
                except asyncio.QueueFull:
                    with suppress(asyncio.QueueEmpty):
                        session.subscriber.get_nowait()
                    continue
        with suppress(asyncio.QueueFull):
            session.subscriber.put_nowait(event)

    def _spawn_dir(self, spawn_id: SpawnId) -> Path:
        return self._state_root / "spawns" / str(spawn_id)

    def _output_log_path(self, spawn_id: SpawnId) -> Path:
        return self._spawn_dir(spawn_id) / "output.jsonl"

    def _inbound_log_path(self, spawn_id: SpawnId) -> Path:
        return self._spawn_dir(spawn_id) / "inbound.jsonl"


__all__ = ["SpawnManager", "SpawnSession"]
