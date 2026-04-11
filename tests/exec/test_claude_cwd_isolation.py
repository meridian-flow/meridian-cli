"""Test CWD isolation for claude harness when running inside Claude Code.

When CLAUDECODE is set in the parent environment and the harness is claude,
the child subprocess CWD should be the spawn's log directory (not the project
root) to prevent the child from deleting the parent's task output file.
"""

import json
import sys
import textwrap
from pathlib import Path
from typing import ClassVar

import pytest

from meridian.lib.core.domain import Spawn, TokenUsage
from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import ArtifactStore as HarnessArtifactStore
from meridian.lib.harness.adapter import (
    BaseSubprocessHarness,
    HarnessCapabilities,
    PermissionResolver,
    PreflightResult,
    SpawnParams,
)
from meridian.lib.harness.claude_preflight import expand_claude_passthrough_args
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.launch_types import ResolvedLaunchSpec
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.ops.spawn.plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_spawn_log_dir, resolve_state_paths


class ClaudeLikeAdapter(BaseSubprocessHarness):
    """Adapter that reports id='claude' to trigger CWD isolation."""

    id: ClassVar[HarnessId] = HarnessId.CLAUDE
    consumed_fields: ClassVar[frozenset[str]] = frozenset()
    explicitly_ignored_fields: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, *, command: tuple[str, ...]) -> None:
        self._command = command

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def resolve_launch_spec(
        self,
        run: SpawnParams,
        perms: PermissionResolver,
    ) -> ResolvedLaunchSpec:
        return ResolvedLaunchSpec(
            prompt=run.prompt or "",
            permission_resolver=perms,
        )

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        _ = perms
        return [*self._command, *run.extra_args]

    def preflight(
        self,
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> PreflightResult:
        return PreflightResult.build(
            expanded_passthrough_args=expand_claude_passthrough_args(
                execution_cwd=execution_cwd,
                child_cwd=child_cwd,
                passthrough_args=passthrough_args,
            )
        )

    def env_overrides(self, config: PermissionConfig) -> dict[str, str]:
        _ = config
        return {}

    def blocked_child_env_vars(self) -> frozenset[str]:
        return frozenset({"CLAUDECODE"})

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


async def _run_and_read_report(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    claudecode_enabled: bool,
) -> dict[str, object]:
    if claudecode_enabled:
        monkeypatch.setenv("CLAUDECODE", "1")
    else:
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
    return json.loads(cwd_report.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_claude_harness_flips_to_log_dir_with_add_dir_under_claudecode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = await _run_and_read_report(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claudecode_enabled=True,
    )

    expected_log_dir = str(resolve_spawn_log_dir(tmp_path, SpawnId("r1")))
    assert report["cwd"] == expected_log_dir
    assert "--add-dir" in report["argv"]
    add_dir_idx = report["argv"].index("--add-dir")
    assert report["argv"][add_dir_idx + 1] == str(tmp_path)


@pytest.mark.asyncio
async def test_claude_harness_keeps_project_cwd_without_claudecode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = await _run_and_read_report(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        claudecode_enabled=False,
    )

    assert report["cwd"] == str(tmp_path)
    assert "--add-dir" not in report["argv"]
