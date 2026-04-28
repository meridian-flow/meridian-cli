"""Unit tests for SpawnApplicationService terminal finalization."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import meridian.lib.core.telemetry as telemetry
from meridian.lib.core.lifecycle import SpawnLifecycleService
from meridian.lib.core.spawn_service import SpawnApplicationService
from meridian.lib.core.types import SpawnId
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import RuntimePaths
from meridian.lib.state.spawn.repository import FileSpawnRepository


@pytest.fixture(autouse=True)
def _reset_telemetry_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry, "_GLOBAL_OBSERVERS", [])
    monkeypatch.setattr(telemetry, "_GLOBAL_EVENT_COUNTER", telemetry.SpawnEventCounter())
    monkeypatch.setattr(telemetry, "_debug_trace_registered", False)


def _start_running_spawn(lifecycle: SpawnLifecycleService) -> SpawnId:
    return SpawnId(
        lifecycle.start(
            chat_id="chat-1",
            model="model-1",
            agent="coder",
            harness="codex",
            prompt="do the thing",
            status="running",
        )
    )


@pytest.mark.asyncio
async def test_complete_spawn_returns_true_for_first_terminal_transition(
    tmp_path: Path,
) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    spawn_id = _start_running_spawn(lifecycle)

    transitioned = await service.complete_spawn(
        spawn_id,
        "succeeded",
        0,
        origin="runner",
        duration_secs=1.5,
        total_cost_usd=0.25,
        input_tokens=10,
        output_tokens=20,
    )

    record = spawn_store.get_spawn(tmp_path, spawn_id)
    assert transitioned is True
    assert record is not None
    assert record.status == "succeeded"
    assert record.exit_code == 0
    assert record.duration_secs == 1.5
    assert record.total_cost_usd == 0.25
    assert record.input_tokens == 10
    assert record.output_tokens == 20
    assert record.terminal_origin == "runner"


@pytest.mark.asyncio
async def test_get_spawn_failure_returns_failure_sentinel(tmp_path: Path) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    spawn_id = _start_running_spawn(lifecycle)

    await service.complete_spawn(spawn_id, "failed", 2, origin="runner")

    failure = service.get_spawn_failure(spawn_id)
    assert failure is not None
    assert failure.spawn_id == str(spawn_id)
    assert failure.exit_code == 2
    assert failure.reason == "runner"


@pytest.mark.asyncio
async def test_get_spawn_failure_ignores_sentinel_when_spawn_is_not_failed(
    tmp_path: Path,
) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    spawn_id = _start_running_spawn(lifecycle)

    lifecycle.finalize(str(spawn_id), "failed", 2, origin="reconciler")
    lifecycle.finalize(str(spawn_id), "succeeded", 0, origin="launcher")

    assert service.get_spawn_failure(spawn_id) is None


@pytest.mark.asyncio
async def test_complete_spawn_returns_false_after_terminal_transition(
    tmp_path: Path,
) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    spawn_id = _start_running_spawn(lifecycle)

    first = await service.complete_spawn(spawn_id, "succeeded", 0, origin="runner")
    second = await service.complete_spawn(spawn_id, "failed", 1, origin="cancel")

    record = spawn_store.get_spawn(tmp_path, spawn_id)
    assert first is True
    assert second is False
    assert record is not None
    assert record.status == "succeeded"
    assert record.terminal_origin == "runner"


@pytest.mark.asyncio
async def test_complete_spawn_serializes_concurrent_terminal_attempts(
    tmp_path: Path,
) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    spawn_id = _start_running_spawn(lifecycle)

    results = await asyncio.gather(
        service.complete_spawn(spawn_id, "succeeded", 0, origin="runner"),
        service.complete_spawn(spawn_id, "cancelled", 130, origin="cancel"),
    )

    events = FileSpawnRepository(RuntimePaths.from_root_dir(tmp_path)).read_events()
    finalize_events = [event for event in events if event.event == "finalize"]
    record = spawn_store.get_spawn(tmp_path, spawn_id)
    assert sorted(results) == [False, True]
    assert len(finalize_events) == 1
    assert record is not None
    assert record.status in {"succeeded", "cancelled"}


# ---- Tests for prepare_spawn (SEAM-1, SEAM-2, SEAM-3) ----


@pytest.fixture
def mock_harness_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock the harness registry to avoid real harness dependencies."""
    from unittest.mock import MagicMock

    from meridian.lib.harness.registry import HarnessRegistry

    mock_registry = MagicMock(spec=HarnessRegistry)
    mock_adapter = MagicMock()
    mock_adapter.id = MagicMock()
    mock_adapter.id.value = "codex"
    mock_adapter.capabilities = MagicMock()
    mock_adapter.capabilities.supports_native_agents = False
    mock_adapter.capabilities.supports_session_resume = False
    mock_adapter.capabilities.supports_session_fork = False
    mock_adapter.run_prompt_policy.return_value = MagicMock(skill_injection_mode="none")
    mock_adapter.preflight.return_value = MagicMock(
        expanded_passthrough_args=(),
        extra_env={},
    )
    mock_adapter.project_content.return_value = MagicMock(
        system_prompt="",
        user_turn_content="test prompt",
    )
    mock_adapter.seed_session.return_value = MagicMock(
        session_id=None,
        session_args=(),
    )
    mock_registry.get_subprocess_harness.return_value = mock_adapter
    monkeypatch.setattr(
        "meridian.lib.harness.registry.get_default_harness_registry",
        lambda: mock_registry,
    )
    return mock_registry


@pytest.mark.asyncio
async def test_prepare_spawn_creates_row_with_resolved_metadata(
    tmp_path: Path,
    mock_harness_registry: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEAM-2: Row metadata reflects resolved values, not placeholders."""
    from meridian.lib.core.spawn_service import PreparedSpawn, SpawnApplicationService
    from meridian.lib.harness.registry import get_default_harness_registry
    from meridian.lib.launch.request import LaunchRuntime, SpawnRequest

    # Set up project paths
    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime_root = tmp_path

    # Mock build_launch_context to return a valid context
    from unittest.mock import MagicMock

    mock_launch_ctx = MagicMock()
    mock_launch_ctx.resolved_request = MagicMock()
    mock_launch_ctx.resolved_request.model = "gpt-5.4"
    mock_launch_ctx.resolved_request.harness = "codex"
    mock_launch_ctx.resolved_request.agent = "coder"
    mock_launch_ctx.resolved_request.prompt = "test prompt"
    mock_launch_ctx.resolved_request.skills = ()
    mock_launch_ctx.resolved_request.skill_paths = ()
    mock_launch_ctx.resolved_request.session = MagicMock()
    mock_launch_ctx.resolved_request.session.requested_harness_session_id = None
    mock_launch_ctx.resolved_request.agent_metadata = {}
    mock_launch_ctx.child_cwd = project_root
    mock_launch_ctx.work_id = None
    mock_launch_ctx.env_overrides = {"MERIDIAN_SPAWN_ID": "p1"}

    monkeypatch.setattr(
        "meridian.lib.core.spawn_service.build_launch_context",
        lambda **kwargs: mock_launch_ctx,
    )

    lifecycle = SpawnLifecycleService(runtime_root)
    service = SpawnApplicationService(runtime_root, lifecycle)

    request = SpawnRequest(prompt="test prompt", harness="codex", model="gpt-5.4")
    runtime = LaunchRuntime(
        runtime_root=runtime_root.as_posix(),
        project_paths_project_root=project_root.as_posix(),
        project_paths_execution_cwd=project_root.as_posix(),
    )

    prepared = await service.prepare_spawn(
        request=request,
        runtime=runtime,
        harness_registry=get_default_harness_registry(),
        chat_id="chat-1",
        initial_status="running",
    )

    # Verify prepared spawn has resolved metadata
    assert isinstance(prepared, PreparedSpawn)
    assert prepared.resolved_model == "gpt-5.4"
    assert prepared.resolved_harness == "codex"
    assert prepared.resolved_agent == "coder"

    # Verify row was created with resolved metadata
    record = spawn_store.get_spawn(runtime_root, prepared.spawn_id)
    assert record is not None
    assert record.model == "gpt-5.4"
    assert record.harness == "codex"
    assert record.agent == "coder"


@pytest.mark.asyncio
async def test_prepare_spawn_projects_env_overrides_from_launch_context(
    tmp_path: Path,
    mock_harness_registry: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEAM-3.2: env_overrides populated from LaunchContext.env_overrides."""
    from meridian.lib.core.spawn_service import SpawnApplicationService
    from meridian.lib.harness.registry import get_default_harness_registry
    from meridian.lib.launch.request import LaunchRuntime, SpawnRequest

    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime_root = tmp_path

    from unittest.mock import MagicMock

    mock_launch_ctx = MagicMock()
    mock_launch_ctx.resolved_request = MagicMock()
    mock_launch_ctx.resolved_request.model = "gpt-5.4"
    mock_launch_ctx.resolved_request.harness = "codex"
    mock_launch_ctx.resolved_request.agent = "coder"
    mock_launch_ctx.resolved_request.prompt = "test prompt"
    mock_launch_ctx.resolved_request.skills = ()
    mock_launch_ctx.resolved_request.skill_paths = ()
    mock_launch_ctx.resolved_request.session = MagicMock()
    mock_launch_ctx.resolved_request.session.requested_harness_session_id = None
    mock_launch_ctx.resolved_request.agent_metadata = {}
    mock_launch_ctx.child_cwd = project_root
    mock_launch_ctx.work_id = "work-123"
    mock_launch_ctx.env_overrides = {
        "MERIDIAN_SPAWN_ID": "p1",
        "MERIDIAN_WORK_ID": "work-123",
    }

    monkeypatch.setattr(
        "meridian.lib.core.spawn_service.build_launch_context",
        lambda **kwargs: mock_launch_ctx,
    )

    lifecycle = SpawnLifecycleService(runtime_root)
    service = SpawnApplicationService(runtime_root, lifecycle)

    request = SpawnRequest(prompt="test prompt", harness="codex")
    runtime = LaunchRuntime(
        runtime_root=runtime_root.as_posix(),
        project_paths_project_root=project_root.as_posix(),
        project_paths_execution_cwd=project_root.as_posix(),
    )

    prepared = await service.prepare_spawn(
        request=request,
        runtime=runtime,
        harness_registry=get_default_harness_registry(),
        chat_id="chat-1",
        initial_status="running",
    )

    # Verify ConnectionConfig has env_overrides from LaunchContext
    assert "MERIDIAN_SPAWN_ID" in prepared.connection_config.env_overrides
    assert "MERIDIAN_WORK_ID" in prepared.connection_config.env_overrides


@pytest.mark.asyncio
async def test_prepare_spawn_no_row_on_resolution_failure(
    tmp_path: Path,
    mock_harness_registry: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SEAM-1: No spawn row exists on launch composition failure."""
    from meridian.lib.core.spawn_service import SpawnApplicationService
    from meridian.lib.harness.registry import get_default_harness_registry
    from meridian.lib.launch.request import LaunchRuntime, SpawnRequest

    project_root = tmp_path / "project"
    project_root.mkdir()
    runtime_root = tmp_path

    # Make build_launch_context raise an exception
    def failing_build_launch_context(**kwargs: object) -> None:
        raise ValueError("Bad model alias")

    monkeypatch.setattr(
        "meridian.lib.core.spawn_service.build_launch_context",
        failing_build_launch_context,
    )

    lifecycle = SpawnLifecycleService(runtime_root)
    service = SpawnApplicationService(runtime_root, lifecycle)

    request = SpawnRequest(prompt="test prompt", harness="codex", model="bad-model")
    runtime = LaunchRuntime(
        runtime_root=runtime_root.as_posix(),
        project_paths_project_root=project_root.as_posix(),
        project_paths_execution_cwd=project_root.as_posix(),
    )

    # Verify no spawns exist before
    assert spawn_store.list_spawns(runtime_root) == []

    with pytest.raises(ValueError, match="Bad model alias"):
        await service.prepare_spawn(
            request=request,
            runtime=runtime,
            harness_registry=get_default_harness_registry(),
            chat_id="chat-1",
        )

    # Verify still no spawns exist after failure
    assert spawn_store.list_spawns(runtime_root) == []
