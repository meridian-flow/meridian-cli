from pathlib import Path

from meridian.lib.ops.spawn import execute as spawn_execute
from meridian.lib.safety.permissions import PermissionConfig


def test_background_worker_command_preserves_adhoc_agent_payload(tmp_path: Path) -> None:
    builder = spawn_execute._build_background_worker_command
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
        adhoc_agent_payload='{"reviewer":{"description":"desc","prompt":"body"}}',
        appended_system_prompt=None,
    )

    assert "--adhoc-agent-payload" in command
    index = command.index("--adhoc-agent-payload")
    assert command[index + 1] == '{"reviewer":{"description":"desc","prompt":"body"}}'


def test_background_worker_command_serializes_skills_as_csv(tmp_path: Path) -> None:
    builder = spawn_execute._build_background_worker_command
    command = builder(
        spawn_id="p1",
        repo_root=tmp_path,
        timeout=None,
        skills=("reviewing", "mermaid"),
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
        adhoc_agent_payload="",
        appended_system_prompt=None,
    )

    assert "--skills" in command
    index = command.index("--skills")
    assert command[index + 1] == "reviewing,mermaid"


def test_parse_csv_skills_rejects_empty_names() -> None:
    parser = spawn_execute._parse_csv_skills

    try:
        parser("reviewing,,mermaid")
    except ValueError as exc:
        assert "--skills" in str(exc)
    else:
        raise AssertionError("Expected invalid CSV skills to raise ValueError")
