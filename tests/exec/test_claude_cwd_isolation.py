"""Test CWD isolation for claude harness when running inside Claude Code.

When CLAUDECODE is set in the parent environment and the harness is claude,
the child subprocess CWD should be the spawn's log directory (not the project
root) to prevent the child from deleting the parent's task output file.
"""

import json
import sys
import textwrap
from pathlib import Path

import pytest

from meridian.lib.core.domain import Spawn, TokenUsage
from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import ArtifactStore as HarnessArtifactStore
from meridian.lib.harness.adapter import (
    BaseSubprocessHarness,
    HarnessCapabilities,
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
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_spawn_log_dir, resolve_state_paths


class ClaudeLikeAdapter(BaseSubprocessHarness):
    """Adapter that reports id='claude' to trigger CWD isolation."""

    def __init__(self, *, command: tuple[str, ...]) -> None:
        self._command = command

    @property
    def id(self) -> HarnessId:
        return HarnessId.CLAUDE

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        return list(self._command)

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def blocked_child_env_vars(self) -> frozenset[str]:
        return frozenset({"CLAUDECODE"})

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)


class NonClaudeAdapter(BaseSubprocessHarness):
    """Adapter with a non-claude id — CWD isolation should NOT trigger."""

    def __init__(self, *, command: tuple[str, ...]) -> None:
        self._command = command

    @property
    def id(self) -> HarnessId:
        return HarnessId.CODEX

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        return list(self._command)

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def extract_usage(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_session_id(self, artifacts: HarnessArtifactStore, spawn_id: SpawnId) -> str | None:
        return extract_session_id_from_artifacts(artifacts, spawn_id)


def _write_cwd_reporter_script(path: Path, output_path: Path) -> None:
    """Write a script that records its CWD and argv to a JSON file."""
    path.write_text(
        textwrap.dedent(f"""\
        import json, os, sys
        json.dump({{"cwd": os.getcwd(), "argv": sys.argv}}, open({str(output_path)!r}, "w"))
        print('{{"result": "ok"}}')
        """),
        encoding="utf-8",
    )


def _build_plan(run: Spawn, harness_id: HarnessId) -> PreparedSpawnPlan:
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
            permission_config=PermissionConfig(),
            permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
        ),
        cli_command=(),
    )


@pytest.mark.asyncio
async def test_claude_harness_uses_log_dir_cwd_when_claudecode_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When CLAUDECODE is set and harness is claude, child CWD should be log_dir."""
    monkeypatch.setenv("CLAUDECODE", "1")

    spawn_id = SpawnId("r1")
    run = Spawn(spawn_id=spawn_id, prompt="test", model=ModelId("test-model"), status="queued")
    state_root = resolve_state_paths(tmp_path).root_dir
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    cwd_report = tmp_path / "cwd-report.json"
    script = tmp_path / "reporter.py"
    _write_cwd_reporter_script(script, cwd_report)

    adapter = ClaudeLikeAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    exit_code = await execute_with_finalization(
        run,
        plan=_build_plan(run, adapter.id),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    assert exit_code == 0
    report = json.loads(cwd_report.read_text(encoding="utf-8"))
    expected_log_dir = str(resolve_spawn_log_dir(tmp_path, spawn_id))
    assert report["cwd"] == expected_log_dir, (
        f"Child CWD should be log_dir when CLAUDECODE is set, "
        f"got {report['cwd']!r}, expected {expected_log_dir!r}"
    )


@pytest.mark.asyncio
async def test_claude_harness_adds_add_dir_flag_when_claudecode_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When CWD isolation is active, --add-dir <project-root> should be in argv."""
    monkeypatch.setenv("CLAUDECODE", "1")

    spawn_id = SpawnId("r1")
    run = Spawn(spawn_id=spawn_id, prompt="test", model=ModelId("test-model"), status="queued")
    state_root = resolve_state_paths(tmp_path).root_dir
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    cwd_report = tmp_path / "cwd-report.json"
    script = tmp_path / "reporter.py"
    _write_cwd_reporter_script(script, cwd_report)

    adapter = ClaudeLikeAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    await execute_with_finalization(
        run,
        plan=_build_plan(run, adapter.id),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    report = json.loads(cwd_report.read_text(encoding="utf-8"))
    # The script receives the full command as argv. The runner appends
    # --add-dir <project-root> to the command when CWD isolation is active.
    # Since our adapter's build_command just returns the script command,
    # argv should contain --add-dir and the project root.
    assert "--add-dir" in report["argv"], "Command should include --add-dir flag"
    add_dir_idx = report["argv"].index("--add-dir")
    assert report["argv"][add_dir_idx + 1] == str(tmp_path), (
        f"--add-dir should point to project root {tmp_path}"
    )


@pytest.mark.asyncio
async def test_claude_harness_uses_project_cwd_when_claudecode_not_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When CLAUDECODE is NOT set, child CWD should be the project root (no isolation)."""
    monkeypatch.delenv("CLAUDECODE", raising=False)

    spawn_id = SpawnId("r1")
    run = Spawn(spawn_id=spawn_id, prompt="test", model=ModelId("test-model"), status="queued")
    state_root = resolve_state_paths(tmp_path).root_dir
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    cwd_report = tmp_path / "cwd-report.json"
    script = tmp_path / "reporter.py"
    _write_cwd_reporter_script(script, cwd_report)

    adapter = ClaudeLikeAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    await execute_with_finalization(
        run,
        plan=_build_plan(run, adapter.id),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    report = json.loads(cwd_report.read_text(encoding="utf-8"))
    assert report["cwd"] == str(tmp_path), (
        f"Child CWD should be project root when CLAUDECODE is not set, got {report['cwd']!r}"
    )
    assert "--add-dir" not in report["argv"], (
        "--add-dir should not be added when CWD isolation is inactive"
    )


@pytest.mark.asyncio
async def test_non_claude_harness_uses_project_cwd_even_when_claudecode_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-claude harnesses should never get CWD isolation, even inside Claude Code."""
    monkeypatch.setenv("CLAUDECODE", "1")

    spawn_id = SpawnId("r1")
    run = Spawn(spawn_id=spawn_id, prompt="test", model=ModelId("test-model"), status="queued")
    state_root = resolve_state_paths(tmp_path).root_dir
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")

    cwd_report = tmp_path / "cwd-report.json"
    script = tmp_path / "reporter.py"
    _write_cwd_reporter_script(script, cwd_report)

    adapter = NonClaudeAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    await execute_with_finalization(
        run,
        plan=_build_plan(run, adapter.id),
        repo_root=tmp_path,
        state_root=state_root,
        artifacts=artifacts,
        registry=registry,
        harness_id=adapter.id,
        cwd=tmp_path,
    )

    report = json.loads(cwd_report.read_text(encoding="utf-8"))
    assert report["cwd"] == str(tmp_path), (
        f"Non-claude harness CWD should always be project root, got {report['cwd']!r}"
    )
