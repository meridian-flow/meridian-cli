import asyncio
from dataclasses import asdict

import pytest

from meridian.lib.chat.event_log import ChatEventLog
from meridian.lib.chat.protocol import ChatEvent, utc_now_iso
from meridian.lib.chat.replay import ReplayService
from meridian.lib.chat.ws_fanout import WebSocketFanOut


class RecordingWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.closed: list[tuple[int, str | None]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent.append(payload)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed.append((code, reason))


class WaitingWebSocket(RecordingWebSocket):
    def __init__(self) -> None:
        super().__init__()
        self._sent_event = asyncio.Event()

    async def send_json(self, payload: dict[str, object]) -> None:
        await super().send_json(payload)
        self._sent_event.set()

    async def wait_for_count(self, count: int, *, timeout: float = 5.0) -> None:
        async with asyncio.timeout(timeout):
            while len(self.sent) < count:
                self._sent_event.clear()
                await self._sent_event.wait()


def _event(seq: int, event_type: str = "content.delta") -> ChatEvent:
    return ChatEvent(
        type=event_type,
        seq=seq,
        chat_id="c1",
        execution_id="e1",
        timestamp=utc_now_iso(),
    )


@pytest.mark.asyncio
async def test_broadcast_evicts_only_overflowing_client_and_keeps_healthy_clients_live() -> None:
    fanout = WebSocketFanOut(max_buffer=1)
    slow_ws = RecordingWebSocket()
    healthy_ws = RecordingWebSocket()

    slow_queue = fanout.register(slow_ws)
    healthy_queue = fanout.register(healthy_ws)
    first = _event(1)
    second = _event(2)

    await fanout.broadcast(first)
    assert slow_queue.get_nowait() == first
    # Put the first event back so the slow client stays backed up.
    slow_queue.put_nowait(first)

    assert healthy_queue.get_nowait() == first

    await fanout.broadcast(second)

    assert fanout.client_count == 1
    assert slow_ws.closed == [(1008, "backpressure:reconnect_with_last_seq")]
    assert healthy_ws.closed == []
    assert healthy_queue.get_nowait() == second


@pytest.mark.asyncio
async def test_unregister_signals_completion_and_updates_client_count() -> None:
    fanout = WebSocketFanOut()
    ws = RecordingWebSocket()

    queue = fanout.register(ws)

    assert fanout.client_count == 1

    fanout.unregister(ws)

    assert fanout.client_count == 0
    assert queue.get_nowait() is None

    fanout.unregister(ws)
    assert fanout.client_count == 0


@pytest.mark.asyncio
async def test_replay_service_exits_cleanly_when_fanout_unregisters_client(tmp_path) -> None:
    log = ChatEventLog(tmp_path / "events.jsonl")
    first = log.append(_event(0, "chat.started"))
    second = log.append(_event(1, "content.delta"))
    ws = WaitingWebSocket()
    fanout = WebSocketFanOut()
    replay = ReplayService(log, fanout)

    connect_task = asyncio.create_task(replay.connect(ws))
    await ws.wait_for_count(2)

    fanout.unregister(ws)
    await asyncio.wait_for(connect_task, timeout=5)

    assert ws.sent == [asdict(first), asdict(second)]
    assert fanout.client_count == 0
