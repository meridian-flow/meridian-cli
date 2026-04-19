from __future__ import annotations

import asyncio
import importlib
import os
import signal
from itertools import pairwise
from pathlib import Path
from typing import ClassVar

import pytest

from meridian.lib.core.domain import Spawn, TokenUsage
from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import ArtifactStore as HarnessArtifactStore
from meridian.lib.harness.adapter import (
    BaseSubprocessHarness,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
)
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts_with_patterns,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    HarnessEvent,
)
from meridian.lib.harness.errors import HarnessBinaryNotFound
from meridian.lib.harness.launch_spec import (
    ClaudeLaunchSpec,
    CodexLaunchSpec,
    OpenCodeLaunchSpec,
    ResolvedLaunchSpec,
)
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.request import LaunchArgvIntent, LaunchRuntime, SpawnRequest
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_runtime_state_root, resolve_spawn_log_dir
from meridian.lib.streaming import spawn_manager as spawn_manager_module
from tests.support.fakes import FakeClock, FakeHeartbeat

streaming_runner_module = importlib.import_module("meridian.lib.launch.streaming_runner")
execute_with_streaming = streaming_runner_module.execute_with_streaming
run_streaming_spawn = streaming_runner_module.run_streaming_spawn


def _fake_connection_class(_harness_id: HarnessId) -> type[_TurnCompletedThenCloseConnection]:
    return _TurnCompletedThenCloseConnection


def _fake_report_hang_connection_class(
    _harness_id: HarnessId,
) -> type[_ReportThenHangConnection]:
    return _ReportThenHangConnection


def _fake_claude_result_connection_class(
    _harness_id: HarnessId,
) -> type[_ClaudeResultThenHangConnection]:
    return _ClaudeResultThenHangConnection


def _fake_claude_result_error_connection_class(
    _harness_id: HarnessId,
) -> type[_ClaudeResultErrorThenCloseConnection]:
    return _ClaudeResultErrorThenCloseConnection


def _fake_opencode_idle_connection_class(
    _harness_id: HarnessId,
) -> type[_OpenCodeIdleThenHangConnection]:
    return _OpenCodeIdleThenHangConnection


def _fake_turn_completed_then_close_connection_class(
    _harness_id: HarnessId,
) -> type[_TurnCompletedThenCloseConnection]:
    return _TurnCompletedThenCloseConnection


def _fake_item_completed_then_close_connection_class(
    _harness_id: HarnessId,
) -> type[_ItemCompletedThenCloseConnection]:
    return _ItemCompletedThenCloseConnection


def _fake_opencode_capture_spec_connection_class(
    _harness_id: HarnessId,
) -> type[_OpenCodeCaptureSpecThenIdleConnection]:
    return _OpenCodeCaptureSpecThenIdleConnection


def _fake_codex_capture_spec_connection_class(
    _harness_id: HarnessId,
) -> type[_CodexCaptureSpecThenIdleConnection]:
    return _CodexCaptureSpecThenIdleConnection


class _DummyCodexHarness(BaseSubprocessHarness):
    id: ClassVar[HarnessId] = HarnessId.CODEX
    consumed_fields: ClassVar[frozenset[str]] = frozenset()
    explicitly_ignored_fields: ClassVar[frozenset[str]] = frozenset()

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def resolve_launch_spec(
        self,
        run: SpawnParams,
        perms: PermissionResolver,
    ) -> ResolvedLaunchSpec:
        if self.id == HarnessId.CLAUDE:
            return ClaudeLaunchSpec(
                prompt=run.prompt or "",
                permission_resolver=perms,
            )
        if self.id == HarnessId.OPENCODE:
            return OpenCodeLaunchSpec(
                prompt=run.prompt or "",
                permission_resolver=perms,
            )
        return CodexLaunchSpec(
            prompt=run.prompt or "",
            permission_resolver=perms,
        )

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        _ = run, perms
        return ["unused"]

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        _ = run
        return None

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts_with_patterns(artifacts, spawn_id)


class _DummyClaudeHarness(_DummyCodexHarness):
    id: ClassVar[HarnessId] = HarnessId.CLAUDE


class _DummyOpenCodeHarness(_DummyCodexHarness):
    id: ClassVar[HarnessId] = HarnessId.OPENCODE


class _FakeControlSocketServer:
    def __init__(self, spawn_id: str, socket_path: Path, manager: object) -> None:
        _ = spawn_id, manager
        self.socket_path = socket_path

    async def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

    async def stop(self) -> None:
        return None


class _HangingAfterTurnCompletedConnection:
    def __init__(self) -> None:
        self.state = "created"
        self._spawn_id = SpawnId("")
        self._repo_root: Path | None = None
        self._session_id = "thread-123"
        self.stop_calls = 0
        self.capabilities = ConnectionCapabilities(
            mid_turn_injection="interrupt_restart",
            supports_steer=True,
            supports_interrupt=True,
            supports_cancel=True,
            runtime_model_switch=False,
            structured_reasoning=True,
        )

    @property
    def harness_id(self) -> HarnessId:
        return HarnessId.CODEX

    @property
    def spawn_id(self) -> SpawnId:
        return self._spawn_id

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def subprocess_pid(self) -> int | None:
        return 4242

    async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
        _ = spec
        self._spawn_id = config.spawn_id
        self._repo_root = config.repo_root
        self.state = "connected"

    async def stop(self) -> None:
        self.stop_calls += 1
        self.state = "stopped"

    def health(self) -> bool:
        return self.state == "connected"

    async def send_user_message(self, text: str) -> None:
        _ = text

    async def send_interrupt(self) -> None:
        return None

    async def send_cancel(self) -> None:
        return None

    async def events(self):  # type: ignore[no-untyped-def]
        repo_root = self._repo_root
        assert repo_root is not None
        spawn_dir = resolve_spawn_log_dir(repo_root, self._spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        (spawn_dir / "report.md").write_text(
            "# Done\n\nStreaming turn completed.\n",
            encoding="utf-8",
        )
        yield HarnessEvent(
            event_type="item/completed",
            harness_id="codex",
            payload={
                "item": {"id": "msg-1", "type": "agentMessage", "text": "done"},
                "threadId": self._session_id,
                "turnId": "turn-1",
            },
        )
        yield HarnessEvent(
            event_type="turn/completed",
            harness_id="codex",
            payload={
                "threadId": self._session_id,
                "turn": {"id": "turn-1", "status": "completed", "error": None, "items": []},
            },
        )
        while True:
            await asyncio.sleep(3600)


class _ReportThenHangConnection(_HangingAfterTurnCompletedConnection):
    async def events(self):  # type: ignore[no-untyped-def]
        repo_root = self._repo_root
        assert repo_root is not None
        spawn_dir = resolve_spawn_log_dir(repo_root, self._spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        (spawn_dir / "report.md").write_text(
            "# Done\n\nWatchdog fallback completed.\n",
            encoding="utf-8",
        )
        yield HarnessEvent(
            event_type="item/completed",
            harness_id="codex",
            payload={
                "item": {"id": "msg-1", "type": "agentMessage", "text": "done"},
                "threadId": self._session_id,
                "turnId": "turn-1",
            },
        )
        while True:
            await asyncio.sleep(3600)


class _ClaudeResultThenHangConnection(_HangingAfterTurnCompletedConnection):
    @property
    def harness_id(self) -> HarnessId:
        return HarnessId.CLAUDE

    async def events(self):  # type: ignore[no-untyped-def]
        repo_root = self._repo_root
        assert repo_root is not None
        spawn_dir = resolve_spawn_log_dir(repo_root, self._spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        (spawn_dir / "report.md").write_text(
            "# Done\n\nClaude result completed.\n",
            encoding="utf-8",
        )
        yield HarnessEvent(
            event_type="assistant",
            harness_id="claude",
            payload={
                "message": {
                    "role": "assistant",
                    "type": "message",
                    "content": [{"type": "text", "text": "done"}],
                },
            },
        )
        yield HarnessEvent(
            event_type="result",
            harness_id="claude",
            payload={
                "subtype": "success",
                "is_error": False,
                "stop_reason": "end_turn",
                "terminal_reason": "completed",
                "result": "Claude completed successfully.",
                "session_id": self._session_id,
                "type": "result",
            },
        )
        while True:
            await asyncio.sleep(3600)


class _OpenCodeIdleThenHangConnection(_HangingAfterTurnCompletedConnection):
    @property
    def harness_id(self) -> HarnessId:
        return HarnessId.OPENCODE

    async def events(self):  # type: ignore[no-untyped-def]
        repo_root = self._repo_root
        assert repo_root is not None
        spawn_dir = resolve_spawn_log_dir(repo_root, self._spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        (spawn_dir / "report.md").write_text(
            "# Done\n\nOpenCode session became idle.\n",
            encoding="utf-8",
        )
        yield HarnessEvent(
            event_type="message.updated",
            harness_id="opencode",
            payload={
                "properties": {
                    "info": {
                        "id": "msg-1",
                        "role": "assistant",
                        "sessionID": self._session_id,
                    },
                    "sessionID": self._session_id,
                },
                "type": "message.updated",
            },
        )
        yield HarnessEvent(
            event_type="session.idle",
            harness_id="opencode",
            payload={
                "properties": {
                    "sessionID": self._session_id,
                },
                "type": "session.idle",
            },
        )
        while True:
            await asyncio.sleep(3600)


class _ClaudeResultErrorThenCloseConnection(_HangingAfterTurnCompletedConnection):
    @property
    def harness_id(self) -> HarnessId:
        return HarnessId.CLAUDE

    async def events(self):  # type: ignore[no-untyped-def]
        yield HarnessEvent(
            event_type="result",
            harness_id="claude",
            payload={
                "subtype": "error",
                "is_error": True,
                "result": "boom",
                "session_id": self._session_id,
                "type": "result",
            },
        )


class _TurnCompletedThenCloseConnection(_HangingAfterTurnCompletedConnection):
    async def events(self):  # type: ignore[no-untyped-def]
        repo_root = self._repo_root
        assert repo_root is not None
        spawn_dir = resolve_spawn_log_dir(repo_root, self._spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        (spawn_dir / "report.md").write_text(
            "# Done\n\nTurn completed before shutdown.\n",
            encoding="utf-8",
        )
        yield HarnessEvent(
            event_type="turn/completed",
            harness_id="codex",
            payload={
                "threadId": self._session_id,
                "turn": {"id": "turn-1", "status": "completed", "error": None, "items": []},
            },
        )


class _ItemCompletedThenCloseConnection(_HangingAfterTurnCompletedConnection):
    async def events(self):  # type: ignore[no-untyped-def]
        repo_root = self._repo_root
        assert repo_root is not None
        spawn_dir = resolve_spawn_log_dir(repo_root, self._spawn_id)
        spawn_dir.mkdir(parents=True, exist_ok=True)
        (spawn_dir / "report.md").write_text(
            "# Done\n\nItem completed before shutdown.\n",
            encoding="utf-8",
        )
        yield HarnessEvent(
            event_type="item/completed",
            harness_id="codex",
            payload={
                "item": {"id": "msg-1", "type": "agentMessage", "text": "done"},
                "threadId": self._session_id,
                "turnId": "turn-1",
            },
        )


class _OpenCodeCaptureSpecThenIdleConnection(_OpenCodeIdleThenHangConnection):
    seen_spec: ResolvedLaunchSpec | None = None

    async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
        type(self).seen_spec = spec
        await super().start(config, spec)


class _CodexCaptureSpecThenIdleConnection(_TurnCompletedThenCloseConnection):
    seen_spec: ResolvedLaunchSpec | None = None

    async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
        type(self).seen_spec = spec
        await super().start(config, spec)


class _MissingBinaryConnection:
    def __init__(self) -> None:
        self.state = "created"
        self.capabilities = ConnectionCapabilities(
            mid_turn_injection="interrupt_restart",
            supports_steer=True,
            supports_interrupt=True,
            supports_cancel=True,
            runtime_model_switch=False,
            structured_reasoning=True,
        )

    @property
    def harness_id(self) -> HarnessId:
        return HarnessId.CODEX

    @property
    def spawn_id(self) -> SpawnId:
        return SpawnId("p-missing")

    @property
    def session_id(self) -> str | None:
        return None

    @property
    def subprocess_pid(self) -> int | None:
        return None

    async def start(self, config: ConnectionConfig, spec: ResolvedLaunchSpec) -> None:
        _ = config, spec
        raise FileNotFoundError(2, "No such file or directory", "codex")

    async def stop(self) -> None:
        return None

    def health(self) -> bool:
        return False

    async def send_user_message(self, text: str) -> None:
        _ = text

    async def send_interrupt(self) -> None:
        return None

    async def send_cancel(self) -> None:
        return None

    async def events(self):  # type: ignore[no-untyped-def]
        if False:
            yield HarnessEvent(
                event_type="noop",
                harness_id="codex",
                payload={},
            )


def _build_plan(
    harness_id: HarnessId = HarnessId.CODEX,
    model: str = "gpt-5.3-codex",
) -> SpawnRequest:
    return SpawnRequest(
        model=model,
        harness=harness_id.value,
        prompt="hello",
    )


async def _execute_with_context(
    run: Spawn,
    *,
    request: SpawnRequest,
    repo_root: Path,
    state_root: Path,
    artifacts: LocalStore,
    registry: HarnessRegistry,
    cwd: Path | None = None,
    **kwargs: object,
) -> int:
    launch_context = build_launch_context(
        spawn_id=str(run.spawn_id),
        request=request,
        runtime=LaunchRuntime(
            argv_intent=LaunchArgvIntent.SPEC_ONLY,
            state_root=state_root.as_posix(),
            project_paths_repo_root=repo_root.as_posix(),
            project_paths_execution_cwd=(cwd or repo_root).resolve().as_posix(),
        ),
        harness_registry=registry,
    )
    return await execute_with_streaming(
        run,
        request=request,
        launch_context=launch_context,
        repo_root=repo_root,
        state_root=state_root,
        artifacts=artifacts,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_run_streaming_spawn_finishes_after_turn_completed_when_stream_drains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_connection_class,
    )

    outcome = await asyncio.wait_for(
        run_streaming_spawn(
            config=ConnectionConfig(
                spawn_id=SpawnId("p1"),
                harness_id=HarnessId.CODEX,
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            spec=CodexLaunchSpec(
                prompt="hello",
                permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
            ),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p1"),
        ),
        timeout=1.0,
    )

    assert outcome.status == "succeeded"
    assert outcome.exit_code == 0


@pytest.mark.asyncio
async def test_run_streaming_spawn_threads_caller_permission_resolver_without_swapping(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_codex_capture_spec_connection_class,
    )
    _CodexCaptureSpecThenIdleConnection.seen_spec = None
    resolver = TieredPermissionResolver(
        config=PermissionConfig(sandbox="read-only", approval="auto")
    )

    outcome = await asyncio.wait_for(
        run_streaming_spawn(
            config=ConnectionConfig(
                spawn_id=SpawnId("p-resolver"),
                harness_id=HarnessId.CODEX,
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            spec=CodexLaunchSpec(
                prompt="hello",
                model="gpt-5.3-codex",
                permission_resolver=resolver,
            ),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p-resolver"),
        ),
        timeout=1.0,
    )

    assert outcome.status == "succeeded"
    observed_spec = _CodexCaptureSpecThenIdleConnection.seen_spec
    assert isinstance(observed_spec, CodexLaunchSpec)
    assert observed_spec.permission_resolver is resolver


@pytest.mark.asyncio
async def test_run_streaming_spawn_raises_structured_missing_binary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        lambda _harness_id: _MissingBinaryConnection,
    )

    with pytest.raises(HarnessBinaryNotFound) as exc_info:
        await run_streaming_spawn(
            config=ConnectionConfig(
                spawn_id=SpawnId("p-missing"),
                harness_id=HarnessId.CODEX,
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            spec=CodexLaunchSpec(
                prompt="hello",
                permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
            ),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p-missing"),
        )

    err = exc_info.value
    assert err.harness_id == "codex"
    assert err.binary_name == "codex"
    assert err.searched_path == str(os.environ.get("PATH", ""))


@pytest.mark.asyncio
async def test_execute_with_streaming_succeeds_when_turn_completes_and_stream_drains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_connection_class,
    )

    run = Spawn(
        spawn_id=SpawnId("r1"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-r1",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    report = (state_root / "spawns" / str(run.spawn_id) / "report.md").read_text(encoding="utf-8")
    assert "Turn completed before shutdown." in report


@pytest.mark.asyncio
async def test_execute_with_streaming_succeeds_after_report_watchdog_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_report_hang_connection_class,
    )

    async def _fast_report_watchdog(
        *,
        report_path: Path,
        completion_event: asyncio.Event,
        manager: spawn_manager_module.SpawnManager,
        spawn_id: SpawnId,
        grace_seconds: float = 60.0,
    ) -> bool:
        _ = grace_seconds
        while not report_path.exists():
            if completion_event.is_set():
                return False
            await asyncio.sleep(0)
        if completion_event.is_set():
            return False
        await manager.stop_spawn(
            spawn_id,
            status="cancelled",
            exit_code=1,
            error="report_watchdog",
        )
        return True

    monkeypatch.setattr(streaming_runner_module, "_report_watchdog", _fast_report_watchdog)

    run = Spawn(
        spawn_id=SpawnId("r2"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-r2",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    report = (state_root / "spawns" / str(run.spawn_id) / "report.md").read_text(encoding="utf-8")
    assert "Watchdog fallback completed." in report


@pytest.mark.asyncio
async def test_execute_with_streaming_waits_for_delayed_terminal_failure_after_drain_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyClaudeHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_claude_result_error_connection_class,
    )

    async def _delayed_terminal_consume(
        *,
        subscriber: asyncio.Queue[HarnessEvent | None],
        budget_tracker: object,
        budget_signal: asyncio.Event,
        budget_breach_holder: list[object | None],
        event_observer: object,
        stream_stdout_to_terminal: bool,
        terminal_event_future: asyncio.Future[object] | None = None,
    ) -> None:
        _ = (
            budget_tracker,
            budget_signal,
            budget_breach_holder,
            event_observer,
            stream_stdout_to_terminal,
        )
        while True:
            event = await subscriber.get()
            if event is None:
                return
            if terminal_event_future is None or terminal_event_future.done():
                continue
            terminal_outcome = streaming_runner_module._terminal_event_outcome(event)
            if terminal_outcome is None:
                continue
            await asyncio.sleep(0.05)
            terminal_event_future.set_result(terminal_outcome)

    monkeypatch.setattr(
        streaming_runner_module,
        "_consume_subscriber_events",
        _delayed_terminal_consume,
    )

    run = Spawn(
        spawn_id=SpawnId("r-f1"),
        prompt="hello",
        model=ModelId("claude-opus-4-1"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rf1",
        model=str(run.model),
        agent="",
        harness="claude",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(HarnessId.CLAUDE, "claude-opus-4-1"),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code != 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error in {"boom", None}


@pytest.mark.asyncio
async def test_execute_with_streaming_prefers_terminal_over_same_wakeup_signal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_turn_completed_then_close_connection_class,
    )

    signal_state: dict[str, object] = {}

    def _capture_signal_handlers(
        loop: asyncio.AbstractEventLoop,
        shutdown_event: asyncio.Event,
        received_signal: list[signal.Signals | None],
    ) -> list[signal.Signals]:
        _ = loop
        signal_state["shutdown_event"] = shutdown_event
        signal_state["received_signal"] = received_signal
        return []

    monkeypatch.setattr(
        streaming_runner_module,
        "_install_signal_handlers",
        _capture_signal_handlers,
    )

    async def _terminal_then_signal_consume(
        *,
        subscriber: asyncio.Queue[HarnessEvent | None],
        budget_tracker: object,
        budget_signal: asyncio.Event,
        budget_breach_holder: list[object | None],
        event_observer: object,
        stream_stdout_to_terminal: bool,
        terminal_event_future: asyncio.Future[object] | None = None,
    ) -> None:
        _ = (
            budget_tracker,
            budget_signal,
            budget_breach_holder,
            event_observer,
            stream_stdout_to_terminal,
        )
        while True:
            event = await subscriber.get()
            if event is None:
                return
            if terminal_event_future is None or terminal_event_future.done():
                continue
            terminal_outcome = streaming_runner_module._terminal_event_outcome(event)
            if terminal_outcome is None:
                continue
            terminal_event_future.set_result(terminal_outcome)
            received_signal_holder = signal_state.get("received_signal")
            shutdown_event = signal_state.get("shutdown_event")
            assert isinstance(received_signal_holder, list)
            assert isinstance(shutdown_event, asyncio.Event)
            received_signal_holder[0] = signal.SIGTERM
            shutdown_event.set()

    monkeypatch.setattr(
        streaming_runner_module,
        "_consume_subscriber_events",
        _terminal_then_signal_consume,
    )

    run = Spawn(
        spawn_id=SpawnId("r-f2"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rf2",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.error is None


@pytest.mark.asyncio
async def test_execute_with_streaming_signal_wins_without_spawn_terminal_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_item_completed_then_close_connection_class,
    )

    signal_state: dict[str, object] = {}

    def _capture_signal_handlers(
        loop: asyncio.AbstractEventLoop,
        shutdown_event: asyncio.Event,
        received_signal: list[signal.Signals | None],
    ) -> list[signal.Signals]:
        _ = loop
        signal_state["shutdown_event"] = shutdown_event
        signal_state["received_signal"] = received_signal
        return []

    monkeypatch.setattr(
        streaming_runner_module,
        "_install_signal_handlers",
        _capture_signal_handlers,
    )

    original_wait_for_completion = spawn_manager_module.SpawnManager.wait_for_completion

    async def _wait_for_completion_then_raise_sigterm(
        manager: spawn_manager_module.SpawnManager,
        spawn_id: SpawnId,
    ) -> spawn_manager_module.DrainOutcome | None:
        outcome = await original_wait_for_completion(manager, spawn_id)
        received_signal_holder = signal_state.get("received_signal")
        shutdown_event = signal_state.get("shutdown_event")
        assert isinstance(received_signal_holder, list)
        assert isinstance(shutdown_event, asyncio.Event)
        received_signal_holder[0] = signal.SIGTERM
        shutdown_event.set()
        return outcome

    monkeypatch.setattr(
        spawn_manager_module.SpawnManager,
        "wait_for_completion",
        _wait_for_completion_then_raise_sigterm,
    )

    async def _delayed_terminal_consume(
        *,
        subscriber: asyncio.Queue[HarnessEvent | None],
        budget_tracker: object,
        budget_signal: asyncio.Event,
        budget_breach_holder: list[object | None],
        event_observer: object,
        stream_stdout_to_terminal: bool,
        terminal_event_future: asyncio.Future[object] | None = None,
    ) -> None:
        _ = (
            budget_tracker,
            budget_signal,
            budget_breach_holder,
            event_observer,
            stream_stdout_to_terminal,
        )
        while True:
            event = await subscriber.get()
            if event is None:
                return
            if terminal_event_future is None or terminal_event_future.done():
                continue
            terminal_outcome = streaming_runner_module._terminal_event_outcome(event)
            if terminal_outcome is None:
                continue
            # Keep terminal pending long enough for completion+signal to be observed first.
            await asyncio.sleep(0.05)
            terminal_event_future.set_result(terminal_outcome)

    monkeypatch.setattr(
        streaming_runner_module,
        "_consume_subscriber_events",
        _delayed_terminal_consume,
    )

    run = Spawn(
        spawn_id=SpawnId("r-f2b"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rf2b",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code == 143
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "cancelled"
    assert row.exit_code == 143
    assert row.error == "terminated"


@pytest.mark.asyncio
async def test_execute_with_streaming_persists_missing_binary_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyClaudeHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)

    async def _raise_missing_binary(
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> _HangingAfterTurnCompletedConnection:
        _ = config, spec
        raise HarnessBinaryNotFound(
            harness_id="claude",
            binary_name="/usr/bin/claude",
            searched_path="/fake:/path",
        )

    monkeypatch.setattr(spawn_manager_module, "dispatch_start", _raise_missing_binary)

    run = Spawn(
        spawn_id=SpawnId("r-f3"),
        prompt="hello",
        model=ModelId("claude-opus-4-1"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rf3",
        model=str(run.model),
        agent="",
        harness="claude",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(HarnessId.CLAUDE, "claude-opus-4-1"),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code != 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error is not None
    assert "binary_name='/usr/bin/claude'" in row.error
    assert "searched_path='/fake:/path'" in row.error


@pytest.mark.asyncio
async def test_execute_with_streaming_codex_uses_adapter_resolved_launch_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(CodexAdapter())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_codex_capture_spec_connection_class,
    )
    _CodexCaptureSpecThenIdleConnection.seen_spec = None

    run = Spawn(
        spawn_id=SpawnId("r2b"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-r2b",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    permission_config = PermissionConfig(sandbox="read-only", approval="auto")
    request = _build_plan().model_copy(
        update={
            "sandbox": "read-only",
            "approval": "auto",
        }
    )

    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=request,
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    observed_spec = _CodexCaptureSpecThenIdleConnection.seen_spec
    assert isinstance(observed_spec, CodexLaunchSpec)
    assert observed_spec.model == "gpt-5.3-codex"
    assert observed_spec.permission_resolver.config == permission_config
    assert observed_spec.report_output_path is not None
    assert observed_spec.report_output_path.endswith("/report.md")


@pytest.mark.asyncio
async def test_run_streaming_spawn_finishes_on_claude_result_without_connection_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_claude_result_connection_class,
    )

    outcome = await asyncio.wait_for(
        run_streaming_spawn(
            config=ConnectionConfig(
                spawn_id=SpawnId("p2"),
                harness_id=HarnessId.CLAUDE,
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            spec=ClaudeLaunchSpec(
                prompt="hello",
                permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
            ),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p2"),
        ),
        timeout=1.0,
    )

    assert outcome.status == "succeeded"
    assert outcome.exit_code == 0


# TODO: Redesign this test — it depends on import-order side effects for
# the global bundle registry (ClaudeAdapter import triggers registration),
# and the assertion conflates the report.md-vs-result-event extraction
# priority in enrich_finalize. The mock writes report.md on disk but the
# Claude extractor overwrites it with the result event content via
# _persist_report(source="assistant_message"). The test needs to be
# rewritten with explicit bundle registry setup and clear assertion
# targets for the extraction pipeline behavior it's testing.
#
# @pytest.mark.asyncio
# async def test_execute_with_streaming_succeeds_when_claude_result_completes_but_connection_lingers(  # noqa: E501
#     tmp_path: Path,
#     monkeypatch: pytest.MonkeyPatch,
# ) -> None:
#     state_root = resolve_runtime_state_root(tmp_path)
#     artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
#     registry = HarnessRegistry()
#     registry.register(_DummyClaudeHarness())
#     monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
#     monkeypatch.setattr(
#         "meridian.lib.harness.connections.get_connection_class",
#         _fake_claude_result_connection_class,
#     )
#
#     run = Spawn(
#         spawn_id=SpawnId("r3"),
#         prompt="hello",
#         model=ModelId("claude-opus-4-1"),
#         status="queued",
#     )
#
#     exit_code = await asyncio.wait_for(
#         execute_with_streaming(
#             run,
#             request=_build_plan(HarnessId.CLAUDE, "claude-opus-4-1"),
#             repo_root=tmp_path,
#             state_root=state_root,
#             artifacts=artifacts,
#             registry=registry,
#             cwd=tmp_path,
#         ),
#         timeout=1.0,
#     )
#
#     assert exit_code == 0
#     row = spawn_store.get_spawn(state_root, run.spawn_id)
#     assert row is not None
#     assert row.status == "succeeded"
#     assert row.exit_code == 0
#     report = (state_root / "spawns" / str(run.spawn_id) / "report.md").read_text(encoding="utf-8")
#     assert "Claude result completed." in report


@pytest.mark.asyncio
async def test_run_streaming_spawn_finishes_on_opencode_idle_without_connection_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_opencode_idle_connection_class,
    )

    outcome = await asyncio.wait_for(
        run_streaming_spawn(
            config=ConnectionConfig(
                spawn_id=SpawnId("p3"),
                harness_id=HarnessId.OPENCODE,
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            spec=OpenCodeLaunchSpec(
                prompt="hello",
                permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
            ),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p3"),
        ),
        timeout=1.0,
    )

    assert outcome.status == "succeeded"
    assert outcome.exit_code == 0


@pytest.mark.asyncio
async def test_run_streaming_spawn_preserves_none_model_in_launch_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_opencode_capture_spec_connection_class,
    )
    _OpenCodeCaptureSpecThenIdleConnection.seen_spec = None

    outcome = await asyncio.wait_for(
        run_streaming_spawn(
            config=ConnectionConfig(
                spawn_id=SpawnId("p4"),
                harness_id=HarnessId.OPENCODE,
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            spec=OpenCodeLaunchSpec(
                prompt="hello",
                model=None,
                permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
            ),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p4"),
        ),
        timeout=1.0,
    )

    assert outcome.status == "succeeded"
    assert outcome.exit_code == 0
    observed_spec = _OpenCodeCaptureSpecThenIdleConnection.seen_spec
    assert observed_spec is not None
    assert observed_spec.model is None


@pytest.mark.asyncio
async def test_execute_with_streaming_succeeds_when_opencode_idle_completes_but_connection_lingers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyOpenCodeHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_opencode_idle_connection_class,
    )

    run = Spawn(
        spawn_id=SpawnId("r4"),
        prompt="hello",
        model=ModelId("openrouter/qwen/qwen3-coder:free"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-r4",
        model=str(run.model),
        agent="",
        harness="opencode",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(HarnessId.OPENCODE, "openrouter/qwen/qwen3-coder:free"),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    report = (state_root / "spawns" / str(run.spawn_id) / "report.md").read_text(encoding="utf-8")
    assert "OpenCode session became idle." in report


@pytest.mark.asyncio
async def test_execute_with_streaming_opencode_uses_adapter_normalized_launch_spec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(OpenCodeAdapter())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_opencode_capture_spec_connection_class,
    )
    _OpenCodeCaptureSpecThenIdleConnection.seen_spec = None

    run = Spawn(
        spawn_id=SpawnId("r5"),
        prompt="hello",
        model=ModelId("opencode-gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-r5",
        model=str(run.model),
        agent="",
        harness="opencode",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )
    request = _build_plan(HarnessId.OPENCODE, "opencode-gpt-5.3-codex").model_copy(
        update={
            "skills": ("skill-a",),
            "mcp_tools": ("tool-a=echo a",),
        }
    )

    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=request,
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    observed_spec = _OpenCodeCaptureSpecThenIdleConnection.seen_spec
    assert isinstance(observed_spec, OpenCodeLaunchSpec)
    assert observed_spec.model == "gpt-5.3-codex"
    assert observed_spec.skills == ()
    assert observed_spec.mcp_tools == ("tool-a=echo a",)


@pytest.mark.asyncio
async def test_execute_with_streaming_starts_and_ticks_runner_heartbeat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_connection_class,
    )

    fake_clock = FakeClock(start=1000.0)
    fake_heartbeat = FakeHeartbeat()
    fake_heartbeat.set_clock(fake_clock)

    async def _delayed_terminal_consume(
        *,
        subscriber: asyncio.Queue[HarnessEvent | None],
        budget_tracker: object,
        budget_signal: asyncio.Event,
        budget_breach_holder: list[object | None],
        event_observer: object,
        stream_stdout_to_terminal: bool,
        terminal_event_future: asyncio.Future[object] | None = None,
    ) -> None:
        _ = (
            budget_tracker,
            budget_signal,
            budget_breach_holder,
            event_observer,
            stream_stdout_to_terminal,
        )
        while True:
            event = await subscriber.get()
            if event is None:
                return
            if terminal_event_future is None or terminal_event_future.done():
                continue
            terminal_outcome = streaming_runner_module._terminal_event_outcome(event)
            if terminal_outcome is None:
                continue
            await asyncio.sleep(0.07)
            fake_clock.advance(0.07)
            terminal_event_future.set_result(terminal_outcome)

    monkeypatch.setattr(
        streaming_runner_module,
        "_consume_subscriber_events",
        _delayed_terminal_consume,
    )

    run = Spawn(
        spawn_id=SpawnId("r-heartbeat-1"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rh1",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )
    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
            clock=fake_clock,
            heartbeat_touch=fake_heartbeat.touch,
            heartbeat_interval_secs=0.02,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    assert len(fake_heartbeat.touches) >= 2
    intervals = [
        later - earlier for earlier, later in pairwise(fake_heartbeat.touches)
    ]
    assert intervals
    assert max(intervals) <= 0.7


@pytest.mark.asyncio
async def test_execute_with_streaming_marks_finalizing_before_terminal_finalize(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_connection_class,
    )

    call_order: list[str] = []
    original_mark_finalizing = streaming_runner_module.spawn_store.mark_finalizing
    original_finalize_spawn = streaming_runner_module.spawn_store.finalize_spawn

    def _tracked_mark_finalizing(*args, **kwargs) -> bool:  # type: ignore[no-untyped-def]
        call_order.append("mark_finalizing")
        return original_mark_finalizing(*args, **kwargs)

    def _tracked_finalize_spawn(*args, **kwargs) -> bool:  # type: ignore[no-untyped-def]
        call_order.append("finalize_spawn")
        return original_finalize_spawn(*args, **kwargs)

    monkeypatch.setattr(
        streaming_runner_module.spawn_store,
        "mark_finalizing",
        _tracked_mark_finalizing,
    )
    monkeypatch.setattr(
        streaming_runner_module.spawn_store,
        "finalize_spawn",
        _tracked_finalize_spawn,
    )

    run = Spawn(
        spawn_id=SpawnId("r-finalizing-order-1"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rfo1",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )
    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    assert call_order
    assert "mark_finalizing" in call_order
    assert "finalize_spawn" in call_order
    assert call_order.index("mark_finalizing") < call_order.index("finalize_spawn")


@pytest.mark.asyncio
async def test_execute_with_streaming_tolerates_mark_finalizing_cas_miss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_connection_class,
    )

    logged_messages: list[str] = []

    def _cas_miss_mark_finalizing(*_args, **_kwargs) -> bool:
        return False

    def _capture_info(message: str, *_args, **_kwargs) -> None:
        logged_messages.append(message)

    monkeypatch.setattr(
        streaming_runner_module.spawn_store,
        "mark_finalizing",
        _cas_miss_mark_finalizing,
    )
    monkeypatch.setattr(streaming_runner_module.logger, "info", _capture_info)

    run = Spawn(
        spawn_id=SpawnId("r-finalizing-cas-miss-1"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rfcm1",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )
    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert any("CAS miss" in message for message in logged_messages)


@pytest.mark.asyncio
async def test_execute_with_streaming_cancels_heartbeat_when_finalize_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_connection_class,
    )

    fake_clock = FakeClock(start=1000.0)
    fake_heartbeat = FakeHeartbeat()
    fake_heartbeat.set_clock(fake_clock)

    def _raising_finalize_spawn(*_args, **_kwargs) -> bool:
        raise RuntimeError("streaming finalize boom")

    monkeypatch.setattr(
        streaming_runner_module.spawn_store,
        "finalize_spawn",
        _raising_finalize_spawn,
    )

    run = Spawn(
        spawn_id=SpawnId("r-heartbeat-2"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rh2",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    with pytest.raises(RuntimeError, match="streaming finalize boom"):
        await asyncio.wait_for(
            _execute_with_context(
                run,
                request=_build_plan(),
                repo_root=tmp_path,
                state_root=state_root,
                artifacts=artifacts,
                registry=registry,
                cwd=tmp_path,
                clock=fake_clock,
                heartbeat_touch=fake_heartbeat.touch,
                heartbeat_interval_secs=0.01,
            ),
            timeout=1.0,
        )

    touched_count = len(fake_heartbeat.touches)
    await asyncio.sleep(0.05)
    assert len(fake_heartbeat.touches) == touched_count


@pytest.mark.asyncio
async def test_execute_with_streaming_cancels_heartbeat_when_finalize_raises_value_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_connection_class,
    )

    fake_clock = FakeClock(start=1000.0)
    fake_heartbeat = FakeHeartbeat()
    fake_heartbeat.set_clock(fake_clock)

    def _raising_finalize_spawn(*_args, **_kwargs) -> bool:
        raise ValueError("streaming finalize value error")

    monkeypatch.setattr(
        streaming_runner_module.spawn_store,
        "finalize_spawn",
        _raising_finalize_spawn,
    )

    run = Spawn(
        spawn_id=SpawnId("r-heartbeat-3"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rh3",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )

    with pytest.raises(ValueError, match="streaming finalize value error"):
        await asyncio.wait_for(
            _execute_with_context(
                run,
                request=_build_plan(),
                repo_root=tmp_path,
                state_root=state_root,
                artifacts=artifacts,
                registry=registry,
                cwd=tmp_path,
                clock=fake_clock,
                heartbeat_touch=fake_heartbeat.touch,
                heartbeat_interval_secs=0.01,
            ),
            timeout=1.0,
        )

    touched_count = len(fake_heartbeat.touches)
    await asyncio.sleep(0.05)
    assert len(fake_heartbeat.touches) == touched_count


@pytest.mark.asyncio
async def test_execute_with_streaming_continues_when_terminal_heartbeat_touch_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_runtime_state_root(tmp_path)
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyCodexHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_connection_class,
    )

    fake_clock = FakeClock(start=1000.0)
    warning_messages: list[str] = []

    class _FailingHeartbeat(FakeHeartbeat):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def touch(self) -> None:
            self.calls += 1
            if self.calls >= 2:
                raise OSError("permission denied")
            super().touch()

    failing_heartbeat = _FailingHeartbeat()
    failing_heartbeat.set_clock(fake_clock)

    def _capture_warning(message: str, *_args, **_kwargs) -> None:
        warning_messages.append(message)

    monkeypatch.setattr(streaming_runner_module.logger, "warning", _capture_warning)

    run = Spawn(
        spawn_id=SpawnId("r-heartbeat-touch-fail-1"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    spawn_store.start_spawn(
        state_root,
        chat_id="test-chat-rhtf1",
        model=str(run.model),
        agent="",
        harness="codex",
        kind="streaming",
        prompt=run.prompt,
        spawn_id=run.spawn_id,
        launch_mode="foreground",
        status="queued",
    )
    exit_code = await asyncio.wait_for(
        _execute_with_context(
            run,
            request=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
            clock=fake_clock,
            heartbeat_touch=failing_heartbeat.touch,
            heartbeat_interval_secs=60.0,
        ),
        timeout=1.0,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert any(
        "Failed to touch heartbeat after entering finalizing" in msg
        for msg in warning_messages
    )
