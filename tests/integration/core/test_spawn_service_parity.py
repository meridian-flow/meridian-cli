"""GATE TEST: service-vs-surface parity for spawn cancellation/finalization."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from meridian.lib.app.spawn_routes import register_spawn_routes
from meridian.lib.config.project_paths import resolve_project_config_paths
from meridian.lib.core.lifecycle import SpawnLifecycleService
from meridian.lib.core.spawn_service import SpawnApplicationService
from meridian.lib.core.types import SpawnId
from meridian.lib.ops.runtime import resolve_runtime_root
from meridian.lib.ops.spawn.api import spawn_cancel
from meridian.lib.ops.spawn.models import SpawnCancelInput
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import RuntimePaths
from meridian.lib.state.spawn.repository import FileSpawnRepository
from meridian.lib.streaming.signal_canceller import CancelOutcome as SignalCancelOutcome


class _FakeSpawnManager:
    def get_connection(self, spawn_id: SpawnId) -> object | None:
        _ = spawn_id
        return None

    def list_spawns(self) -> list[SpawnId]:
        return []

    async def inject(self, spawn_id: SpawnId, text: str, source: str = "rest") -> object:
        _ = (spawn_id, text, source)
        raise AssertionError("inject must not be called in this parity test")

    async def wait_for_completion(self, spawn_id: SpawnId) -> None:
        _ = spawn_id
        return None

    async def stop_spawn(
        self,
        spawn_id: SpawnId,
        *,
        status: str = "cancelled",
        exit_code: int = 1,
        error: str | None = None,
    ) -> None:
        _ = (spawn_id, status, exit_code, error)
        raise AssertionError("stop_spawn must not be called in this parity test")

    async def start_spawn(self, *args: object, **kwargs: object) -> object:
        _ = (args, kwargs)
        raise AssertionError("start_spawn must not be called in this parity test")

    async def _start_heartbeat(self, spawn_id: SpawnId) -> None:
        _ = spawn_id
        return None


def _seed_running_spawn(project_root: Path, *, spawn_id: str = "p1") -> tuple[Path, SpawnId]:
    runtime_root = resolve_runtime_root(project_root)
    lifecycle = SpawnLifecycleService(runtime_root)
    created_spawn_id = SpawnId(
        lifecycle.start(
            chat_id="chat-1",
            model="gpt-5.4",
            agent="coder",
            harness="codex",
            kind="child",
            prompt="hello",
            spawn_id=spawn_id,
            launch_mode="foreground",
            runner_pid=None,
            status="running",
        )
    )
    return runtime_root, created_spawn_id


def _build_http_client(project_root: Path) -> tuple[TestClient, Path, SpawnId]:
    runtime_root, spawn_id = _seed_running_spawn(project_root)
    lifecycle = SpawnLifecycleService(runtime_root)
    app = FastAPI()
    register_spawn_routes(
        app,
        _FakeSpawnManager(),
        runtime_root=runtime_root,
        project_paths=resolve_project_config_paths(project_root=project_root),
        lifecycle_service=lifecycle,
        spawn_id_lock=asyncio.Lock(),
        background_finalize_tasks=set(),
        http_exception=HTTPException,
    )
    return TestClient(app), runtime_root, spawn_id


def _terminal_snapshot(runtime_root: Path, spawn_id: SpawnId) -> dict[str, object | None]:
    record = spawn_store.get_spawn(runtime_root, spawn_id)
    assert record is not None
    return {
        "spawn_id": str(spawn_id),
        "status": record.status,
        "terminal_origin": record.terminal_origin,
        "exit_code": record.exit_code,
        "model": record.model,
        "harness": record.harness,
    }


def _finalize_event_count(runtime_root: Path) -> int:
    events = FileSpawnRepository(RuntimePaths.from_root_dir(runtime_root)).read_events()
    return sum(1 for event in events if event.event == "finalize")


@pytest.mark.asyncio
async def test_http_cancel_and_cli_cancel_match_for_running_spawn_state(
    tmp_path: Path,
) -> None:
    http_project_root = tmp_path / "http"
    cli_project_root = tmp_path / "cli"

    http_client, http_runtime_root, http_spawn_id = _build_http_client(http_project_root)
    cli_runtime_root, cli_spawn_id = _seed_running_spawn(cli_project_root)

    http_response = http_client.post(f"/api/spawns/{http_spawn_id}/cancel")
    assert http_response.status_code == 200
    assert http_response.json() == {"ok": True, "status": "cancelled", "origin": "cancel"}

    cli_output = await spawn_cancel(
        SpawnCancelInput(
            spawn_id=str(cli_spawn_id),
            project_root=cli_project_root.as_posix(),
        )
    )

    assert cli_output.status == "cancelled"
    assert cli_output.exit_code == 130
    assert cli_output.message == "Spawn cancelled."

    assert _terminal_snapshot(http_runtime_root, http_spawn_id) == _terminal_snapshot(
        cli_runtime_root,
        cli_spawn_id,
    )


@pytest.mark.asyncio
async def test_complete_spawn_idempotence_holds_with_full_service_setup(
    tmp_path: Path,
) -> None:
    runtime_root, spawn_id = _seed_running_spawn(tmp_path / "service")
    lifecycle = SpawnLifecycleService(runtime_root)
    service = SpawnApplicationService(runtime_root, lifecycle)

    first = await service.complete_spawn(spawn_id, "succeeded", 0, origin="runner")
    second = await service.complete_spawn(spawn_id, "failed", 1, origin="cancel")

    record = spawn_store.get_spawn(runtime_root, spawn_id)
    assert first is True
    assert second is False
    assert record is not None
    assert record.status == "succeeded"
    assert record.exit_code == 0
    assert record.terminal_origin == "runner"
    assert _finalize_event_count(runtime_root) == 1


@pytest.mark.asyncio
async def test_concurrent_cancel_and_finalize_attempts_do_not_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_root, spawn_id = _seed_running_spawn(tmp_path / "race")
    lifecycle = SpawnLifecycleService(runtime_root)
    service = SpawnApplicationService(runtime_root, lifecycle)

    started = asyncio.Event()
    release = asyncio.Event()

    class _PausingSignalCanceller:
        def __init__(self, *args: object, **kwargs: object) -> None:
            _ = (args, kwargs)

        async def cancel(self, target_spawn_id: SpawnId) -> SignalCancelOutcome:
            assert target_spawn_id == spawn_id
            started.set()
            await release.wait()
            spawn_store.finalize_spawn(
                runtime_root,
                target_spawn_id,
                status="cancelled",
                exit_code=130,
                origin="cancel",
                error="cancelled",
            )
            return SignalCancelOutcome(status="cancelled", origin="cancel", exit_code=130)

    monkeypatch.setattr(
        "meridian.lib.streaming.signal_canceller.SignalCanceller",
        _PausingSignalCanceller,
    )

    cancel_task = asyncio.create_task(service.cancel(spawn_id))
    await started.wait()
    finalize_task = asyncio.create_task(
        service.complete_spawn(spawn_id, "succeeded", 0, origin="runner")
    )
    await asyncio.sleep(0)
    release.set()

    cancel_outcome, finalize_result = await asyncio.gather(cancel_task, finalize_task)

    record = spawn_store.get_spawn(runtime_root, spawn_id)
    assert cancel_outcome.status == "cancelled"
    assert cancel_outcome.origin == "cancel"
    assert cancel_outcome.exit_code == 130
    assert finalize_result is False
    assert record is not None
    assert record.status == "cancelled"
    assert record.exit_code == 130
    assert record.terminal_origin == "cancel"
    assert _finalize_event_count(runtime_root) == 1
