"""WebSocket fan-out for normalized chat events."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

from meridian.lib.chat.protocol import ChatEvent


class WebSocketFanOut:
    """Broadcast chat events to many WebSocket clients with bounded buffers."""

    def __init__(self, max_buffer: int = 1000) -> None:
        self._clients: dict[WebSocket, asyncio.Queue[ChatEvent | None]] = {}
        self._max_buffer = max_buffer

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def register(self, ws: WebSocket) -> asyncio.Queue[ChatEvent | None]:
        queue: asyncio.Queue[ChatEvent | None] = asyncio.Queue(maxsize=self._max_buffer)
        self._clients[ws] = queue
        return queue

    def unregister(self, ws: WebSocket) -> None:
        queue = self._clients.pop(ws, None)
        if queue is not None:
            with suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    async def broadcast(self, event: ChatEvent) -> None:
        dead: list[WebSocket] = []
        for ws, queue in list(self._clients.items()):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead.append(ws)
        for ws in dead:
            self._clients.pop(ws, None)
            with suppress(Exception):
                await ws.close(code=1008, reason="backpressure:reconnect_with_last_seq")


__all__ = ["WebSocketFanOut"]
