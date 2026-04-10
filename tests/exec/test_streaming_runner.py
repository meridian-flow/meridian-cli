from __future__ import annotations

import asyncio
from pathlib import Path

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
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.connections.base import (
    ConnectionCapabilities,
    ConnectionConfig,
    HarnessEvent,
)
from meridian.lib.harness.launch_spec import ResolvedLaunchSpec
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch import streaming_runner as streaming_runner_module
from meridian.lib.launch.streaming_runner import execute_with_streaming, run_streaming_spawn
from meridian.lib.ops.spawn.plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_spawn_log_dir, resolve_state_paths
from meridian.lib.streaming import spawn_manager as spawn_manager_module


def _fake_connection_class(_harness_id: HarnessId) -> type[_HangingAfterTurnCompletedConnection]:
    return _HangingAfterTurnCompletedConnection


def _fake_report_hang_connection_class(
    _harness_id: HarnessId,
) -> type[_ReportThenHangConnection]:
    return _ReportThenHangConnection


def _fake_claude_result_connection_class(
    _harness_id: HarnessId,
) -> type[_ClaudeResultThenHangConnection]:
    return _ClaudeResultThenHangConnection


def _fake_opencode_idle_connection_class(
    _harness_id: HarnessId,
) -> type[_OpenCodeIdleThenHangConnection]:
    return _OpenCodeIdleThenHangConnection


class _DummyCodexHarness(BaseSubprocessHarness):
    @property
    def id(self) -> HarnessId:
        return HarnessId.CODEX

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

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
        return extract_session_id_from_artifacts(artifacts, spawn_id)


class _DummyClaudeHarness(_DummyCodexHarness):
    @property
    def id(self) -> HarnessId:
        return HarnessId.CLAUDE


class _DummyOpenCodeHarness(_DummyCodexHarness):
    @property
    def id(self) -> HarnessId:
        return HarnessId.OPENCODE


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


def _build_plan(
    harness_id: HarnessId = HarnessId.CODEX,
    model: str = "gpt-5.3-codex",
) -> PreparedSpawnPlan:
    return PreparedSpawnPlan(
        model=model,
        harness_id=harness_id.value,
        prompt="hello",
        agent_name=None,
        skills=(),
        skill_paths=(),
        reference_files=(),
        template_vars={},
        mcp_tools=(),
        session_agent="",
        session_agent_path="",
        session=SessionContinuation(),
        execution=ExecutionPolicy(
            timeout_secs=None,
            kill_grace_secs=30.0,
            max_retries=0,
            retry_backoff_secs=0.0,
            permission_config=PermissionConfig(),
            permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
            allowed_tools=(),
        ),
        cli_command=(),
    )


@pytest.mark.asyncio
async def test_run_streaming_spawn_finishes_on_turn_completed_without_connection_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
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
                model="gpt-5.3-codex",
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            params=SpawnParams(prompt="hello"),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p1"),
        ),
        timeout=0.5,
    )

    assert outcome.status == "succeeded"
    assert outcome.exit_code == 0


@pytest.mark.asyncio
async def test_execute_with_streaming_succeeds_when_turn_completes_but_connection_lingers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
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

    exit_code = await asyncio.wait_for(
        execute_with_streaming(
            run,
            plan=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=0.5,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    report = (state_root / "spawns" / str(run.spawn_id) / "report.md").read_text(encoding="utf-8")
    assert "Streaming turn completed." in report


@pytest.mark.asyncio
async def test_execute_with_streaming_succeeds_after_report_watchdog_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
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

    exit_code = await asyncio.wait_for(
        execute_with_streaming(
            run,
            plan=_build_plan(),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=0.5,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    report = (state_root / "spawns" / str(run.spawn_id) / "report.md").read_text(encoding="utf-8")
    assert "Watchdog fallback completed." in report


@pytest.mark.asyncio
async def test_run_streaming_spawn_finishes_on_claude_result_without_connection_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
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
                model="claude-opus-4-1",
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            params=SpawnParams(prompt="hello"),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p2"),
        ),
        timeout=0.5,
    )

    assert outcome.status == "succeeded"
    assert outcome.exit_code == 0


@pytest.mark.asyncio
async def test_execute_with_streaming_succeeds_when_claude_result_completes_but_connection_lingers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    registry = HarnessRegistry()
    registry.register(_DummyClaudeHarness())
    monkeypatch.setattr(spawn_manager_module, "ControlSocketServer", _FakeControlSocketServer)
    monkeypatch.setattr(
        "meridian.lib.harness.connections.get_connection_class",
        _fake_claude_result_connection_class,
    )

    run = Spawn(
        spawn_id=SpawnId("r3"),
        prompt="hello",
        model=ModelId("claude-opus-4-1"),
        status="queued",
    )

    exit_code = await asyncio.wait_for(
        execute_with_streaming(
            run,
            plan=_build_plan(HarnessId.CLAUDE, "claude-opus-4-1"),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=0.5,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    report = (state_root / "spawns" / str(run.spawn_id) / "report.md").read_text(encoding="utf-8")
    assert "Claude completed successfully." in report


@pytest.mark.asyncio
async def test_run_streaming_spawn_finishes_on_opencode_idle_without_connection_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
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
                model="openrouter/qwen/qwen3-coder:free",
                prompt="hello",
                repo_root=tmp_path,
                env_overrides={},
            ),
            params=SpawnParams(prompt="hello"),
            state_root=state_root,
            repo_root=tmp_path,
            spawn_id=SpawnId("p3"),
        ),
        timeout=0.5,
    )

    assert outcome.status == "succeeded"
    assert outcome.exit_code == 0


@pytest.mark.asyncio
async def test_execute_with_streaming_succeeds_when_opencode_idle_completes_but_connection_lingers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_root = resolve_state_paths(tmp_path).root_dir
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

    exit_code = await asyncio.wait_for(
        execute_with_streaming(
            run,
            plan=_build_plan(HarnessId.OPENCODE, "openrouter/qwen/qwen3-coder:free"),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            cwd=tmp_path,
        ),
        timeout=0.5,
    )

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    report = (state_root / "spawns" / str(run.spawn_id) / "report.md").read_text(encoding="utf-8")
    assert "OpenCode session became idle." in report
