import sys
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
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.ops.spawn.plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_state_paths


class RecordingHarnessAdapter(BaseSubprocessHarness):
    def __init__(self, *, recorded_runs: list[SpawnParams]) -> None:
        self._recorded_runs = recorded_runs

    @property
    def id(self) -> HarnessId:
        return HarnessId.CODEX

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        self._recorded_runs.append(run)
        return [sys.executable, "-c", "raise SystemExit(0)", *perms.resolve_flags(self.id)]

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        _ = run
        return None

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)


class ForkingRecordingHarnessAdapter(RecordingHarnessAdapter):
    def __init__(
        self,
        *,
        recorded_runs: list[SpawnParams],
        events: list[tuple[str, str, bool]],
    ) -> None:
        super().__init__(recorded_runs=recorded_runs)
        self._events = events

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities(supports_session_fork=True)

    def fork_session(self, source_session_id: str) -> str:
        self._events.append(("fork", source_session_id, True))
        return f"{source_session_id}-forked"

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        self._events.append(
            ("build", run.continue_harness_session_id or "", bool(run.continue_fork))
        )
        return [sys.executable, "-c", "raise SystemExit(0)", *perms.resolve_flags(self.id)]


@pytest.mark.asyncio
async def test_execute_with_finalization_passes_adhoc_agent_payload(tmp_path: Path) -> None:
    run = Spawn(
        spawn_id=SpawnId("r1"),
        prompt="hello",
        model=ModelId("claude-sonnet-4-6"),
        status="queued",
    )
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    recorded_runs: list[SpawnParams] = []

    adapter = RecordingHarnessAdapter(recorded_runs=recorded_runs)
    registry = HarnessRegistry()
    registry.register(adapter)

    plan = PreparedSpawnPlan(
        model=str(run.model),
        harness_id=str(adapter.id),
        prompt=run.prompt,
        agent_name="reviewer",
        skills=(),
        skill_paths=(),
        reference_files=(),
        template_vars={},
        mcp_tools=(),
        session_agent="reviewer",
        session_agent_path="",
        adhoc_agent_payload='{"reviewer":{"description":"desc","prompt":"body"}}',
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

    await execute_with_finalization(
        run,
        plan=plan,
        repo_root=tmp_path,
        state_root=resolve_state_paths(tmp_path).root_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert recorded_runs
    assert (
        recorded_runs[0].adhoc_agent_payload
        == '{"reviewer":{"description":"desc","prompt":"body"}}'
    )


@pytest.mark.asyncio
async def test_execute_with_finalization_materializes_codex_fork_before_build(
    tmp_path: Path,
) -> None:
    run = Spawn(
        spawn_id=SpawnId("r2"),
        prompt="hello",
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    state_root = resolve_state_paths(tmp_path).root_dir
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    recorded_runs: list[SpawnParams] = []
    events: list[tuple[str, str, bool]] = []
    observed_session_ids: list[str] = []

    adapter = ForkingRecordingHarnessAdapter(recorded_runs=recorded_runs, events=events)
    registry = HarnessRegistry()
    registry.register(adapter)

    plan = PreparedSpawnPlan(
        model=str(run.model),
        harness_id=str(adapter.id),
        prompt=run.prompt,
        agent_name="reviewer",
        skills=(),
        skill_paths=(),
        reference_files=(),
        template_vars={},
        mcp_tools=(),
        session_agent="reviewer",
        session_agent_path="",
        adhoc_agent_payload="",
        session=SessionContinuation(
            harness_session_id="source-session",
            continue_fork=True,
        ),
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

    await execute_with_finalization(
        run,
        plan=plan,
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
        harness_session_id_observer=observed_session_ids.append,
    )

    assert events[0] == ("fork", "source-session", True)
    assert events[1] == ("build", "source-session-forked", False)
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.harness_session_id == "source-session-forked"
    assert observed_session_ids == ["source-session-forked"]
