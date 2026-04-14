from __future__ import annotations

import asyncio
import json
import sys
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from meridian.lib.app import server as server_module
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.connections.base import ConnectionCapabilities, ConnectionConfig
from meridian.lib.harness.launch_spec import ResolvedLaunchSpec
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.spawn_store import get_spawn
from meridian.lib.streaming.spawn_manager import DrainOutcome


class FakeHTTPException(Exception):
    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FakeApp:
    def __init__(self, *, title: str, lifespan: object) -> None:
        self.title = title
        self.lifespan = lifespan
        self.state = types.SimpleNamespace()
        self.post_routes: dict[str, object] = {}
        self.get_routes: dict[str, object] = {}
        self.delete_routes: dict[str, object] = {}

    def add_middleware(self, middleware_class: type[object], **kwargs: object) -> None:
        _ = middleware_class, kwargs

    def post(self, path: str):
        def decorator(handler: object) -> object:
            self.post_routes[path] = handler
            return handler

        return decorator

    def get(self, path: str):
        def decorator(handler: object) -> object:
            self.get_routes[path] = handler
            return handler

        return decorator

    def delete(self, path: str):
        def decorator(handler: object) -> object:
            self.delete_routes[path] = handler
            return handler

        return decorator

    def mount(self, path: str, app: object, name: str | None = None) -> None:
        _ = path, app, name


class FakeFastAPIModule:
    HTTPException = FakeHTTPException

    @staticmethod
    def FastAPI(*, title: str, lifespan: object) -> object:
        return FakeApp(title=title, lifespan=lifespan)


class FakeCorsModule:
    CORSMiddleware = object


class FakeStaticFilesModule:
    class StaticFiles:
        def __init__(self, **kwargs: object) -> None:
            _ = kwargs


def _fake_import_module(name: str) -> object:
    if name == "fastapi":
        return FakeFastAPIModule
    if name == "fastapi.middleware.cors":
        return FakeCorsModule
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
    ) -> None:
        self.state_root = state_root
        self.repo_root = repo_root
        self._completion_ready = completion_ready
        self._wait_calls = wait_calls

    async def start_spawn(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec | None = None,
    ) -> FakeConnection:
        _ = config, spec
        return FakeConnection()

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

    def get_connection(self, spawn_id: SpawnId) -> None:
        _ = spawn_id
        return None

    async def inject(self, spawn_id: SpawnId, message: str, source: str = "rest") -> object:
        _ = spawn_id, message, source
        return types.SimpleNamespace(success=True, error=None)

    async def cancel(self, spawn_id: SpawnId, source: str = "rest") -> object:
        _ = spawn_id, source
        return types.SimpleNamespace(success=True, error=None)


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


def _create_spawn_handler(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    completion_ready: asyncio.Event,
    wait_calls: list[SpawnId],
    allow_unsafe_no_permissions: bool = False,
) -> Callable[[server_module.SpawnCreateRequest], Any]:
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
    )
    app_obj = server_module.create_app(
        cast("Any", manager),
        allow_unsafe_no_permissions=allow_unsafe_no_permissions,
    )
    app = cast("Any", app_obj)
    return cast("Callable[[server_module.SpawnCreateRequest], Any]", app.post_routes["/api/spawns"])


@pytest.mark.asyncio
async def test_app_server_create_spawn_background_finalizer_writes_finalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    create_spawn_handler = _create_spawn_handler(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
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
    assert events[-1]["origin"] == "launcher"
    assert wait_calls == [SpawnId("p1")]

    row = get_spawn(state_root, "p1")
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.duration_secs == 2.5


@pytest.mark.asyncio
async def test_app_server_rejects_missing_permissions_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []
    create_spawn_handler = _create_spawn_handler(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
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
    create_spawn_handler = _create_spawn_handler(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        completion_ready=completion_ready,
        wait_calls=wait_calls,
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

    class _CaptureAdapter:
        def __init__(self) -> None:
            self.seen_resolver: object | None = None

        def resolve_launch_spec(self, run: SpawnParams, perms: object) -> ResolvedLaunchSpec:
            self.seen_resolver = perms
            return ResolvedLaunchSpec(prompt=run.prompt, permission_resolver=cast("Any", perms))

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
