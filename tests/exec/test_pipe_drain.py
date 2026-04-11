import asyncio
import os
import signal
import sys
import textwrap
from contextlib import suppress
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
    resolve_permission_flags,
)
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.launch_types import ResolvedLaunchSpec
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.ops.spawn.plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_state_paths


class ReportScriptHarnessAdapter(BaseSubprocessHarness):
    id: ClassVar[HarnessId] = HarnessId.CODEX
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
        return [
            *self._command,
            run.report_output_path or "",
            *resolve_permission_flags(perms, self.id),
            *run.extra_args,
        ]

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


def _create_run(repo_root: Path, *, prompt: str) -> tuple[Spawn, Path]:
    run = Spawn(
        spawn_id=SpawnId("r1"),
        prompt=prompt,
        model=ModelId("gpt-5.3-codex"),
        status="queued",
    )
    return run, resolve_state_paths(repo_root).root_dir


def _write_script(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")


def _build_plan(
    run: Spawn,
    harness_id: HarnessId,
    *,
    timeout_seconds: float | None,
    kill_grace_seconds: float,
    max_retries: int,
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
            retry_backoff_secs=0.0,
            permission_config=PermissionConfig(),
            permission_resolver=TieredPermissionResolver(config=PermissionConfig()),
            allowed_tools=(),
        ),
        cli_command=(),
    )


@pytest.mark.asyncio
async def test_execute_finalizes_when_descendant_keeps_stdio_open(tmp_path: Path) -> None:
    run, state_root = _create_run(tmp_path, prompt="drain")
    artifacts = LocalStore(root_dir=tmp_path / ".artifacts")
    sleeper_pid_path = tmp_path / "sleeper.pid"
    script = tmp_path / "inherits_stdio.py"
    _write_script(
        script,
        f"""
        import json
        import os
        import subprocess
        import sys
        from pathlib import Path

        report_path = Path(sys.argv[1])
        sleeper_pid_path = Path({sleeper_pid_path.as_posix()!r})
        sleeper = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        sleeper_pid_path.write_text(str(sleeper.pid), encoding="utf-8")
        report_path.write_text("# Complete\\n", encoding="utf-8")
        print(
            json.dumps(
                {{
                    "type": "response.completed",
                    "tokens": {{"input_tokens": 3, "output_tokens": 5}},
                }}
            ),
            flush=True,
        )
        os._exit(0)
        """,
    )

    adapter = ReportScriptHarnessAdapter(command=(sys.executable, str(script)))
    registry = HarnessRegistry()
    registry.register(adapter)

    try:
        exit_code = await asyncio.wait_for(
            execute_with_finalization(
                run,
                plan=_build_plan(
                    run,
                    adapter.id,
                    timeout_seconds=5.0,
                    kill_grace_seconds=0.05,
                    max_retries=0,
                ),
                repo_root=tmp_path,
                state_root=state_root,
                artifacts=artifacts,
                registry=registry,
                harness_id=adapter.id,
                cwd=tmp_path,
            ),
            timeout=10.0,
        )
    finally:
        if sleeper_pid_path.exists():
            sleeper_pid = int(sleeper_pid_path.read_text(encoding="utf-8").strip())
            with suppress(ProcessLookupError):
                os.kill(sleeper_pid, signal.SIGKILL)

    assert exit_code == 0
    row = spawn_store.get_spawn(state_root, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.input_tokens == 3
    assert row.output_tokens == 5
