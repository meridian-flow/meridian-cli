from __future__ import annotations

from pathlib import Path

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.connections.claude_ws import ClaudeConnection
from meridian.lib.harness.launch_spec import ClaudeLaunchSpec, ResolvedLaunchSpec
from meridian.lib.harness.projections.project_claude import project_claude_spec_to_cli_args
from meridian.lib.safety.permissions import UnsafeNoOpPermissionResolver


class _TestableClaudeConnection(ClaudeConnection):
    def build_command_for_test(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> list[str]:
        return self._build_command(config, spec)


def _build_config(tmp_path: Path) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=SpawnId("p123"),
        harness_id=HarnessId.CLAUDE,
        prompt="hello",
        repo_root=tmp_path,
        env_overrides={},
    )


def test_claude_ws_build_command_includes_resume_and_fork_flags(tmp_path: Path) -> None:
    connection = _TestableClaudeConnection()
    config = _build_config(tmp_path)
    spec = ClaudeLaunchSpec(
        prompt="hello",
        model="claude-sonnet-4-6",
        continue_session_id="session-123",
        continue_fork=True,
        extra_args=("--add-dir", "/tmp/extra"),
        permission_resolver=UnsafeNoOpPermissionResolver(_suppress_warning=True),
    )

    command = connection.build_command_for_test(config, spec)
    expected = project_claude_spec_to_cli_args(
        spec,
        base_command=(
            "claude",
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
        ),
    )

    assert command == expected
