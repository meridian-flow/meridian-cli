import asyncio
import os
import signal
import sys
import textwrap
from pathlib import Path

import pytest

from meridian.lib.core.domain import Spawn, TokenUsage
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.harness.adapter import ArtifactStore as HarnessArtifactStore
from meridian.lib.harness.adapter import (
    BaseHarnessAdapter,
    HarnessCapabilities,
    McpConfig,
    PermissionResolver,
    SpawnParams,
    StreamEvent,
)
from meridian.lib.harness.common import (
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.state.space_store import create_space
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.core.types import HarnessId, ModelId, SpawnId, SpaceId


class ReportScriptHarnessAdapter(BaseHarnessAdapter):
    def __init__(self, *, command: tuple[str, ...]) -> None:
        self._command = command

    @property
    def id(self) -> HarnessId:
        return HarnessId("report-script")

    @property
    def capabilities(self) -> HarnessCapabilities:
        return HarnessCapabilities()

    def build_command(self, run: SpawnParams, perms: PermissionResolver) -> list[str]:
        return [
            *self._command,
            run.report_output_path or "",
            *perms.resolve_flags(self.id),
            *run.extra_args,
        ]

    def mcp_config(self, run: SpawnParams) -> McpConfig | None:
        _ = run
        return None

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
    space = create_space(repo_root, name="pipe-drain")
    run = Spawn(
        spawn_id=SpawnId("r1"),
        prompt=prompt,
        model=ModelId("gpt-5.3-codex"),
        status="queued",
        space_id=SpaceId(space.id),
    )
    return run, resolve_space_dir(repo_root, space.id)


def _write_script(path: Path, source: str) -> None:
    path.write_text(textwrap.dedent(source), encoding="utf-8")


@pytest.mark.asyncio
async def test_execute_finalizes_when_descendant_keeps_stdio_open(tmp_path: Path) -> None:
    run, space_dir = _create_run(tmp_path, prompt="drain")
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
        print(json.dumps({{"type": "response.completed", "tokens": {{"input_tokens": 3, "output_tokens": 5}}}}), flush=True)
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
                repo_root=tmp_path,
                space_dir=space_dir,
                artifacts=artifacts,
                registry=registry,
                harness_id=adapter.id,
                cwd=tmp_path,
                timeout_seconds=5.0,
                kill_grace_seconds=0.05,
                max_retries=0,
            ),
            timeout=10.0,
        )
    finally:
        if sleeper_pid_path.exists():
            sleeper_pid = int(sleeper_pid_path.read_text(encoding="utf-8").strip())
            try:
                os.kill(sleeper_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    assert exit_code == 0
    row = spawn_store.get_spawn(space_dir, run.spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.input_tokens == 3
    assert row.output_tokens == 5
