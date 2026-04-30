"""Replay persisted chat events to WebSocket clients."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

from meridian.lib.chat.event_log import ChatEventLog
from meridian.lib.chat.ws_fanout import WebSocketFanOut


class ReplayService:
    """Register-before-replay WebSocket replay service."""

    def __init__(
        self,
        event_log: ChatEventLog,
        ws_fanout: WebSocketFanOut | None,
        send_lock: asyncio.Lock | None = None,
    ) -> None:
        self._log = event_log
        self._fanout = ws_fanout
        self._send_lock = send_lock

    async def connect(self, ws: WebSocket, last_seq: int | None = None) -> None:
        start = 0 if last_seq is None else last_seq + 1
        if self._fanout is None:
            for event in self._log.read_from(start):
                await self._send_json(ws, asdict(event))
            await ws.close(code=1000)
            return

        live_queue = self._fanout.register(ws)
        max_replayed_seq = start - 1
        try:
            for event in self._log.read_from(start):
                await self._send_json(ws, asdict(event))
                max_replayed_seq = max(max_replayed_seq, event.seq)

            while True:
                event = await live_queue.get()
                if event is None:
                    return
                if event.seq <= max_replayed_seq:
                    continue
                await self._send_json(ws, asdict(event))
        finally:
            self._fanout.unregister(ws)


    async def _send_json(self, ws: WebSocket, payload: dict[str, object]) -> None:
        if self._send_lock is None:
            await ws.send_json(payload)
            return
        async with self._send_lock:
            await ws.send_json(payload)


__all__ = ["ReplayService"]
