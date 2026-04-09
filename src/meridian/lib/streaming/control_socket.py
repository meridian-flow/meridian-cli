"""Per-spawn Unix domain socket control server."""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, cast

from meridian.lib.core.types import SpawnId
from meridian.lib.streaming.types import InjectResult

if TYPE_CHECKING:
    from meridian.lib.streaming.spawn_manager import SpawnManager


class ControlSocketServer:
    """Handle one control socket endpoint for one active spawn."""

    def __init__(self, spawn_id: SpawnId, socket_path: Path, manager: SpawnManager):
        self._spawn_id = spawn_id
        self._socket_path = socket_path
        self._manager = manager
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        """Create and bind the Unix domain control socket."""

        self._socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._socket_path.unlink(missing_ok=True)
        self._server = await asyncio.start_unix_server(
            self._handle_client, path=str(self._socket_path)
        )

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Read one request, route to the manager, and write one response."""

        response: dict[str, object]
        try:
            raw = await reader.readline()
            if not raw:
                response = {"ok": False, "error": "empty request"}
            else:
                response = await self._handle_request(raw)
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}

        encoded = (
            json.dumps(response, separators=(",", ":"), sort_keys=True).encode("utf-8")
            + b"\n"
        )
        writer.write(encoded)
        with suppress(BrokenPipeError, ConnectionResetError):
            await writer.drain()
        writer.close()
        with suppress(BrokenPipeError, ConnectionResetError):
            await writer.wait_closed()

    async def _handle_request(self, raw: bytes) -> dict[str, object]:
        """Decode and route one control request."""

        try:
            payload_value: object = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"ok": False, "error": "invalid JSON request"}

        if not isinstance(payload_value, dict):
            return {"ok": False, "error": "request must be a JSON object"}
        payload = cast("dict[str, object]", payload_value)

        message_type = payload.get("type")
        if not isinstance(message_type, str):
            return {"ok": False, "error": "missing request type"}

        result: InjectResult
        if message_type == "user_message":
            text = payload.get("text")
            if not isinstance(text, str):
                return {"ok": False, "error": "user_message requires text"}
            result = await self._manager.inject(
                self._spawn_id, message=text, source="control_socket"
            )
        elif message_type == "interrupt":
            result = await self._manager.interrupt(self._spawn_id, source="control_socket")
        elif message_type == "cancel":
            result = await self._manager.cancel(self._spawn_id, source="control_socket")
        else:
            return {"ok": False, "error": f"unsupported request type: {message_type}"}

        if result.success:
            return {"ok": True}
        return {"ok": False, "error": result.error or "request failed"}

    async def stop(self) -> None:
        """Close the server and remove the socket path."""

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._socket_path.unlink(missing_ok=True)


__all__ = ["ControlSocketServer"]
