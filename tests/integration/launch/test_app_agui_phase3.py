from __future__ import annotations

import asyncio
import json
import types
from pathlib import Path
from typing import Any, cast

import pytest
from ag_ui.core import RunErrorEvent, RunFinishedEvent, RunStartedEvent

from meridian.lib.app import agui_mapping as mapping_module
from meridian.lib.app import ws_endpoint
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import HarnessEvent


def _event_types(events: list[Any]) -> list[str]:
    return [cast("str", event.type) for event in events]


@pytest.mark.parametrize(
    ("harness_id", "event_type"),
    [
        (HarnessId.CLAUDE, "error"),
        (HarnessId.CODEX, "error/connectionClosed"),
        (HarnessId.OPENCODE, "error"),
        (HarnessId.OPENCODE, "error/fatal"),
        (HarnessId.OPENCODE, "session_error"),
    ],
)
def test_mappers_translate_error_events_to_run_error(
    harness_id: HarnessId,
    event_type: str,
) -> None:
    mapper = mapping_module.get_agui_mapper(harness_id)

    events = mapper.translate(
        HarnessEvent(event_type=event_type, payload={"message": "boom"}, harness_id=str(harness_id))
    )

    assert _event_types(events) == ["RUN_ERROR"]
    assert events[0].message == "boom"


@pytest.mark.asyncio
async def test_outbound_loop_skips_run_finished_after_run_error() -> None:
    class FakeMapper:
        def translate(self, event: HarnessEvent) -> list[Any]:
            if event.event_type == "error":
                return [RunErrorEvent(message="boom")]
            return []

        def make_run_started(self, spawn_id: str) -> Any:
            return RunStartedEvent(thread_id=spawn_id, run_id=f"{spawn_id}-run-1")

        def make_run_finished(self, spawn_id: str) -> Any:
            return RunFinishedEvent(thread_id=spawn_id, run_id=f"{spawn_id}-run-1")

        def make_run_error(self, message: str) -> Any:
            return RunErrorEvent(message=message)

    class FakeWebSocket:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        async def send_text(self, data: str) -> None:
            self.payloads.append(cast("dict[str, object]", json.loads(data)))

    queue: asyncio.Queue[HarnessEvent | None] = asyncio.Queue()
    await queue.put(HarnessEvent(event_type="error", payload={"message": "boom"}, harness_id="codex"))
    await queue.put(None)

    websocket = FakeWebSocket()
    await ws_endpoint._outbound_loop(websocket, queue, FakeMapper(), "p1")
    assert [payload["type"] for payload in websocket.payloads] == ["RUN_ERROR"]


@pytest.mark.asyncio
async def test_ws_route_rejects_non_local_origin_before_accept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spawn_calls = 0

    async def fake_spawn_websocket(websocket_obj: object, spawn_id: str, manager: object) -> None:
        nonlocal spawn_calls
        _ = websocket_obj, spawn_id, manager
        spawn_calls += 1

    monkeypatch.setattr(ws_endpoint, "spawn_websocket", fake_spawn_websocket)

    class FakeApp:
        def __init__(self) -> None:
            self.handler: object | None = None

        def websocket(self, path: str):
            assert path == "/api/spawns/{spawn_id}/ws"

            def decorator(handler: object) -> object:
                self.handler = handler
                return handler

            return decorator

    class FakeWebSocket:
        def __init__(self) -> None:
            self.headers = {"origin": "https://example.com"}
            self.close_calls: list[int | None] = []
            self.accept_calls = 0

        async def accept(self) -> None:
            self.accept_calls += 1

        async def close(self, code: int | None = None) -> None:
            self.close_calls.append(code)

    app = FakeApp()
    ws_endpoint.register_ws_routes(app, object())
    websocket = FakeWebSocket()

    handler = cast("Any", app.handler)
    await handler(websocket, "p1")

    assert spawn_calls == 0
    assert websocket.close_calls == [4403]
    assert websocket.accept_calls == 0


@pytest.mark.asyncio
async def test_inbound_loop_routes_interrupt(tmp_path: Path) -> None:
    class FakeManager:
        def __init__(self) -> None:
            self.state_root = tmp_path
            self.interrupt_calls: list[tuple[SpawnId, str]] = []

        async def inject(self, spawn_id: SpawnId, message: str, source: str = "app_ws") -> object:
            _ = spawn_id, message, source
            return types.SimpleNamespace(success=True, error=None, inbound_seq=1)

        async def interrupt(self, spawn_id: SpawnId, source: str = "app_ws") -> object:
            self.interrupt_calls.append((spawn_id, source))
            return types.SimpleNamespace(success=True, error=None, inbound_seq=2, noop=False)

    class FakeWebSocket:
        def __init__(self) -> None:
            self.frames: list[dict[str, object]] = [
                {"type": "websocket.receive", "text": '{"type":"interrupt"}'},
                {"type": "websocket.disconnect"},
            ]
            self.payloads: list[dict[str, object]] = []

        async def receive(self) -> dict[str, object]:
            return self.frames.pop(0)

        async def send_text(self, data: str) -> None:
            self.payloads.append(cast("dict[str, object]", json.loads(data)))

    manager = FakeManager()
    websocket = FakeWebSocket()

    await ws_endpoint._inbound_loop(websocket, SpawnId("p1"), cast("Any", manager))

    assert manager.interrupt_calls == [(SpawnId("p1"), "app_ws")]
    assert websocket.payloads == []
