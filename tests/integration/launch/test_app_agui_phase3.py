from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import pytest

from ag_ui.core import RunErrorEvent, RunFinishedEvent, RunStartedEvent
from meridian.lib.app import agui_mapping as mapping_module
from meridian.lib.app import ws_endpoint
from meridian.lib.core.types import HarnessId
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


def test_opencode_message_updated_translates_assistant_snapshot_to_text_delta() -> None:
    mapper = mapping_module.get_agui_mapper(HarnessId.OPENCODE)

    initial = mapper.translate(
        HarnessEvent(
            event_type="message.updated",
            payload={
                "properties": {
                    "info": {"id": "msg-1", "role": "assistant", "content": "Hel"},
                }
            },
            harness_id=HarnessId.OPENCODE.value,
        )
    )
    assert _event_types(initial) == ["TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT"]
    assert initial[1].delta == "Hel"

    snapshot = mapper.translate(
        HarnessEvent(
            event_type="message.updated",
            payload={
                "properties": {
                    "info": {"id": "msg-1", "role": "assistant", "content": "Hello"},
                }
            },
            harness_id=HarnessId.OPENCODE.value,
        )
    )
    assert _event_types(snapshot) == ["TEXT_MESSAGE_CONTENT"]
    assert snapshot[0].delta == "lo"


def test_opencode_message_updated_closes_assistant_message_for_user_role() -> None:
    mapper = mapping_module.get_agui_mapper(HarnessId.OPENCODE)

    _ = mapper.translate(
        HarnessEvent(
            event_type="message.updated",
            payload={
                "properties": {
                    "info": {"id": "msg-1", "role": "assistant", "content": "hello"},
                }
            },
            harness_id=HarnessId.OPENCODE.value,
        )
    )

    user_update = mapper.translate(
        HarnessEvent(
            event_type="message.updated",
            payload={
                "properties": {"info": {"id": "msg-2", "role": "user", "content": "hi"}},
            },
            harness_id=HarnessId.OPENCODE.value,
        )
    )
    assert _event_types(user_update) == ["TEXT_MESSAGE_END"]


def test_claude_assistant_snapshot_translates_all_content_blocks() -> None:
    mapper = mapping_module.get_agui_mapper(HarnessId.CLAUDE)

    events = mapper.translate(
        HarnessEvent(
            event_type="assistant",
            payload={
                "message": {
                    "content": [
                        {"type": "thinking", "thinking": "\ncheck plan\n"},
                        {"type": "text", "text": "\nHello\nworld\n"},
                        {
                            "type": "tool_use",
                            "id": "toolu_abc123",
                            "name": "Read",
                            "input": {"path": "/foo"},
                        },
                    ]
                }
            },
            harness_id=HarnessId.CLAUDE.value,
        )
    )

    assert _event_types(events) == [
        "REASONING_MESSAGE_START",
        "REASONING_MESSAGE_CONTENT",
        "REASONING_MESSAGE_END",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "TEXT_MESSAGE_END",
        "TOOL_CALL_START",
        "TOOL_CALL_ARGS",
        "TOOL_CALL_END",
    ]
    assert events[1].delta == "\ncheck plan\n"
    assert events[4].delta == "\nHello\nworld\n"
    assert events[6].tool_call_id == "toolu_abc123"
    assert events[6].tool_call_name == "Read"
    assert events[7].tool_call_id == "toolu_abc123"
    assert events[7].delta == '{"path": "/foo"}'
    assert events[8].tool_call_id == "toolu_abc123"


@pytest.mark.parametrize(
    "event_type",
    ["server.heartbeat", "server.connected", "sync", "session.diff", "session.updated"],
)
def test_opencode_keepalive_events_do_not_close_active_assistant_message(event_type: str) -> None:
    mapper = mapping_module.get_agui_mapper(HarnessId.OPENCODE)

    first = mapper.translate(
        HarnessEvent(
            event_type="message.updated",
            payload={
                "properties": {
                    "info": {"id": "msg-1", "role": "assistant", "content": "Hello"},
                }
            },
            harness_id=HarnessId.OPENCODE.value,
        )
    )
    assert _event_types(first) == ["TEXT_MESSAGE_START", "TEXT_MESSAGE_CONTENT"]

    keepalive = mapper.translate(
        HarnessEvent(
            event_type=event_type,
            payload={"properties": {"info": {"title": "ignored"}}},
            harness_id=HarnessId.OPENCODE.value,
        )
    )
    assert keepalive == []

    follow_up = mapper.translate(
        HarnessEvent(
            event_type="message.updated",
            payload={
                "properties": {
                    "info": {"id": "msg-1", "role": "assistant", "content": "Hello world"},
                }
            },
            harness_id=HarnessId.OPENCODE.value,
        )
    )
    assert _event_types(follow_up) == ["TEXT_MESSAGE_CONTENT"]
    assert follow_up[0].delta == " world"


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
    event = HarnessEvent(event_type="error", payload={"message": "boom"}, harness_id="codex")
    await queue.put(event)
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
