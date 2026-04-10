from __future__ import annotations

# pyright: reportPrivateUsage=false
import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    HarnessEvent,
)
from meridian.lib.harness.launch_spec import ResolvedLaunchSpec
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.spawn_store import get_spawn, start_spawn
from meridian.lib.streaming import spawn_manager as spawn_manager_module
from meridian.lib.streaming.spawn_manager import SpawnManager


def _read_output_lines(state_root: Path, spawn_id: str) -> list[dict[str, object]]:
    output_path = state_root / "spawns" / spawn_id / "output.jsonl"
    return [
        cast("dict[str, object]", json.loads(line))
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _read_spawn_events(state_root: Path) -> list[dict[str, object]]:
    spawns_path = state_root / "spawns.jsonl"
    return [
        cast("dict[str, object]", json.loads(line))
        for line in spawns_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _build_config(spawn_id: str, repo_root: Path) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=spawn_id,
        harness_id=HarnessId.CODEX,
        model="gpt-5.3-codex",
        prompt="hello",
        repo_root=repo_root,
        env_overrides={},
    )


async def _wait_until(predicate: Callable[[], bool], *, attempts: int = 200) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("timed out waiting for condition")


@pytest.mark.asyncio
async def test_spawn_manager_natural_completion_writes_envelope_and_completion_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    release_completion = asyncio.Event()
    stop_called = asyncio.Event()

    class FakeControlSocketServer:
        def __init__(self, spawn_id: str, socket_path: Path, manager: SpawnManager) -> None:
            _ = spawn_id, manager
            self.socket_path = socket_path

        async def start(self) -> None:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        async def stop(self) -> None:
            pass

    class FakeConnection:
        def __init__(self) -> None:
            self._spawn_id = ""
            self.state = "created"
            self.stop_calls = 0
            self.capabilities = ConnectionCapabilities(
                mid_turn_injection="queue",
                supports_steer=True,
                supports_interrupt=True,
                supports_cancel=True,
                runtime_model_switch=False,
                structured_reasoning=False,
            )

        @property
        def harness_id(self) -> HarnessId:
            return HarnessId.CODEX

        @property
        def spawn_id(self) -> str:
            return self._spawn_id

        async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
            _ = spec
            self._spawn_id = config.spawn_id
            self.state = "connected"

        async def stop(self) -> None:
            self.stop_calls += 1
            self.state = "stopped"
            stop_called.set()

        def health(self) -> bool:
            return True

        async def send_user_message(self, text: str) -> None:
            _ = text

        async def send_interrupt(self) -> None:
            return None

        async def send_cancel(self) -> None:
            return None

        async def events(self):  # type: ignore[no-untyped-def]
            yield HarnessEvent(
                event_type="item.completed",
                harness_id="codex",
                payload={"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
            )
            await release_completion.wait()

    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        lambda harness_id: FakeConnection,
    )

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        kind="streaming",
        prompt="hello",
        launch_mode="foreground",
        status="running",
    )
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    await manager.start_spawn(
        _build_config(spawn_id, repo_root),
        ResolvedLaunchSpec(prompt="hello"),
    )
    completion_task = asyncio.create_task(manager.wait_for_completion(spawn_id))
    release_completion.set()
    completion = await completion_task
    assert completion is not None
    await _wait_until(
        lambda: get_spawn(state_root, spawn_id) is not None
        and manager.get_connection(spawn_id) is None
        and stop_called.is_set()
    )
    assert completion.status == "succeeded"
    assert completion.exit_code == 0
    assert completion.error is None
    assert completion.duration_secs >= 0.0

    output = _read_output_lines(state_root, spawn_id)
    assert output == [
        {
            "event_type": "item.completed",
            "harness_id": "codex",
            "payload": {"item": {"text": "hi", "type": "agent_message"}, "type": "item.completed"},
        }
    ]

    spawn_events = _read_spawn_events(state_root)
    assert [event["event"] for event in spawn_events] == ["start"]

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "running"
    assert row.exit_code is None


@pytest.mark.asyncio
async def test_spawn_manager_wait_for_completion_after_natural_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    cleanup_finished = asyncio.Event()

    class FakeControlSocketServer:
        def __init__(self, spawn_id: str, socket_path: Path, manager: SpawnManager) -> None:
            _ = spawn_id, manager
            self.socket_path = socket_path

        async def start(self) -> None:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        async def stop(self) -> None:
            pass

    class FakeConnection:
        def __init__(self) -> None:
            self._spawn_id = ""
            self.state = "created"
            self.capabilities = ConnectionCapabilities(
                mid_turn_injection="queue",
                supports_steer=True,
                supports_interrupt=True,
                supports_cancel=True,
                runtime_model_switch=False,
                structured_reasoning=False,
            )

        @property
        def harness_id(self) -> HarnessId:
            return HarnessId.CODEX

        @property
        def spawn_id(self) -> str:
            return self._spawn_id

        async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
            _ = spec
            self._spawn_id = config.spawn_id
            self.state = "connected"

        async def stop(self) -> None:
            self.state = "stopped"

        def health(self) -> bool:
            return True

        async def send_user_message(self, text: str) -> None:
            _ = text

        async def send_interrupt(self) -> None:
            return None

        async def send_cancel(self) -> None:
            return None

        async def events(self):  # type: ignore[no-untyped-def]
            yield HarnessEvent(
                event_type="item.completed",
                harness_id="codex",
                payload={
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "done"},
                },
            )

    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        lambda harness_id: FakeConnection,
    )

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        kind="streaming",
        prompt="hello",
        launch_mode="foreground",
        status="running",
    )
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    original_cleanup = manager._cleanup_completed_session

    async def tracked_cleanup(spawn_id: SpawnId) -> None:
        await original_cleanup(spawn_id)
        cleanup_finished.set()

    monkeypatch.setattr(manager, "_cleanup_completed_session", tracked_cleanup)
    await manager.start_spawn(_build_config(spawn_id, repo_root))

    await cleanup_finished.wait()
    assert manager.get_connection(spawn_id) is None
    completion = await manager.wait_for_completion(spawn_id)
    assert completion is not None
    assert completion.status == "succeeded"
    assert completion.exit_code == 0


@pytest.mark.asyncio
async def test_spawn_manager_stop_spawn_returns_cancelled_outcome_without_finalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir

    class FakeControlSocketServer:
        def __init__(self, spawn_id: str, socket_path: Path, manager: SpawnManager) -> None:
            _ = spawn_id, manager
            self.socket_path = socket_path
            self.stopped = False

        async def start(self) -> None:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        async def stop(self) -> None:
            self.stopped = True

    class FakeConnection:
        def __init__(self) -> None:
            self._spawn_id = ""
            self.state = "created"
            self.capabilities = ConnectionCapabilities(
                mid_turn_injection="queue",
                supports_steer=True,
                supports_interrupt=True,
                supports_cancel=True,
                runtime_model_switch=False,
                structured_reasoning=False,
            )
            self.stop_calls = 0

        @property
        def harness_id(self) -> HarnessId:
            return HarnessId.CODEX

        @property
        def spawn_id(self) -> str:
            return self._spawn_id

        async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
            _ = spec
            self._spawn_id = config.spawn_id
            self.state = "connected"

        async def stop(self) -> None:
            self.stop_calls += 1
            self.state = "stopped"

        def health(self) -> bool:
            return True

        async def send_user_message(self, text: str) -> None:
            _ = text

        async def send_interrupt(self) -> None:
            return None

        async def send_cancel(self) -> None:
            return None

        async def events(self):  # type: ignore[no-untyped-def]
            while True:
                await asyncio.sleep(3600)

    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        lambda harness_id: FakeConnection,
    )

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        kind="streaming",
        prompt="hello",
        launch_mode="foreground",
        status="running",
    )
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    await manager.start_spawn(_build_config(spawn_id, repo_root))
    completion_task = asyncio.create_task(manager.wait_for_completion(spawn_id))

    outcome = await manager.stop_spawn(spawn_id, status="cancelled", exit_code=1)
    completion = await completion_task
    assert outcome is not None
    assert completion is not None
    assert outcome == completion
    assert outcome.status == "cancelled"
    assert outcome.exit_code == 1
    assert outcome.error is None
    assert outcome.duration_secs >= 0.0

    spawn_events = _read_spawn_events(state_root)
    assert [event["event"] for event in spawn_events] == ["start"]

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "running"
    assert row.exit_code is None
    assert manager.get_connection(spawn_id) is None


@pytest.mark.asyncio
async def test_spawn_manager_stop_spawn_race_uses_natural_completion_outcome_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()

    class FakeControlSocketServer:
        def __init__(self, spawn_id: str, socket_path: Path, manager: SpawnManager) -> None:
            _ = spawn_id, manager
            self.socket_path = socket_path

        async def start(self) -> None:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        async def stop(self) -> None:
            pass

    class FakeConnection:
        def __init__(self) -> None:
            self._spawn_id = ""
            self.state = "created"
            self.capabilities = ConnectionCapabilities(
                mid_turn_injection="queue",
                supports_steer=True,
                supports_interrupt=True,
                supports_cancel=True,
                runtime_model_switch=False,
                structured_reasoning=False,
            )

        @property
        def harness_id(self) -> HarnessId:
            return HarnessId.CODEX

        @property
        def spawn_id(self) -> str:
            return self._spawn_id

        async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
            _ = spec
            self._spawn_id = config.spawn_id
            self.state = "connected"

        async def stop(self) -> None:
            self.state = "stopped"

        def health(self) -> bool:
            return True

        async def send_user_message(self, text: str) -> None:
            _ = text

        async def send_interrupt(self) -> None:
            return None

        async def send_cancel(self) -> None:
            return None

        async def events(self):  # type: ignore[no-untyped-def]
            if False:
                yield
            return

    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        lambda harness_id: FakeConnection,
    )

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        kind="streaming",
        prompt="hello",
        launch_mode="foreground",
        status="running",
    )
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    original_cleanup = manager._cleanup_completed_session

    async def gated_cleanup(spawn_id: SpawnId) -> None:
        cleanup_started.set()
        await release_cleanup.wait()
        await original_cleanup(spawn_id)

    monkeypatch.setattr(manager, "_cleanup_completed_session", gated_cleanup)

    await manager.start_spawn(_build_config(spawn_id, repo_root))
    await cleanup_started.wait()

    completion = await manager.wait_for_completion(spawn_id)
    outcome = await manager.stop_spawn(spawn_id, status="cancelled", exit_code=1)
    release_cleanup.set()
    await asyncio.sleep(0)
    assert completion is not None
    assert completion.status == "succeeded"
    assert completion.exit_code == 0
    assert outcome == completion

    spawn_events = _read_spawn_events(state_root)
    assert [event["event"] for event in spawn_events] == ["start"]

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "running"
    assert row.exit_code is None
