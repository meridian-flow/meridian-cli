from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from meridian.lib.app import server as server_module
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.connections.base import ConnectionCapabilities, ConnectionConfig
from meridian.lib.harness.launch_spec import ResolvedLaunchSpec
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.spawn_store import get_spawn
from meridian.lib.streaming.signal_canceller import CancelOutcome
from meridian.lib.streaming.spawn_manager import DrainOutcome


class FakeHTTPException(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers or {}


class FakeJSONResponse:
    def __init__(self, *, status_code: int, content: dict[str, object]) -> None:
        self.status_code = status_code
        self.content = content


class FakeRequestValidationError(Exception):
    def __init__(self, errors: list[dict[str, object]]) -> None:
        self._errors = errors

    def errors(self) -> list[dict[str, object]]:
        return self._errors


class FakeApp:
    def __init__(self, *, title: str, lifespan: object) -> None:
        self.title = title
        self.lifespan = lifespan
        self.state = types.SimpleNamespace()
        self.post_routes: dict[str, object] = {}
        self.get_routes: dict[str, object] = {}
        self.delete_routes: dict[str, object] = {}
        self.post_route_options: dict[str, dict[str, object]] = {}
        self.get_route_options: dict[str, dict[str, object]] = {}
        self.delete_route_options: dict[str, dict[str, object]] = {}
        self.exception_handlers: dict[object, object] = {}

    def add_middleware(self, middleware_class: type[object], **kwargs: object) -> None:
        _ = middleware_class, kwargs

    def add_exception_handler(self, exc_class_or_status_code: object, handler: object) -> None:
        self.exception_handlers[exc_class_or_status_code] = handler

    def post(self, path: str, **kwargs: object):
        def decorator(handler: object) -> object:
            self.post_routes[path] = handler
            self.post_route_options[path] = kwargs
            return handler

        return decorator

    def get(self, path: str, **kwargs: object):
        def decorator(handler: object) -> object:
            self.get_routes[path] = handler
            self.get_route_options[path] = kwargs
            return handler

        return decorator

    def delete(self, path: str, **kwargs: object):
        def decorator(handler: object) -> object:
            self.delete_routes[path] = handler
            self.delete_route_options[path] = kwargs
            return handler

        return decorator

    def mount(self, path: str, app: object, name: str | None = None) -> None:
        _ = path, app, name


class FakeFastAPIModule:
    HTTPException = FakeHTTPException

    @staticmethod
    def Depends(callable_dep: object) -> object:
        return callable_dep

    @staticmethod
    def FastAPI(*, title: str, lifespan: object) -> object:
        return FakeApp(title=title, lifespan=lifespan)


class FakeCorsModule:
    CORSMiddleware = object


class FakeRequestsModule:
    class Request:
        def __init__(self) -> None:
            self.scope: dict[str, object] = {}


class FakeValidationModule:
    RequestValidationError = FakeRequestValidationError


class FakeExceptionHandlersModule:
    @staticmethod
    async def request_validation_exception_handler(
        request: object,
        exc: FakeRequestValidationError,
    ) -> dict[str, object]:
        _ = request
        return {"status_code": 422, "detail": exc.errors()}


class FakeResponsesModule:
    JSONResponse = FakeJSONResponse


class FakeStaticFilesModule:
    class StaticFiles:
        def __init__(self, **kwargs: object) -> None:
            _ = kwargs


def _fake_import_module(name: str) -> object:
    if name == "fastapi":
        return FakeFastAPIModule
    if name == "fastapi.middleware.cors":
        return FakeCorsModule
    if name == "starlette.requests":
        return FakeRequestsModule
    if name == "fastapi.exceptions":
        return FakeValidationModule
    if name == "fastapi.exception_handlers":
        return FakeExceptionHandlersModule
    if name == "fastapi.responses":
        return FakeResponsesModule
    if name == "starlette.staticfiles":
        return FakeStaticFilesModule
    raise AssertionError(f"unexpected import: {name}")


class FakeConnection:
    harness_id = HarnessId.CODEX
    state = "connected"
    capabilities = ConnectionCapabilities(
        mid_turn_injection="queue",
        supports_steer=True,
        supports_interrupt=True,
        supports_cancel=True,
        runtime_model_switch=False,
        structured_reasoning=False,
    )


class FakeManager:
    def __init__(
        self,
        *,
        state_root: Path,
        repo_root: Path,
        completion_ready: asyncio.Event,
        wait_calls: list[SpawnId],
        heartbeat_calls: list[SpawnId],
    ) -> None:
        self.state_root = state_root
        self.repo_root = repo_root
        self._completion_ready = completion_ready
        self._wait_calls = wait_calls
        self._heartbeat_calls = heartbeat_calls
        self.inject_calls: list[tuple[SpawnId, str, str]] = []
        self.interrupt_calls: list[tuple[SpawnId, str]] = []
        self.inject_result = types.SimpleNamespace(success=True, error=None, inbound_seq=2)
        self.interrupt_result = types.SimpleNamespace(
            success=True,
            error=None,
            inbound_seq=3,
            noop=False,
        )
        self._connections: dict[SpawnId, object] = {}

    async def start_spawn(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec | None = None,
    ) -> FakeConnection:
        _ = spec
        connection = FakeConnection()
        self._connections[config.spawn_id] = connection
        return connection

    async def _start_heartbeat(self, spawn_id: SpawnId) -> None:
        self._heartbeat_calls.append(spawn_id)

    async def wait_for_completion(self, spawn_id: SpawnId) -> DrainOutcome | None:
        self._wait_calls.append(spawn_id)
        await self._completion_ready.wait()
        return DrainOutcome(
            status="succeeded",
            exit_code=0,
            duration_secs=2.5,
        )

    async def shutdown(
        self,
        *,
        status: str = "cancelled",
        exit_code: int = 1,
        error: str | None = None,
    ) -> None:
        _ = status, exit_code, error

    def list_spawns(self) -> list[SpawnId]:
        return []

    def get_connection(self, spawn_id: SpawnId) -> object | None:
        return self._connections.get(spawn_id)

    async def inject(self, spawn_id: SpawnId, message: str, source: str = "rest") -> object:
        self.inject_calls.append((spawn_id, message, source))
        return self.inject_result

    async def interrupt(self, spawn_id: SpawnId, source: str = "rest") -> object:
        self.interrupt_calls.append((spawn_id, source))
        return self.interrupt_result

    def set_connection(self, spawn_id: SpawnId, connection: object | None) -> None:
        if connection is None:
            self._connections.pop(spawn_id, None)
            return
        self._connections[spawn_id] = connection


def _read_spawn_events(state_root: Path) -> list[dict[str, object]]:
    events_path = state_root / "spawns.jsonl"
    return [
        cast("dict[str, object]", json.loads(line))
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


async def _wait_until(predicate: Callable[[], bool], *, attempts: int = 200) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("timed out waiting for condition")


def _create_test_app(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    completion_ready: asyncio.Event,
    wait_calls: list[SpawnId],
    heartbeat_calls: list[SpawnId],
    allow_unsafe_no_permissions: bool = False,
) -> tuple[FakeApp, FakeManager]:
    fake_ws_module = types.SimpleNamespace(
        register_ws_routes=lambda app_obj, manager, validate_spawn_id=None: None
    )
    monkeypatch.setitem(sys.modules, "meridian.lib.app.ws_endpoint", fake_ws_module)
    monkeypatch.setattr(server_module, "import_module", _fake_import_module)

    manager = FakeManager(
        state_root=resolve_state_paths(tmp_path).root_dir,
        repo_root=tmp_path,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )
    app_obj = server_module.create_app(
        cast("Any", manager),
        allow_unsafe_no_permissions=allow_unsafe_no_permissions,
    )
    return cast("FakeApp", app_obj), manager


def _create_spawn_handler(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    completion_ready: asyncio.Event,
    wait_calls: list[SpawnId],
    heartbeat_calls: list[SpawnId],
    allow_unsafe_no_permissions: bool = False,
) -> Callable[[server_module.SpawnCreateRequest], Any]:
    app, _manager = _create_test_app(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
        allow_unsafe_no_permissions=allow_unsafe_no_permissions,
    )
    return cast("Callable[[server_module.SpawnCreateRequest], Any]", app.post_routes["/api/spawns"])


def _start_running_app_spawn(state_root: Path, spawn_id: str = "p1") -> SpawnId:
    created = spawn_store.start_spawn(
        state_root,
        chat_id="chat",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        spawn_id=spawn_id,
        launch_mode="app",
        status="running",
    )
    return SpawnId(created)


@pytest.mark.asyncio
async def test_app_server_create_spawn_background_finalizer_writes_finalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []
    create_spawn_handler = _create_spawn_handler(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    payload = server_module.SpawnCreateRequest(
        harness="codex",
        prompt="hello",
        permissions=server_module.PermissionRequest(
            sandbox="workspace-write",
            approval="confirm",
        ),
    )
    response = await create_spawn_handler(payload)
    assert response["spawn_id"] == "p1"

    completion_ready.set()
    await _wait_until(lambda: len(_read_spawn_events(state_root)) == 2)

    events = _read_spawn_events(state_root)
    assert [event["event"] for event in events] == ["start", "finalize"]
    assert events[-1]["status"] == "succeeded"
    assert events[-1]["exit_code"] == 0
    assert events[-1]["duration_secs"] == 2.5
    assert events[-1]["origin"] == "runner"
    assert wait_calls == [SpawnId("p1")]
    assert heartbeat_calls == [SpawnId("p1")]

    row = get_spawn(state_root, "p1")
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.duration_secs == 2.5
    assert row.launch_mode == "app"
    assert row.runner_pid == os.getpid()


@pytest.mark.asyncio
async def test_app_server_rejects_missing_permissions_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []
    create_spawn_handler = _create_spawn_handler(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    with pytest.raises(FakeHTTPException) as exc_info:
        await create_spawn_handler(
            server_module.SpawnCreateRequest(
                harness="codex",
                prompt="hello",
            )
        )

    assert exc_info.value.status_code == 400
    assert "permissions block is required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_app_server_allows_unsafe_no_permissions_when_opted_in(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []
    create_spawn_handler = _create_spawn_handler(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
        allow_unsafe_no_permissions=True,
    )

    with caplog.at_level("WARNING"):
        response = await create_spawn_handler(
            server_module.SpawnCreateRequest(
                harness="codex",
                prompt="hello",
            )
        )

    assert response["spawn_id"] == "p1"
    assert "allow-unsafe-no-permissions" in caplog.text
    assert "UnsafeNoOpPermissionResolver constructed" in caplog.text

    completion_ready.set()
    await _wait_until(lambda: len(_read_spawn_events(state_root)) == 2)
    assert wait_calls == [SpawnId("p1")]


@pytest.mark.asyncio
async def test_app_server_threads_permission_resolver_into_streaming_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []

    class _CaptureAdapter(CodexAdapter):
        """CodexAdapter subclass that captures the permission resolver."""

        def __init__(self) -> None:
            super().__init__()
            self.seen_resolver: object | None = None

        def resolve_launch_spec(self, run: SpawnParams, perms: object) -> ResolvedLaunchSpec:
            self.seen_resolver = perms
            return super().resolve_launch_spec(run, cast("Any", perms))

    class _CaptureRegistry:
        def __init__(self, adapter: _CaptureAdapter) -> None:
            self._adapter = adapter

        def get_subprocess_harness(self, harness_id: HarnessId) -> _CaptureAdapter:
            _ = harness_id
            return self._adapter

    adapter = _CaptureAdapter()
    registry = _CaptureRegistry(adapter)
    monkeypatch.setattr(server_module, "get_default_harness_registry", lambda: registry)
    create_spawn_handler = _create_spawn_handler(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    await create_spawn_handler(
        server_module.SpawnCreateRequest(
            harness="codex",
            prompt="hello",
            permissions=server_module.PermissionRequest(
                sandbox="read-only",
                approval="auto",
            ),
        )
    )

    resolver = adapter.seen_resolver
    assert resolver is not None
    assert cast("Any", resolver).config.sandbox == "read-only"
    assert cast("Any", resolver).config.approval == "auto"


@pytest.mark.asyncio
async def test_app_server_start_spawn_failure_tags_launch_failure_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []

    async def _raising_start_spawn(
        self: FakeManager,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec | None = None,
    ) -> FakeConnection:
        _ = self, config, spec
        raise RuntimeError("start failed")

    monkeypatch.setattr(FakeManager, "start_spawn", _raising_start_spawn)
    create_spawn_handler = _create_spawn_handler(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    with pytest.raises(FakeHTTPException) as exc_info:
        await create_spawn_handler(
            server_module.SpawnCreateRequest(
                harness="codex",
                prompt="hello",
                permissions=server_module.PermissionRequest(
                    sandbox="workspace-write",
                    approval="confirm",
                ),
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "start failed"
    assert wait_calls == []
    events = _read_spawn_events(state_root)
    assert [event["event"] for event in events] == ["start", "finalize"]
    assert events[-1]["status"] == "failed"
    assert events[-1]["origin"] == "launch_failure"


@pytest.mark.asyncio
async def test_inject_text_routes_to_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []
    app, manager = _create_test_app(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    spawn_id = _start_running_app_spawn(manager.state_root, spawn_id="p1")
    manager.set_connection(spawn_id, FakeConnection())
    inject_handler = cast("Any", app.post_routes["/api/spawns/{spawn_id}/inject"])

    response = await inject_handler(
        "p1",
        server_module.InjectRequest(text="hello"),
    )

    assert response == {"ok": True, "inbound_seq": 2}
    assert manager.inject_calls == [(SpawnId("p1"), "hello", "rest")]
    assert manager.interrupt_calls == []


@pytest.mark.asyncio
async def test_inject_interrupt_dispatches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []
    app, manager = _create_test_app(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    _start_running_app_spawn(manager.state_root, spawn_id="p1")
    manager.set_connection(SpawnId("p1"), FakeConnection())
    manager.interrupt_result = types.SimpleNamespace(
        success=True,
        error=None,
        inbound_seq=9,
        noop=True,
    )
    inject_handler = cast("Any", app.post_routes["/api/spawns/{spawn_id}/inject"])

    response = await inject_handler(
        "p1",
        server_module.InjectRequest(interrupt=True),
    )

    assert response == {"ok": True, "inbound_seq": 9, "noop": True}
    assert manager.interrupt_calls == [(SpawnId("p1"), "rest")]
    assert manager.inject_calls == []


@pytest.mark.asyncio
async def test_inject_rejects_terminal_and_finalizing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []
    app, manager = _create_test_app(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    terminal_id = _start_running_app_spawn(manager.state_root, spawn_id="p1")
    manager.set_connection(terminal_id, FakeConnection())
    spawn_store.finalize_spawn(
        manager.state_root,
        terminal_id,
        status="failed",
        exit_code=1,
        origin="runner",
        error="boom",
    )

    inject_handler = cast("Any", app.post_routes["/api/spawns/{spawn_id}/inject"])
    with pytest.raises(FakeHTTPException) as terminal_exc:
        await inject_handler(
            "p1",
            server_module.InjectRequest(text="hello"),
        )
    assert terminal_exc.value.status_code == 410
    assert terminal_exc.value.detail == "spawn already terminal"

    finalizing_id = _start_running_app_spawn(manager.state_root, spawn_id="p2")
    manager.set_connection(finalizing_id, FakeConnection())
    assert spawn_store.mark_finalizing(manager.state_root, finalizing_id) is True

    with pytest.raises(FakeHTTPException) as finalizing_exc:
        await inject_handler(
            "p2",
            server_module.InjectRequest(text="hello"),
        )
    assert finalizing_exc.value.status_code == 503
    assert finalizing_exc.value.detail == "spawn is finalizing"


@pytest.mark.asyncio
async def test_cancel_endpoint_returns_origin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []
    app, manager = _create_test_app(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    spawn_id = _start_running_app_spawn(manager.state_root, spawn_id="p1")

    class _FakeCanceller:
        def __init__(self, *, state_root: Path, manager: FakeManager) -> None:
            _ = state_root, manager

        async def cancel(self, cancel_spawn_id: SpawnId) -> CancelOutcome:
            assert cancel_spawn_id == spawn_id
            return CancelOutcome(status="cancelled", origin="runner", exit_code=143)

    monkeypatch.setattr(server_module, "SignalCanceller", _FakeCanceller)

    cancel_handler = cast("Any", app.post_routes["/api/spawns/{spawn_id}/cancel"])
    response = await cancel_handler("p1")
    assert response == {"ok": True, "status": "cancelled", "origin": "runner"}


@pytest.mark.asyncio
async def test_cancel_endpoint_rejects_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []
    app, manager = _create_test_app(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    terminal_id = _start_running_app_spawn(manager.state_root, spawn_id="p1")
    spawn_store.finalize_spawn(
        manager.state_root,
        terminal_id,
        status="cancelled",
        exit_code=143,
        origin="runner",
        error="cancelled",
    )

    cancel_handler = cast("Any", app.post_routes["/api/spawns/{spawn_id}/cancel"])
    with pytest.raises(FakeHTTPException) as cancel_exc:
        await cancel_handler("p1")
    assert cancel_exc.value.status_code == 409
    assert cancel_exc.value.detail == "spawn already terminal: cancelled"


@pytest.mark.asyncio
async def test_validation_error_handler_maps_only_mutually_exclusive_value_errors_to_400(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    heartbeat_calls: list[SpawnId] = []
    app, _manager = _create_test_app(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
        heartbeat_calls=heartbeat_calls,
    )

    handler = cast(
        "Callable[[object, FakeRequestValidationError], Any]",
        app.exception_handlers[FakeRequestValidationError],
    )

    semantic_response = await handler(
        object(),
        FakeRequestValidationError(
            [{"ctx": {"error": ValueError("text and interrupt are mutually exclusive")}}]
        ),
    )
    assert isinstance(semantic_response, FakeJSONResponse)
    assert semantic_response.status_code == 400
    assert semantic_response.content == {
        "detail": "text and interrupt are mutually exclusive"
    }

    fallback_value_error_response = await handler(
        object(),
        FakeRequestValidationError(
            [{"ctx": {"error": ValueError("provide text or interrupt: true")}}]
        ),
    )
    assert fallback_value_error_response["status_code"] == 422
    fallback_detail = cast("list[dict[str, object]]", fallback_value_error_response["detail"])
    assert len(fallback_detail) == 1
    fallback_ctx = cast("dict[str, object]", fallback_detail[0]["ctx"])
    fallback_error = fallback_ctx["error"]
    assert isinstance(fallback_error, ValueError)
    assert str(fallback_error) == "provide text or interrupt: true"

    schema_response = await handler(object(), FakeRequestValidationError([{"type": "missing"}]))
    assert schema_response == {"status_code": 422, "detail": [{"type": "missing"}]}
