from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path

from meridian.lib.chat.event_log import ChatEventLog
from meridian.lib.chat.protocol import ChatEvent, utc_now_iso
from meridian.lib.chat.replay import ReplayService
from meridian.lib.chat.ws_fanout import WebSocketFanOut


class RecordingWebSocket:
    def __init__(self, *, send_delay: float = 0.0) -> None:
        self.sent: list[dict[str, object]] = []
        self.closed: list[tuple[int, str | None]] = []
        self._send_delay = send_delay
        self._sent_event = asyncio.Event()
        self._closed_event = asyncio.Event()

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)
        self._sent_event.set()
        if self._send_delay:
            await asyncio.sleep(self._send_delay)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed.append((code, reason))
        self._closed_event.set()

    async def wait_for_count(self, count: int, *, timeout: float = 5.0) -> None:
        async with asyncio.timeout(timeout):
            while len(self.sent) < count:
                self._sent_event.clear()
                await self._sent_event.wait()

    async def wait_for_close(self, *, timeout: float = 5.0) -> None:
        async with asyncio.timeout(timeout):
            if not self.closed:
                await self._closed_event.wait()

def _event(chat_id: str, seq: int, event_type: str = "content.delta") -> ChatEvent:
    return ChatEvent(
        type=event_type,
        seq=seq,
        chat_id=chat_id,
        execution_id="p-backpressure",
        timestamp=utc_now_iso(),
    )

def test_backpressure_eviction_allows_reconnect_with_last_seq_to_recover_missing_events(
    tmp_path: Path,
) -> None:
    chat_id = "c-backpressure"
    event_log = ChatEventLog(tmp_path / "history.jsonl")
    fanout = WebSocketFanOut(max_buffer=2)
    slow_websocket = RecordingWebSocket(send_delay=0.05)
    replay = ReplayService(event_log, fanout)

    async def exercise() -> tuple[
        list[dict[str, object]],
        list[dict[str, object]],
        list[tuple[int, str | None]],
    ]:
        event_log.append(_event(chat_id, 0, "chat.started"))
        live_task = asyncio.create_task(replay.connect(slow_websocket))
        await slow_websocket.wait_for_count(1)

        for seq in range(1, 7):
            event = _event(chat_id, seq)
            event_log.append(event)
            await fanout.broadcast(event)

        await slow_websocket.wait_for_close()
        await asyncio.sleep(0.2)
        live_task.cancel()
        with suppress(asyncio.CancelledError):
            await live_task

        last_seq = int(slow_websocket.sent[-1]["seq"])
        recovery_websocket = RecordingWebSocket()
        recovery = ReplayService(event_log, None)
        await recovery.connect(recovery_websocket, last_seq=last_seq)
        return slow_websocket.sent, recovery_websocket.sent, slow_websocket.closed

    live_payloads, recovered_payloads, closed = asyncio.run(exercise())

    live_seqs = [int(payload["seq"]) for payload in live_payloads]
    recovered_seqs = [int(payload["seq"]) for payload in recovered_payloads]

    assert closed == [(1008, "backpressure:reconnect_with_last_seq")]
    assert live_seqs == list(range(live_seqs[-1] + 1))
    assert len(live_seqs) < 7
    assert recovered_seqs == list(range(live_seqs[-1] + 1, 7))
    assert live_seqs + recovered_seqs == list(range(7))
    assert [payload["type"] for payload in recovered_payloads] == [
        asdict(_event(chat_id, seq))["type"] for seq in recovered_seqs
    ]
