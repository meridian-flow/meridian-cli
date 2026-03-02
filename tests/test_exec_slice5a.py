"""Slice 5a execution/finalization behavior tests."""

from __future__ import annotations

import asyncio
import sys
import textwrap
from pathlib import Path

import pytest

from meridian.lib.domain import Spawn, TokenUsage
from meridian.lib.exec.spawn import execute_with_finalization
from meridian.lib.harness._common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.adapter import (
    ArtifactStore as HarnessArtifactStore,
)
from meridian.lib.harness.adapter import (
    HarnessCapabilities,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.space.space_file import create_space
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.types import HarnessId, ModelId, SpawnId, SpaceId


class ScriptHarnessAdapter:
    def __init__(self, *, command: tuple[str, ...]) -> None:
        self._command = command

    @property
    def id(self) -> HarnessId:
        return HarnessId("slice5-script")

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


def _create_run(repo_root: Path, *, prompt: str) -> tuple[Spawn, Path]:
    space = create_space(repo_root, name="slice5")
    run = Spawn(
        spawn_id=SpawnId("r1"),
        prompt=prompt,
        model=ModelId("gpt-5.3-codex"),
        status="queued",
        space_id=SpaceId(space.id),
    )
    return run, resolve_space_dir(repo_root, space.id)


def _fetch_run_row(space_dir: Path, spawn_id: SpawnId) -> spawn_store.SpawnRecord:
    row = spawn_store.get_spawn(space_dir, spawn_id)
    assert row is not None
    return row


def _write_script(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")


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
    run, space_dir = _create_run(tmp_path, prompt="fail once")
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
        space_dir=space_dir,
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
async def test_execute_marks_empty_success_output_as_failed(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="empty")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    script = tmp_path / "empty-success.py"
    _write_script(
        script,
        """
        raise SystemExit(0)
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
        max_retries=3,
        retry_backoff_seconds=0.0,
    )

    assert exit_code == 1
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.status == "failed"
    assert row.error == "missing_report"


@pytest.mark.asyncio
async def test_primary_kind_uses_optional_report_policy(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="empty-primary")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    spawn_store.start_spawn(
        space_dir,
        spawn_id=run.spawn_id,
        chat_id="c1",
        model=str(run.model),
        agent="primary",
        harness="codex",
        kind="primary",
        prompt=run.prompt,
    )

    script = tmp_path / "empty-primary-success.py"
    _write_script(
        script,
        """
        raise SystemExit(0)
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
        max_retries=0,
        retry_backoff_seconds=0.0,
    )

    assert exit_code == 1
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.kind == "primary"
    assert row.status == "failed"
    # Primary bypasses child report policy, so empty-output fallback remains.
    assert row.error == "empty_output"


@pytest.mark.asyncio
async def test_retry_does_not_reuse_stale_fallback_report(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="retry stale fallback")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    counter = tmp_path / "attempt-count.txt"
    script = tmp_path / "retry-stale-fallback.py"
    _write_script(
        script,
        """
        from pathlib import Path
        import sys

        counter = Path(sys.argv[1])
        if counter.exists():
            attempt = int(counter.read_text(encoding="utf-8"))
        else:
            attempt = 0
        counter.write_text(str(attempt + 1), encoding="utf-8")

        if attempt == 0:
            print('{"role":"assistant","content":"first attempt fallback report"}', flush=True)
            print("network error: timeout", file=sys.stderr, flush=True)
            raise SystemExit(1)

        # Successful exit with no output should still fail finalization as missing report.
        raise SystemExit(0)
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
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    assert exit_code == 1
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.status == "failed"
    assert row.error == "missing_report"
    assert not artifacts.exists(make_artifact_key(run.spawn_id, "report.md"))


@pytest.mark.asyncio
async def test_finalize_row_enriched_with_usage_cost_and_report(
    package_root: Path,
    tmp_path: Path,
) -> None:
    run, space_dir = _create_run(tmp_path, prompt="enrich")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    stream_fixture = tmp_path / "slice5-stream.jsonl"
    stream_fixture.write_text(
        (
            '{"role":"assistant","content":"Edited src/story/ch1.md","session_id":"sess-7",'
            '"files_touched":["src/story/ch1.md","_docs/plans/plan.md"]}\n'
            '{"role":"assistant","content":"Final summary."}\n'
        ),
        encoding="utf-8",
    )

    adapter = ScriptHarnessAdapter(
        command=(
            sys.executable,
            str(package_root / "tests" / "mock_harness.py"),
            "--tokens",
            '{"input_tokens":22,"output_tokens":7,"total_cost_usd":0.014}',
            "--stdout-file",
            str(stream_fixture),
        )
    )
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
        max_retries=0,
    )

    assert exit_code == 0
    row = _fetch_run_row(space_dir, run.spawn_id)
    assert row.status == "succeeded"
    assert row.input_tokens == 22
    assert row.output_tokens == 7
    assert row.total_cost_usd == pytest.approx(0.014)

    report_key = make_artifact_key(run.spawn_id, "report.md")
    assert artifacts.exists(report_key)
    assert "Final summary." in artifacts.get(report_key).decode("utf-8")


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
