
import asyncio
import json
import sys
import textwrap
from pathlib import Path

import pytest

from meridian.lib.core.domain import Spawn, TokenUsage
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.adapter import ArtifactStore as HarnessArtifactStore
from meridian.lib.harness.adapter import (
    BaseHarnessAdapter,
    HarnessCapabilities,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.core.types import HarnessId, ModelId, SpawnId


class ScriptHarnessAdapter(BaseHarnessAdapter):
    def __init__(self, *, command: tuple[str, ...]) -> None:
        self._command = command

    @property
    def id(self) -> HarnessId:
        return HarnessId("exec-script")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        return [*self._command, *perms.resolve_flags(self.id), *run.extra_args]

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def parse_stream_event(self, line: str) -> StreamEvent | None:
        _ = line
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


def _fetch_run_row(space_dir: Path, spawn_id: SpawnId) -> spawn_store.SpawnRecord:
    row = spawn_store.get_spawn(space_dir, spawn_id)
    assert row is not None
    return row


def _write_script(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")


def _read_output_payload(artifacts: LocalStore, spawn_id: SpawnId) -> dict[str, object]:
    raw = artifacts.get(make_artifact_key(spawn_id, "output.jsonl")).decode("utf-8")
    return json.loads(raw.strip())


@pytest.mark.asyncio
async def test_execute_retries_retryable_errors_up_to_max(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="retry me")
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
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
        max_retries=3,
        retry_backoff_seconds=0.0,
    )

    assert exit_code == 1
    assert counter.read_text(encoding="utf-8") == "4"
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.status == "failed"
    assert row.error is None


@pytest.mark.asyncio
async def test_execute_does_not_retry_unrecoverable_errors(tmp_path: Path) -> None:
    run, _space_dir = _create_run(tmp_path, prompt="fail once")
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
        repo_root=tmp_path,
        space_dir=resolve_state_paths(tmp_path).root_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
        max_retries=3,
        retry_backoff_seconds=0.0,
    )

    assert exit_code == 1
    assert counter.read_text(encoding="utf-8") == "1"


@pytest.mark.asyncio
async def test_execute_sets_timeout_failure_reason(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="timeout")
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
        repo_root=tmp_path,
        space_dir=space_dir,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
        timeout_seconds=0.05,
        kill_grace_seconds=0.05,
        max_retries=3,
        retry_backoff_seconds=0.0,
    )

    assert exit_code == 3
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.status == "failed"
    assert row.error == "timeout"
    assert _read_output_payload(artifacts, run.spawn_id) == {
        "error_code": "harness_empty_output",
        "failure_reason": "timeout",
        "exit_code": 3,
        "timed_out": True,
    }


@pytest.mark.asyncio
async def test_execute_sets_cancelled_failure_reason(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="cancel")
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
            repo_root=tmp_path,
            space_dir=space_dir,
            artifacts=artifacts,
            registry=registry,
            harness_id=adapter.id,
            cwd=tmp_path,
            timeout_seconds=None,
            kill_grace_seconds=0.05,
            max_retries=0,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    exit_code = await task

    assert exit_code == 130
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.status == "failed"
    assert row.error == "cancelled"
