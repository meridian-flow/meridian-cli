from pathlib import Path

from meridian.lib.ops.spawn import execute as spawn_execute
from meridian.lib.safety.permissions import PermissionConfig


def test_background_worker_command_preserves_adhoc_agent_json(tmp_path: Path) -> None:
    builder = getattr(spawn_execute, "_build_background_worker_command")
    command = builder(
        spawn_id="p1",
        repo_root=tmp_path,
        timeout=None,
        skills=(),
        agent_name="reviewer",
        mcp_tools=(),
        permission_config=PermissionConfig(),
        allowed_tools=(),
        passthrough_args=(),
        continue_harness_session_id=None,
        continue_fork=False,
        session_agent="reviewer",
        session_agent_path="",
        session_skill_paths=(),
        adhoc_agent_json='{"reviewer":{"description":"desc","prompt":"body"}}',
        appended_system_prompt=None,
    )

    assert "--adhoc-agent-json" in command
    index = command.index("--adhoc-agent-json")
    assert command[index + 1] == '{"reviewer":{"description":"desc","prompt":"body"}}'
