
import asyncio
import json
import signal
import sys
import textwrap
from pathlib import Path

import pytest

from meridian.lib.launch import runner as launch_runner
from meridian.lib.core.domain import Spawn, TokenUsage
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.adapter import ArtifactStore as HarnessArtifactStore
from meridian.lib.harness.adapter import (
    BaseSubprocessHarness,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver
from meridian.lib.ops.spawn.plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.core.types import HarnessId, ModelId, SpawnId


class ScriptHarnessAdapter(BaseSubprocessHarness):
    def __init__(self, *, command: tuple[str, ...]) -> None:
        self._command = command

    @property
    def id(self) -> HarnessId:
        return HarnessId.CODEX

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        return [*self._command, *perms.resolve_flags(self.id), *run.extra_args]

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


def _create_run(repo_root: Path, *, prompt: str, name: str = "exec") -> tuple[Spawn, Path]:
    run = Spawn(
        spawn_id=SpawnId("r1"),
        prompt=prompt,
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    return run, resolve_state_paths(repo_root).root_dir


def _fetch_run_row(state_root: Path, spawn_id: SpawnId) -> spawn_store.SpawnRecord:
    row = spawn_store.get_spawn(state_root, spawn_id)
    assert row is not None
    return row


def _write_script(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")


def _read_output_payload(artifacts: LocalStore, spawn_id: SpawnId) -> dict[str, object]:
    raw = artifacts.get(make_artifact_key(spawn_id, "output.jsonl")).decode("utf-8")
    return json.loads(raw.strip())


def _build_plan(
    run: Spawn,
    harness_id: HarnessId,
    *,
    timeout_seconds: float | None = None,
    kill_grace_seconds: float = 30.0,
    max_retries: int = 0,
    retry_backoff_seconds: float = 2.0,
) -> PreparedSpawnPlan:
    return PreparedSpawnPlan(
        model=str(run.model),
        harness_id=str(harness_id),
        prompt=run.prompt,
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
            timeout_secs=timeout_seconds,
            kill_grace_secs=kill_grace_seconds,
            max_retries=max_retries,
            retry_backoff_secs=retry_backoff_seconds,
            permission_config=PermissionConfig(),
            permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
            allowed_tools=(),
        ),
        cli_command=(),
    )


@pytest.mark.asyncio
async def test_execute_retries_retryable_errors_up_to_max(tmp_path: Path) -> None:
    run, state_root = _create_run(tmp_path, prompt="retry me")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    counter = tmp_path / "retryable-count.txt"
    script = tmp_path / "retryable.py"
    _write_script(
        script,
        """
        from pathlib import Path
        import sys

        counter = Path(sys.argv[1])
        if counter.exists():
            value = int(counter.read_text(encoding="utf-8"))
        else:
            value = 0
        counter.write_text(str(value + 1), encoding="utf-8")
        print("network error: connection reset", file=sys.stderr, flush=True)
        raise SystemExit(1)
        """,
    )

    adapter = ScriptHarnessAdapter(command=(sys.executable, str(script), str(counter)))
    registry = HarnessRegistry()
    registry.register(adapter)

    exit_code = await execute_with_finalization(
        run,
        plan=_build_plan(
            run,
            adapter.id,
            max_retries=3,
            retry_backoff_seconds=0.0,
        ),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert exit_code == 1
    assert counter.read_text(encoding="utf-8") == "4"
    row = _fetch_run_row(state_root, run.spawn_id)
    assert row.status == "failed"
    assert row.error is None


@pytest.mark.asyncio
async def test_execute_does_not_retry_unrecoverable_errors(tmp_path: Path) -> None:
    run, _state_root = _create_run(tmp_path, prompt="fail once")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    counter = tmp_path / "unrecoverable-count.txt"
    script = tmp_path / "unrecoverable.py"
    _write_script(
        script,
        """
        from pathlib import Path
        import sys

        counter = Path(sys.argv[1])
        if counter.exists():
            value = int(counter.read_text(encoding="utf-8"))
        else:
            value = 0
        counter.write_text(str(value + 1), encoding="utf-8")
        print("model not found", file=sys.stderr, flush=True)
        raise SystemExit(1)
        """,
    )

    adapter = ScriptHarnessAdapter(command=(sys.executable, str(script), str(counter)))
    registry = HarnessRegistry()
    registry.register(adapter)

    exit_code = await execute_with_finalization(
        run,
        plan=_build_plan(
            run,
            adapter.id,
            max_retries=3,
            retry_backoff_seconds=0.0,
        ),
        repo_root=tmp_path,
        state_root=resolve_state_paths(tmp_path).root_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert exit_code == 1
    assert counter.read_text(encoding="utf-8") == "1"


@pytest.mark.asyncio
async def test_execute_sets_timeout_failure_reason(tmp_path: Path) -> None:
    run, state_root = _create_run(tmp_path, prompt="timeout")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    script = tmp_path / "timeout.py"
    _write_script(
        script,
        """
        import time

        time.sleep(2.0)
        """,
    )
    adapter = ScriptHarnessAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    exit_code = await execute_with_finalization(
        run,
        plan=_build_plan(
            run,
            adapter.id,
            timeout_seconds=0.05,
            kill_grace_seconds=0.05,
            max_retries=3,
            retry_backoff_seconds=0.0,
        ),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert exit_code == 3
    row = _fetch_run_row(state_root, run.spawn_id)
    assert row.status == "failed"
    assert row.error == "timeout"
    assert _read_output_payload(artifacts, run.spawn_id) == {
        "error_code": "harness_empty_output",
        "failure_reason": "timeout",
        "exit_code": 3,
        "timed_out": True,
    }


@pytest.mark.asyncio
async def test_execute_handles_large_stdout_json_lines(tmp_path: Path) -> None:
    run, state_root = _create_run(tmp_path, prompt="large line")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    script = tmp_path / "large_line.py"
    _write_script(
        script,
        """
        import json
        import sys
        from pathlib import Path

        report_path = Path(sys.argv[1])
        payload = {"type": "tool_result", "content": "x" * 70000}
        print(json.dumps(payload), flush=True)
        report_path.write_text("# Large Line OK\\n", encoding="utf-8")
        print(json.dumps({"type": "result", "subtype": "success"}), flush=True)
        """,
    )

    class LargeLineHarnessAdapter(ScriptHarnessAdapter):
        def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
            return [
                *self._command,
                run.report_output_path or "",
                *perms.resolve_flags(self.id),
                *run.extra_args,
            ]

    adapter = LargeLineHarnessAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    exit_code = await execute_with_finalization(
        run,
        plan=_build_plan(
            run,
            adapter.id,
            max_retries=0,
        ),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert exit_code == 0
    row = _fetch_run_row(state_root, run.spawn_id)
    assert row.status == "succeeded"
    output = artifacts.get(make_artifact_key(run.spawn_id, "output.jsonl")).decode("utf-8")
    assert '"type": "tool_result"' in output
    assert len(output) > 70000


@pytest.mark.asyncio
async def test_execute_treats_watchdog_termination_after_report_as_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    run, state_root = _create_run(tmp_path, prompt="report then linger")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    script = tmp_path / "report_then_linger.py"
    _write_script(
        script,
        """
        import json
        import sys
        import time
        from pathlib import Path

        report_path = Path(sys.argv[1])
        print(json.dumps({"type": "message", "text": "working"}), flush=True)
        report_path.write_text("# Finished\\n\\nActual work is done.\\n", encoding="utf-8")
        print(json.dumps({"type": "result", "subtype": "success"}), flush=True)
        time.sleep(5.0)
        """,
    )

    class ReportHarnessAdapter(ScriptHarnessAdapter):
        def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
            return [
                *self._command,
                run.report_output_path or "",
                *perms.resolve_flags(self.id),
                *run.extra_args,
            ]

    async def fast_watchdog(
        report_path: Path,
        process: asyncio.subprocess.Process,
        grace_secs: float = 60.0,
    ) -> bool:
        _ = grace_secs
        while not report_path.exists():
            if process.returncode is not None:
                return False
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)
        if process.returncode is not None:
            return False
        await launch_runner.terminate_process(process, grace_seconds=0.05)
        return True

    adapter = ReportHarnessAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)
    monkeypatch.setattr(launch_runner, "_report_watchdog", fast_watchdog)

    exit_code = await execute_with_finalization(
        run,
        plan=_build_plan(
            run,
            adapter.id,
            max_retries=0,
        ),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert exit_code == 0
    row = _fetch_run_row(state_root, run.spawn_id)
    assert row.status == "succeeded"
    assert row.exit_code == 0
    report = (state_root / "spawns" / str(run.spawn_id) / "report.md").read_text(encoding="utf-8")
    assert "Actual work is done." in report


@pytest.mark.asyncio
async def test_execute_sets_cancelled_failure_reason(tmp_path: Path) -> None:
    run, state_root = _create_run(tmp_path, prompt="cancel")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    script = tmp_path / "cancel.py"
    _write_script(
        script,
        """
        import time

        time.sleep(5.0)
        """,
    )
    adapter = ScriptHarnessAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    task = asyncio.create_task(
        execute_with_finalization(
            run,
            plan=_build_plan(
                run,
                adapter.id,
                timeout_seconds=None,
                kill_grace_seconds=0.05,
                max_retries=0,
            ),
            repo_root=tmp_path,
            state_root=state_root,
            artifacts=artifacts,
            registry=registry,
            harness_id=adapter.id,
            cwd=tmp_path,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    exit_code = await task

    assert exit_code == 130
    row = _fetch_run_row(state_root, run.spawn_id)
    assert row.status == "failed"
    assert row.error == "cancelled"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("received_signal", "durable_report", "expected_status", "expected_exit_code"),
    [
        pytest.param(signal.SIGTERM, True, "succeeded", 0, id="forwarded-sigterm-with-report"),
        pytest.param(None, True, "succeeded", 0, id="raw-sigterm-with-report"),
        pytest.param(signal.SIGTERM, False, "failed", 143, id="forwarded-sigterm-without-report"),
    ],
)
async def test_execute_resolves_sigterm_after_report_regardless_of_received_signal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    received_signal: signal.Signals | None,
    durable_report: bool,
    expected_status: str,
    expected_exit_code: int,
) -> None:
    run, state_root = _create_run(tmp_path, prompt="sigterm lifecycle")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    adapter = ScriptHarnessAdapter(command=("unused-command",))
    registry = HarnessRegistry()
    registry.register(adapter)

    async def fake_spawn_and_stream(
        *,
        spawn_id: SpawnId,
        output_log_path: Path,
        stderr_log_path: Path,
        report_watchdog_path: Path | None = None,
        **_: object,
    ) -> launch_runner.SpawnResult:
        _ = spawn_id
        if durable_report and report_watchdog_path is not None:
            report_watchdog_path.parent.mkdir(parents=True, exist_ok=True)
            report_watchdog_path.write_text("# Done\n\nWork completed.\n", encoding="utf-8")

        return launch_runner.SpawnResult(
            exit_code=143,
            raw_return_code=-signal.SIGTERM.value,
            timed_out=False,
            received_signal=received_signal,
            output_log_path=output_log_path,
            stderr_log_path=stderr_log_path,
            budget_breach=None,
            terminated_by_report_watchdog=False,
        )

    monkeypatch.setattr(launch_runner, "spawn_and_stream", fake_spawn_and_stream)

    exit_code = await execute_with_finalization(
        run,
        plan=_build_plan(
            run,
            adapter.id,
            max_retries=0,
        ),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert exit_code == expected_exit_code
    row = _fetch_run_row(state_root, run.spawn_id)
    assert row.status == expected_status
    assert row.exit_code == expected_exit_code
