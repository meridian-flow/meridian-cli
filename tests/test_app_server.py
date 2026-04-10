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
from meridian.lib.harness.connections.base import ConnectionCapabilities, ConnectionConfig
from meridian.lib.harness.launch_spec import ResolvedLaunchSpec
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.spawn_store import get_spawn
from meridian.lib.streaming.spawn_manager import DrainOutcome


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


@pytest.mark.asyncio
async def test_app_server_create_spawn_background_finalizer_writes_finalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    completion_ready = asyncio.Event()
    wait_calls: list[SpawnId] = []

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

    def fake_import_module(name: str) -> object:
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
        def __init__(self, *, state_root: Path, repo_root: Path) -> None:
            self.state_root = state_root
            self.repo_root = repo_root

        async def start_spawn(
            self,
            config: ConnectionConfig,
            spec: ResolvedLaunchSpec | None = None,
        ) -> FakeConnection:
            _ = config, spec
            return FakeConnection()

        async def wait_for_completion(self, spawn_id: SpawnId) -> DrainOutcome | None:
            wait_calls.append(spawn_id)
            await completion_ready.wait()
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

    fake_ws_module = types.SimpleNamespace(
        register_ws_routes=lambda app_obj, manager, validate_spawn_id=None: None
    )

    monkeypatch.setitem(sys.modules, "meridian.lib.app.ws_endpoint", fake_ws_module)
    monkeypatch.setattr(server_module, "import_module", fake_import_module)

    manager = FakeManager(state_root=state_root, repo_root=repo_root)
    app_obj = server_module.create_app(cast("Any", manager))
    app = cast("Any", app_obj)
    create_spawn_handler = cast(
        "Callable[[server_module.SpawnCreateRequest], Any]",
        app.post_routes["/api/spawns"],
    )

    payload = server_module.SpawnCreateRequest(harness="codex", prompt="hello")
    response = await create_spawn_handler(payload)
    assert response["spawn_id"] == "p1"

    completion_ready.set()
    await _wait_until(lambda: len(_read_spawn_events(state_root)) == 2)

    events = _read_spawn_events(state_root)
    assert [event["event"] for event in events] == ["start", "finalize"]
    assert events[-1]["status"] == "succeeded"
    assert events[-1]["exit_code"] == 0
    assert events[-1]["duration_secs"] == 2.5
    assert wait_calls == [SpawnId("p1")]

    row = get_spawn(state_root, "p1")
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.duration_secs == 2.5
