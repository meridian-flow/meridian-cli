from __future__ import annotations

import asyncio
import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import ConnectionCapabilities, HarnessEvent
from meridian.lib.streaming.spawn_manager import DrainOutcome, SpawnManager, SpawnSession


def _install_runtime_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    ag_ui_module = types.ModuleType("ag_ui")
    ag_ui_core = types.ModuleType("ag_ui.core")

    class _BaseEvent(BaseModel):
        model_config = ConfigDict(extra="allow", populate_by_name=True)

    class RunStartedEvent(_BaseEvent):
        type: str = "RUN_STARTED"
        thread_id: str
        run_id: str

    class RunFinishedEvent(_BaseEvent):
        type: str = "RUN_FINISHED"
        thread_id: str
        run_id: str
        status: str | None = None

    class RunErrorEvent(_BaseEvent):
        type: str = "RUN_ERROR"
        message: str
        is_cancelled: bool | None = Field(default=None, alias="isCancelled")

    class TextMessageStartEvent(_BaseEvent):
        type: str = "TEXT_MESSAGE_START"
        message_id: str
        role: str

    class TextMessageContentEvent(_BaseEvent):
        type: str = "TEXT_MESSAGE_CONTENT"
        message_id: str
        delta: str

    class TextMessageEndEvent(_BaseEvent):
        type: str = "TEXT_MESSAGE_END"
        message_id: str

    class ReasoningMessageStartEvent(_BaseEvent):
        type: str = "REASONING_MESSAGE_START"
        message_id: str
        role: str

    class ReasoningMessageContentEvent(_BaseEvent):
        type: str = "REASONING_MESSAGE_CONTENT"
        message_id: str
        delta: str

    class ReasoningMessageEndEvent(_BaseEvent):
        type: str = "REASONING_MESSAGE_END"
        message_id: str

    class ToolCallStartEvent(_BaseEvent):
        type: str = "TOOL_CALL_START"
        tool_call_id: str
        tool_call_name: str

    class ToolCallArgsEvent(_BaseEvent):
        type: str = "TOOL_CALL_ARGS"
        tool_call_id: str
        delta: str

    class ToolCallEndEvent(_BaseEvent):
        type: str = "TOOL_CALL_END"
        tool_call_id: str

    class ToolCallResultEvent(_BaseEvent):
        type: str = "TOOL_CALL_RESULT"
        message_id: str
        tool_call_id: str
        content: str

    class StepFinishedEvent(_BaseEvent):
        type: str = "STEP_FINISHED"
        step_name: str

    class CustomEvent(_BaseEvent):
        type: str = "CUSTOM"
        name: str
        value: object

    for name, value in {
        "BaseEvent": _BaseEvent,
        "CustomEvent": CustomEvent,
        "ReasoningMessageContentEvent": ReasoningMessageContentEvent,
        "ReasoningMessageEndEvent": ReasoningMessageEndEvent,
        "ReasoningMessageStartEvent": ReasoningMessageStartEvent,
        "RunErrorEvent": RunErrorEvent,
        "RunFinishedEvent": RunFinishedEvent,
        "RunStartedEvent": RunStartedEvent,
        "StepFinishedEvent": StepFinishedEvent,
        "TextMessageContentEvent": TextMessageContentEvent,
        "TextMessageEndEvent": TextMessageEndEvent,
        "TextMessageStartEvent": TextMessageStartEvent,
        "ToolCallArgsEvent": ToolCallArgsEvent,
        "ToolCallEndEvent": ToolCallEndEvent,
        "ToolCallResultEvent": ToolCallResultEvent,
        "ToolCallStartEvent": ToolCallStartEvent,
    }.items():
        setattr(ag_ui_core, name, value)

    starlette_module = types.ModuleType("starlette")
    starlette_websockets = types.ModuleType("starlette.websockets")

    class WebSocket:
        def __init__(self, headers: dict[str, str] | None = None) -> None:
            self.headers = headers or {}
            self.accept_calls = 0
            self.close_calls: list[int | None] = []

        async def accept(self) -> None:
            self.accept_calls += 1

        async def close(self, code: int | None = None) -> None:
            self.close_calls.append(code)

        async def send_text(self, data: str) -> None:
            _ = data

        async def receive(self) -> dict[str, object]:
            return {"type": "websocket.disconnect"}

    starlette_websockets.WebSocket = WebSocket
    starlette_module.websockets = starlette_websockets

    monkeypatch.setitem(sys.modules, "ag_ui", ag_ui_module)
    monkeypatch.setitem(sys.modules, "ag_ui.core", ag_ui_core)
    monkeypatch.setitem(sys.modules, "starlette", starlette_module)
    monkeypatch.setitem(sys.modules, "starlette.websockets", starlette_websockets)


@pytest.fixture
def phase3_modules(monkeypatch: pytest.MonkeyPatch) -> tuple[types.ModuleType, types.ModuleType]:
    _install_runtime_stubs(monkeypatch)

    for module_name in (
        "meridian.lib.app.agui_mapping.base",
        "meridian.lib.app.agui_mapping.extensions",
        "meridian.lib.app.agui_mapping.claude",
        "meridian.lib.app.agui_mapping.codex",
        "meridian.lib.app.agui_mapping.opencode",
        "meridian.lib.app.agui_mapping",
        "meridian.lib.app.ws_endpoint",
    ):
        sys.modules.pop(module_name, None)

    mapping_module = importlib.import_module("meridian.lib.app.agui_mapping")
    ws_module = importlib.import_module("meridian.lib.app.ws_endpoint")
    return mapping_module, ws_module


def _event_types(events: list[Any]) -> list[str]:
    return [cast("str", event.type) for event in events]


def test_agui_mapper_protocol_includes_run_error(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    mapping_module, _ = phase3_modules
    protocol = importlib.import_module("meridian.lib.app.agui_mapping.base").AGUIMapper
    assert "make_run_error" in protocol.__dict__
    for harness_id in (HarnessId.CLAUDE, HarnessId.CODEX, HarnessId.OPENCODE):
        assert hasattr(mapping_module.get_agui_mapper(harness_id), "make_run_error")


@pytest.mark.parametrize(
    ("harness_id", "event_type"),
    [
        (HarnessId.CLAUDE, "error"),
        (HarnessId.CODEX, "error/connectionClosed"),
    ],
)
def test_mappers_translate_error_events_to_run_error(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
    harness_id: HarnessId,
    event_type: str,
) -> None:
    mapping_module, _ = phase3_modules
    mapper = mapping_module.get_agui_mapper(harness_id)

    events = mapper.translate(
        HarnessEvent(event_type=event_type, payload={"message": "boom"}, harness_id=str(harness_id))
    )

    assert _event_types(events) == ["RUN_ERROR"]
    assert events[0].message == "boom"


@pytest.mark.parametrize("event_type", ["error", "error/fatal", "session_error"])
def test_opencode_maps_all_error_variants_to_run_error(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
    event_type: str,
) -> None:
    mapping_module, _ = phase3_modules
    mapper = mapping_module.get_agui_mapper(HarnessId.OPENCODE)

    events = mapper.translate(
        HarnessEvent(event_type=event_type, payload={"message": "boom"}, harness_id="opencode")
    )

    assert _event_types(events) == ["RUN_ERROR"]
    assert events[0].message == "boom"


def test_outbound_loop_skips_run_finished_after_run_error(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    _, ws_module = phase3_modules
    ag_ui_core = importlib.import_module("ag_ui.core")

    class FakeMapper:
        def translate(self, event: HarnessEvent) -> list[Any]:
            if event.event_type == "error":
                return [ag_ui_core.RunErrorEvent(message="boom")]
            return []

        def make_run_started(self, spawn_id: str) -> Any:
            return ag_ui_core.RunStartedEvent(thread_id=spawn_id, run_id=f"{spawn_id}-run-1")

        def make_run_finished(self, spawn_id: str) -> Any:
            return ag_ui_core.RunFinishedEvent(thread_id=spawn_id, run_id=f"{spawn_id}-run-1")

        def make_run_error(self, message: str) -> Any:
            return ag_ui_core.RunErrorEvent(message=message)

    class FakeWebSocket:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        async def send_text(self, data: str) -> None:
            self.payloads.append(cast("dict[str, object]", json.loads(data)))

    async def run() -> list[dict[str, object]]:
        queue: asyncio.Queue[HarnessEvent | None] = asyncio.Queue()
        await queue.put(
            HarnessEvent(
                event_type="error",
                payload={"message": "boom"},
                harness_id="codex",
            )
        )
        await queue.put(None)
        websocket = FakeWebSocket()
        await ws_module._outbound_loop(websocket, queue, FakeMapper(), "p1")
        return websocket.payloads

    payloads = asyncio.run(run())
    assert [payload["type"] for payload in payloads] == ["RUN_ERROR"]


def test_outbound_loop_emits_run_finished_without_run_error(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    _, ws_module = phase3_modules
    ag_ui_core = importlib.import_module("ag_ui.core")

    class FakeMapper:
        def translate(self, event: HarnessEvent) -> list[Any]:
            _ = event
            return []

        def make_run_started(self, spawn_id: str) -> Any:
            return ag_ui_core.RunStartedEvent(thread_id=spawn_id, run_id=f"{spawn_id}-run-1")

        def make_run_finished(self, spawn_id: str) -> Any:
            return ag_ui_core.RunFinishedEvent(thread_id=spawn_id, run_id=f"{spawn_id}-run-1")

        def make_run_error(self, message: str) -> Any:
            return ag_ui_core.RunErrorEvent(message=message)

    class FakeWebSocket:
        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        async def send_text(self, data: str) -> None:
            self.payloads.append(cast("dict[str, object]", json.loads(data)))

    async def run() -> list[dict[str, object]]:
        queue: asyncio.Queue[HarnessEvent | None] = asyncio.Queue()
        await queue.put(None)
        websocket = FakeWebSocket()
        await ws_module._outbound_loop(websocket, queue, FakeMapper(), "p1")
        return websocket.payloads

    payloads = asyncio.run(run())
    assert [payload["type"] for payload in payloads] == ["RUN_FINISHED"]


def test_allowed_origin_regex_matches_localhost_forms(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
) -> None:
    _, ws_module = phase3_modules

    for origin in (
        "http://localhost",
        "https://localhost",
        "http://localhost:3000",
        "https://localhost:8443",
        "http://127.0.0.1",
        "https://127.0.0.1:9000",
    ):
        assert ws_module._ALLOWED_ORIGIN_RE.match(origin) is not None


@pytest.mark.asyncio
async def test_ws_route_allows_missing_origin_header(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, ws_module = phase3_modules
    called: list[tuple[object, str, object]] = []

    async def fake_spawn_websocket(websocket: object, spawn_id: str, manager: object) -> None:
        called.append((websocket, spawn_id, manager))

    monkeypatch.setattr(ws_module, "spawn_websocket", fake_spawn_websocket)

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
            self.headers: dict[str, str] = {}
            self.close_calls: list[int | None] = []
            self.accept_calls = 0

        async def accept(self) -> None:
            self.accept_calls += 1

        async def close(self, code: int | None = None) -> None:
            self.close_calls.append(code)

        async def send_text(self, data: str) -> None:
            _ = data

        async def receive(self) -> dict[str, object]:
            return {"type": "websocket.disconnect"}

    app = FakeApp()
    manager = object()
    ws_module.register_ws_routes(app, manager)
    websocket = FakeWebSocket()

    handler = cast("Any", app.handler)
    await handler(websocket, "p1")

    assert called == [(websocket, "p1", manager)]
    assert websocket.close_calls == []
    assert websocket.accept_calls == 0


@pytest.mark.asyncio
async def test_ws_route_rejects_non_local_origin_before_accept(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, ws_module = phase3_modules
    spawn_calls = 0

    async def fake_spawn_websocket(websocket: object, spawn_id: str, manager: object) -> None:
        nonlocal spawn_calls
        _ = websocket, spawn_id, manager
        spawn_calls += 1

    monkeypatch.setattr(ws_module, "spawn_websocket", fake_spawn_websocket)

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

        async def send_text(self, data: str) -> None:
            _ = data

        async def receive(self) -> dict[str, object]:
            return {"type": "websocket.disconnect"}

    app = FakeApp()
    ws_module.register_ws_routes(app, object())
    websocket = FakeWebSocket()

    handler = cast("Any", app.handler)
    await handler(websocket, "p1")

    assert spawn_calls == 0
    assert websocket.close_calls == [4403]
    assert websocket.accept_calls == 0


@pytest.mark.asyncio
async def test_inbound_loop_routes_interrupt(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
    tmp_path: Path,
) -> None:
    _, ws_module = phase3_modules

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

    await ws_module._inbound_loop(websocket, SpawnId("p1"), cast("Any", manager))

    assert manager.interrupt_calls == [(SpawnId("p1"), "app_ws")]
    assert websocket.payloads == []


@pytest.mark.asyncio
async def test_inbound_loop_routes_cancel_to_signal_canceller(
    phase3_modules: tuple[types.ModuleType, types.ModuleType],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, ws_module = phase3_modules
    cancel_calls: list[SpawnId] = []

    class FakeManager:
        def __init__(self) -> None:
            self.state_root = tmp_path

        async def inject(self, spawn_id: SpawnId, message: str, source: str = "app_ws") -> object:
            _ = spawn_id, message, source
            return types.SimpleNamespace(success=True, error=None, inbound_seq=1)

        async def interrupt(self, spawn_id: SpawnId, source: str = "app_ws") -> object:
            _ = spawn_id, source
            return types.SimpleNamespace(success=True, error=None, inbound_seq=2, noop=False)

    class _FakeCanceller:
        def __init__(self, *, state_root: Path, manager: FakeManager) -> None:
            _ = state_root, manager

        async def cancel(self, spawn_id: SpawnId) -> object:
            cancel_calls.append(spawn_id)
            return types.SimpleNamespace(
                already_terminal=False,
                finalizing=False,
                status="cancelled",
            )

    class FakeWebSocket:
        def __init__(self) -> None:
            self.frames: list[dict[str, object]] = [
                {"type": "websocket.receive", "text": '{"type":"cancel"}'},
                {"type": "websocket.disconnect"},
            ]
            self.payloads: list[dict[str, object]] = []

        async def receive(self) -> dict[str, object]:
            return self.frames.pop(0)

        async def send_text(self, data: str) -> None:
            self.payloads.append(cast("dict[str, object]", json.loads(data)))

    manager = FakeManager()
    websocket = FakeWebSocket()
    monkeypatch.setattr(ws_module, "SignalCanceller", _FakeCanceller)

    await ws_module._inbound_loop(websocket, SpawnId("p1"), cast("Any", manager))

    assert cancel_calls == [SpawnId("p1")]
    assert websocket.payloads == []


@pytest.mark.asyncio
async def test_drain_loop_fans_out_threshold_event_before_exit(tmp_path: Path) -> None:
    manager = SpawnManager(state_root=tmp_path, repo_root=tmp_path)
    spawn_id = SpawnId("p1")
    subscriber: asyncio.Queue[HarnessEvent | None] = asyncio.Queue()
    cleanup_calls: list[SpawnId] = []
    completion_future: asyncio.Future[DrainOutcome] = asyncio.get_running_loop().create_future()

    class FakeControlServer:
        async def stop(self) -> None:
            return None

    class FakeConnection:
        @property
        def harness_id(self) -> HarnessId:
            return HarnessId.CODEX

        @property
        def spawn_id(self) -> SpawnId:
            return spawn_id

        @property
        def capabilities(self) -> ConnectionCapabilities:
            return ConnectionCapabilities(
                mid_turn_injection="queue",
                supports_steer=True,
                supports_interrupt=True,
                supports_cancel=True,
                runtime_model_switch=False,
                structured_reasoning=False,
            )

        @property
        def state(self) -> str:
            return "connected"

        async def start(self, config: object) -> None:
            _ = config

        async def stop(self) -> None:
            return None

        def health(self) -> bool:
            return True

        async def send_user_message(self, text: str) -> None:
            _ = text

        async def send_interrupt(self) -> None:
            return None

        async def send_cancel(self) -> None:
            return None

        async def events(self):  # type: ignore[no-untyped-def]
            for index in range(10):
                yield HarnessEvent(
                    event_type="tick",
                    payload={"index": index},
                    harness_id="codex",
                )

    async def fail_append(path: Path, payload: dict[str, object]) -> None:
        _ = path, payload
        raise OSError("disk full")

    async def fake_cleanup(
        cleanup_spawn_id: SpawnId,
    ) -> None:
        assert cleanup_spawn_id == spawn_id
        cleanup_calls.append(cleanup_spawn_id)
        manager._sessions.pop(spawn_id, None)

    manager._sessions[spawn_id] = SpawnSession(
        connection=cast("Any", FakeConnection()),
        drain_task=asyncio.current_task(),
        subscriber=subscriber,
        control_server=cast("Any", FakeControlServer()),
        started_monotonic=0.0,
        completion_future=completion_future,
    )

    manager._append_jsonl = cast("Any", fail_append)
    manager._cleanup_completed_session = cast("Any", fake_cleanup)

    await manager._drain_loop(spawn_id, cast("Any", FakeConnection()))
    await asyncio.gather(*manager._cleanup_tasks)
    assert completion_future.done()
    outcome = completion_future.result()
    assert outcome.status == "failed"
    assert outcome.exit_code == 1
    assert outcome.error == "Aborted drain loop after repeated output persistence failures"
    assert outcome.duration_secs >= 0.0

    delivered: list[int] = []
    while True:
        event = await subscriber.get()
        if event is None:
            break
        delivered.append(cast("int", event.payload["index"]))

    assert delivered == list(range(10))
    assert cleanup_calls == [spawn_id]
