from __future__ import annotations

# pyright: reportPrivateUsage=false
import asyncio
import json
from collections.abc import Callable
from dataclasses import fields
from pathlib import Path
from typing import cast

import pytest

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.bundle import _REGISTRY, HarnessBundle, get_harness_bundle
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    HarnessEvent,
)
from meridian.lib.harness.ids import TransportId
from meridian.lib.harness.launch_spec import CodexLaunchSpec, ResolvedLaunchSpec
from meridian.lib.safety.permissions import UnsafeNoOpPermissionResolver
from meridian.lib.state import paths
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.spawn_store import finalize_spawn, get_spawn, start_spawn
from meridian.lib.streaming import spawn_manager as spawn_manager_module
from meridian.lib.streaming.heartbeat import heartbeat_loop
from meridian.lib.streaming.inject_lock import get_lock
from meridian.lib.streaming.spawn_manager import SpawnManager
from meridian.lib.streaming.types import InjectResult


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


def _read_inbound_lines(state_root: Path, spawn_id: str) -> list[dict[str, object]]:
    inbound_path = state_root / "spawns" / spawn_id / "inbound.jsonl"
    return [
        cast("dict[str, object]", json.loads(line))
        for line in inbound_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _build_config(spawn_id: str, repo_root: Path) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=spawn_id,
        harness_id=HarnessId.CODEX,
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


async def _start_recording_manager(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    user_message_gate: asyncio.Event | None = None,
    user_message_started: asyncio.Event | None = None,
) -> tuple[SpawnManager, Path, str, object]:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir

    class FakeControlSocketServer:
        def __init__(self, spawn_id: str, socket_path: Path, manager: SpawnManager) -> None:
            _ = spawn_id, manager
            self.socket_path = socket_path

        async def start(self) -> None:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        async def stop(self) -> None:
            pass

    class RecordingConnection:
        latest: RecordingConnection | None = None

        def __init__(self) -> None:
            type(self).latest = self
            self._spawn_id = ""
            self.state = "created"
            self.operations: list[tuple[str, str | None]] = []
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
            self.operations.append(("user_message", text))
            if user_message_started is not None:
                user_message_started.set()
            if user_message_gate is not None:
                await user_message_gate.wait()

        async def send_interrupt(self) -> None:
            self.operations.append(("interrupt", None))

        async def send_cancel(self) -> None:
            self.operations.append(("cancel", None))

        async def events(self):  # type: ignore[no-untyped-def]
            while True:
                await asyncio.sleep(3600)
                if False:
                    yield HarnessEvent(
                        event_type="noop",
                        harness_id="codex",
                        payload={},
                    )

    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        lambda harness_id: RecordingConnection,
    )

    spawn_id = str(
        start_spawn(
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
    )
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    await manager.start_spawn(
        _build_config(spawn_id, repo_root),
        CodexLaunchSpec(
            prompt="hello",
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        ),
    )
    connection = RecordingConnection.latest
    assert connection is not None
    return manager, state_root, spawn_id, connection


def test_inject_result_exposes_phase_1_fields() -> None:
    assert [field.name for field in fields(InjectResult)] == [
        "success",
        "inbound_seq",
        "noop",
        "error",
    ]
    assert InjectResult(success=True) == InjectResult(
        success=True,
        inbound_seq=None,
        noop=False,
        error=None,
    )


@pytest.mark.asyncio
async def test_heartbeat_loop_creates_missing_sentinel(tmp_path: Path) -> None:
    state_root = tmp_path / ".meridian"
    spawn_id = SpawnId("p-heartbeat")
    sentinel = paths.heartbeat_path(state_root, spawn_id)

    task = asyncio.create_task(heartbeat_loop(state_root, spawn_id, interval=0.01))
    try:
        await _wait_until(sentinel.exists)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_heartbeat_loop_uses_configured_interval_touching(tmp_path: Path) -> None:
    state_root = tmp_path / ".meridian"
    spawn_id = SpawnId("p-heartbeat")
    sentinel = paths.heartbeat_path(state_root, spawn_id)
    touch_count = 0

    def _touch(_state_root: Path, _spawn_id: SpawnId) -> None:
        nonlocal touch_count
        touch_count += 1
        sentinel.touch()

    task = asyncio.create_task(
        heartbeat_loop(state_root, spawn_id, interval=0.01, touch=_touch)
    )
    try:
        await asyncio.sleep(0.035)
        assert touch_count >= 2
        assert sentinel.exists()
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_spawn_manager_concurrent_injects_assign_distinct_monotonic_inbound_seq(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, state_root, spawn_id, connection = await _start_recording_manager(
        tmp_path,
        monkeypatch,
    )
    try:
        first, second = await asyncio.gather(
            manager.inject(SpawnId(spawn_id), "A"),
            manager.inject(SpawnId(spawn_id), "B"),
        )

        inbound_lines = _read_inbound_lines(state_root, spawn_id)
        assert [line["action"] for line in inbound_lines] == ["user_message", "user_message"]
        assert [line["data"]["text"] for line in inbound_lines] == [
            payload for action, payload in connection.operations if action == "user_message"
        ]
        assert {first.inbound_seq, second.inbound_seq} == {0, 1}
        assert sorted(
            cast("list[int]", [first.inbound_seq, second.inbound_seq])
        ) == [0, 1]
        row = get_spawn(state_root, SpawnId(spawn_id))
        assert row is not None
        assert row.status == "running"
    finally:
        await manager.stop_spawn(SpawnId(spawn_id))


@pytest.mark.asyncio
async def test_spawn_manager_interrupt_and_inject_share_one_linearized_sequence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, state_root, spawn_id, connection = await _start_recording_manager(
        tmp_path,
        monkeypatch,
    )
    try:
        inject_result, interrupt_result = await asyncio.gather(
            manager.inject(SpawnId(spawn_id), "A"),
            manager.interrupt(SpawnId(spawn_id), source="control_socket"),
        )

        inbound_lines = _read_inbound_lines(state_root, spawn_id)
        assert [line["action"] for line in inbound_lines] == [
            action for action, _ in connection.operations if action != "cancel"
        ]
        assert {inject_result.inbound_seq, interrupt_result.inbound_seq} == {0, 1}
        assert sorted(
            cast("list[int]", [inject_result.inbound_seq, interrupt_result.inbound_seq])
        ) == [0, 1]
        row = get_spawn(state_root, SpawnId(spawn_id))
        assert row is not None
        assert row.status == "running"
    finally:
        await manager.stop_spawn(SpawnId(spawn_id))


@pytest.mark.asyncio
async def test_spawn_manager_on_result_callback_runs_before_lock_is_released(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_send_started = asyncio.Event()
    release_first_send = asyncio.Event()
    manager, _state_root, spawn_id, _connection = await _start_recording_manager(
        tmp_path,
        monkeypatch,
        user_message_gate=release_first_send,
        user_message_started=first_send_started,
    )
    try:
        callback_lock_states: list[bool] = []
        callback_second_task_done: list[bool] = []

        def _on_result(_result: InjectResult) -> None:
            callback_lock_states.append(get_lock(SpawnId(spawn_id)).locked())
            callback_second_task_done.append(second_task.done())

        first_task = asyncio.create_task(
            manager.inject(SpawnId(spawn_id), "A", on_result=_on_result)
        )
        await first_send_started.wait()
        second_task = asyncio.create_task(manager.inject(SpawnId(spawn_id), "B"))
        await asyncio.sleep(0)
        assert second_task.done() is False
        release_first_send.set()
        await first_task
        await second_task

        assert callback_lock_states == [True]
        assert callback_second_task_done == [False]
    finally:
        await manager.stop_spawn(SpawnId(spawn_id))


@pytest.mark.asyncio
async def test_spawn_manager_inject_rejects_when_spawn_is_not_active(tmp_path: Path) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        kind="streaming",
        prompt="hello",
        launch_mode="foreground",
        status="succeeded",
    )
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)

    result = await manager.inject(spawn_id, "late message")

    assert result == InjectResult(
        success=False,
        error="spawn not running: succeeded",
    )


@pytest.mark.asyncio
async def test_spawn_manager_inject_rejects_when_spawn_is_terminal_before_session_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, state_root, spawn_id, _connection = await _start_recording_manager(
        tmp_path,
        monkeypatch,
    )
    try:
        finalized = finalize_spawn(
            state_root,
            SpawnId(spawn_id),
            status="succeeded",
            exit_code=0,
            origin="runner",
        )
        assert finalized is True
        result = await manager.inject(SpawnId(spawn_id), "late message")
        assert result == InjectResult(
            success=False,
            error="spawn not running: succeeded",
        )
    finally:
        await manager.stop_spawn(SpawnId(spawn_id))


@pytest.mark.asyncio
async def test_spawn_manager_interrupt_rejects_when_spawn_is_terminal_before_session_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, state_root, spawn_id, _connection = await _start_recording_manager(
        tmp_path,
        monkeypatch,
    )
    try:
        finalized = finalize_spawn(
            state_root,
            SpawnId(spawn_id),
            status="succeeded",
            exit_code=0,
            origin="runner",
        )
        assert finalized is True
        result = await manager.interrupt(SpawnId(spawn_id), source="control_socket")
        assert result == InjectResult(
            success=False,
            error="spawn not running: succeeded",
        )
    finally:
        await manager.stop_spawn(SpawnId(spawn_id))


@pytest.mark.asyncio
async def test_spawn_manager_interrupt_returns_noop_when_codex_has_no_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    send_interrupt_calls = 0

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
            self.current_turn_id: str | None = None

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
            nonlocal send_interrupt_calls
            send_interrupt_calls += 1

        async def send_cancel(self) -> None:
            return None

        async def events(self):  # type: ignore[no-untyped-def]
            while True:
                await asyncio.sleep(3600)
                if False:
                    yield HarnessEvent(
                        event_type="noop",
                        harness_id="codex",
                        payload={},
                    )

    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        lambda harness_id: FakeConnection,
    )

    spawn_id = str(
        start_spawn(
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
    )
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    await manager.start_spawn(
        _build_config(spawn_id, repo_root),
        CodexLaunchSpec(
            prompt="hello",
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        ),
    )
    try:
        result = await manager.interrupt(SpawnId(spawn_id), source="control_socket")
        assert result == InjectResult(success=True, noop=True)
        assert send_interrupt_calls == 0

        inbound_path = state_root / "spawns" / spawn_id / "inbound.jsonl"
        assert inbound_path.exists() is False
    finally:
        await manager.stop_spawn(SpawnId(spawn_id))


@pytest.mark.asyncio
async def test_spawn_manager_missing_terminal_event_defaults_to_failed_completion_outcome(
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
        CodexLaunchSpec(
            prompt="hello",
            permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
        ),
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
    assert completion.status == "failed"
    assert completion.exit_code == 1
    assert completion.error == "connection_closed_without_terminal_event"
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
async def test_spawn_manager_wait_for_completion_after_missing_terminal_event_cleanup(
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
    assert completion.status == "failed"
    assert completion.exit_code == 1
    assert completion.error == "connection_closed_without_terminal_event"


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
                if False:
                    yield HarnessEvent(
                        event_type="noop",
                        harness_id="codex",
                        payload={},
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
async def test_spawn_manager_stop_spawn_cancel_emits_single_terminal_cancelled_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir

    class FakeControlSocketServer:
        def __init__(self, spawn_id: str, socket_path: Path, manager: SpawnManager) -> None:
            _ = spawn_id, manager
            self.socket_path = socket_path

        async def start(self) -> None:
            self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        async def stop(self) -> None:
            pass

    class FakeConnection:
        send_cancel_calls = 0
        stop_calls = 0

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
            type(self).stop_calls += 1
            self.state = "stopped"

        def health(self) -> bool:
            return True

        async def send_user_message(self, text: str) -> None:
            _ = text

        async def send_interrupt(self) -> None:
            return None

        async def send_cancel(self) -> None:
            type(self).send_cancel_calls += 1

        async def events(self):  # type: ignore[no-untyped-def]
            while True:
                await asyncio.sleep(3600)
                if False:
                    yield HarnessEvent(
                        event_type="noop",
                        harness_id="codex",
                        payload={},
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
    await manager.start_spawn(_build_config(spawn_id, repo_root))

    await manager.stop_spawn(spawn_id, status="cancelled", exit_code=143, error="cancelled")
    await manager.stop_spawn(spawn_id, status="cancelled", exit_code=143, error="cancelled")

    assert FakeConnection.send_cancel_calls == 1
    output = _read_output_lines(state_root, spawn_id)
    cancelled = [entry for entry in output if entry.get("event_type") == "cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0]["payload"]["status"] == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("ordering", "expected_terminal"),
    [
        ("cancel_first", "cancelled"),
        ("completion_first", "failed"),
    ],
)
async def test_spawn_manager_cancel_vs_completion_race_emits_both_events_and_first_terminal_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ordering: str,
    expected_terminal: str,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    release_completion = asyncio.Event()
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
            yield HarnessEvent(
                event_type="item.completed",
                harness_id="codex",
                payload={
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "done"},
                },
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
    original_cleanup = manager._cleanup_completed_session

    async def gated_cleanup(spawn_id: SpawnId) -> None:
        cleanup_started.set()
        await release_cleanup.wait()
        await original_cleanup(spawn_id)

    monkeypatch.setattr(manager, "_cleanup_completed_session", gated_cleanup)

    await manager.start_spawn(_build_config(spawn_id, repo_root))
    completion_task = asyncio.create_task(manager.wait_for_completion(spawn_id))
    output_path = state_root / "spawns" / spawn_id / "output.jsonl"

    def _output_has_item_completed() -> bool:
        if not output_path.exists():
            return False
        return any(
            entry.get("event_type") == "item.completed"
            for entry in _read_output_lines(state_root, spawn_id)
        )

    await _wait_until(_output_has_item_completed)

    try:
        if ordering == "completion_first":
            release_completion.set()
            await cleanup_started.wait()
            completion = await completion_task
            assert completion is not None
            assert completion.status == "failed"
            assert completion.error == "connection_closed_without_terminal_event"
            outcome = await manager.stop_spawn(spawn_id, status="cancelled", exit_code=1)
            assert outcome == completion
        else:
            outcome = await manager.stop_spawn(spawn_id, status="cancelled", exit_code=1)
            completion = await completion_task
            assert outcome is not None
            assert completion is not None
            assert outcome == completion

        assert outcome is not None
        assert outcome.status == expected_terminal

        output = _read_output_lines(state_root, spawn_id)
        event_types = [entry.get("event_type") for entry in output]
        assert "item.completed" in event_types
        assert "cancelled" in event_types
        assert len([t for t in event_types if t == "cancelled"]) == 1
    finally:
        release_cleanup.set()


@pytest.mark.asyncio
async def test_spawn_manager_stop_spawn_race_uses_missing_terminal_outcome_once(
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
    assert completion.status == "failed"
    assert completion.exit_code == 1
    assert completion.error == "connection_closed_without_terminal_event"
    assert outcome == completion

    spawn_events = _read_spawn_events(state_root)
    assert [event["event"] for event in spawn_events] == ["start"]

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "running"
    assert row.exit_code is None


@pytest.mark.asyncio
async def test_spawn_manager_dispatch_rejects_base_spec_for_claude(tmp_path: Path) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)

    config = ConnectionConfig(
        spawn_id=SpawnId("p-claude-mismatch"),
        harness_id=HarnessId.CLAUDE,
        prompt="hello",
        repo_root=repo_root,
        env_overrides={},
    )
    base_spec = ResolvedLaunchSpec(
        prompt="hello",
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )

    with pytest.raises(TypeError, match=r"expected ClaudeLaunchSpec"):
        await manager.start_spawn(config, base_spec)


@pytest.mark.asyncio
async def test_spawn_manager_dispatch_raises_keyerror_when_streaming_transport_missing(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    state_root = resolve_state_paths(repo_root).root_dir
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)

    config = ConnectionConfig(
        spawn_id=SpawnId("p-codex-missing-streaming"),
        harness_id=HarnessId.CODEX,
        prompt="hello",
        repo_root=repo_root,
        env_overrides={},
    )
    spec = CodexLaunchSpec(
        prompt="hello",
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )

    original_bundle = get_harness_bundle(HarnessId.CODEX)
    _REGISTRY[HarnessId.CODEX] = HarnessBundle(
        harness_id=original_bundle.harness_id,
        adapter=original_bundle.adapter,
        spec_cls=original_bundle.spec_cls,
        extractor=original_bundle.extractor,
        connections={TransportId.SUBPROCESS: next(iter(original_bundle.connections.values()))},
    )
    try:
        with pytest.raises(
            KeyError,
            match=r"harness codex has no connection for transport streaming",
        ):
            await manager.start_spawn(config, spec)
    finally:
        _REGISTRY[HarnessId.CODEX] = original_bundle
