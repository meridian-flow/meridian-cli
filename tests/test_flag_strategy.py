"""Flag-strategy command builder tests for harness adapters."""

from __future__ import annotations

import dataclasses

from meridian.lib.harness.adapter import PermissionResolver, SpawnParams
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.types import HarnessId, ModelId


class StubPermissionResolver(PermissionResolver):
    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        return ["--perm", str(harness_id)]


def _sample_run(*, model: str, extra_args: tuple[str, ...] = ()) -> SpawnParams:
    return SpawnParams(
        prompt="Implement feature X.",
        model=ModelId(model),
        skills=("reviewing",),
        agent="reviewer",
        extra_args=extra_args,
    )


def test_every_run_params_field_is_mapped_for_each_adapter() -> None:
    skip = {"prompt", "extra_args", "repo_root", "mcp_tools", "adhoc_agent_json", "interactive", "report_output_path"}
    required = {field.name for field in dataclasses.fields(SpawnParams)} - skip
    adapter_classes = (ClaudeAdapter, CodexAdapter, OpenCodeAdapter)

    for adapter_class in adapter_classes:
        mapped = set(adapter_class.STRATEGIES)
        missing = required - mapped
        assert not missing, f"{adapter_class.__name__} missing strategy for {sorted(missing)}"


def test_claude_build_command_passes_agent_natively() -> None:
    command = ClaudeAdapter().build_command(
        _sample_run(model="claude-opus-4-6"),
        StubPermissionResolver(),
    )

    assert command == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
        "--model",
        "claude-opus-4-6",
        "--agent",
        "reviewer",
        "--perm",
        "claude",
    ]
    assert "--skills" not in command


def test_codex_build_command_drops_agent_and_uses_stdin_prompt_marker() -> None:
    command = CodexAdapter().build_command(
        _sample_run(model="gpt-5.3-codex"),
        StubPermissionResolver(),
    )

    assert command == [
        "codex",
        "exec",
        "--json",
        "--model",
        "gpt-5.3-codex",
        "--perm",
        "codex",
        "-",
    ]
    assert "--agent" not in command
    assert "--skills" not in command


def test_codex_build_command_includes_json_without_extra_args() -> None:
    command = CodexAdapter().build_command(
        SpawnParams(
            prompt="Implement feature X.",
            model=ModelId("gpt-5.3-codex"),
        ),
        StubPermissionResolver(),
    )

    assert command[:3] == ["codex", "exec", "--json"]
    assert command[-1] == "-"
    assert command.count("--json") == 1


def test_claude_build_command_resume_and_fork() -> None:
    command = ClaudeAdapter().build_command(
        SpawnParams(
            prompt="Follow up.",
            model=ModelId("claude-opus-4-6"),
            continue_harness_session_id="session-123",
            continue_fork=True,
        ),
        StubPermissionResolver(),
    )

    assert command[:5] == ["claude", "-p", "--output-format", "stream-json", "--verbose"]
    assert "--resume" in command
    assert "session-123" in command
    assert "--fork-session" in command


def test_claude_build_command_interactive_omits_dash_p_and_uses_append_prompt() -> None:
    command = ClaudeAdapter().build_command(
        SpawnParams(
            prompt="space prompt",
            model=ModelId("claude-opus-4-6"),
            interactive=True,
            appended_system_prompt="space prompt",
        ),
        StubPermissionResolver(),
    )

    assert command[0] == "claude"
    assert "-p" not in command
    assert "--append-system-prompt" in command
    assert command[command.index("--append-system-prompt") + 1] == "space prompt"


def test_claude_filter_launch_content_suppresses_skill_injection() -> None:
    policy = ClaudeAdapter().filter_launch_content(
        prompt="space prompt",
        skill_injection="# Skill: orchestrate\n\nSkill content here",
        is_resume=False,
        harness_session_id="",
    )

    assert policy.prompt == "space prompt"
    assert policy.skill_injection == ""


def test_claude_filter_launch_content_resume_suppresses_all() -> None:
    policy = ClaudeAdapter().filter_launch_content(
        prompt="space prompt",
        skill_injection="skill content",
        is_resume=True,
        harness_session_id="session-123",
    )

    assert policy.prompt == ""
    assert policy.skill_injection is None


def test_codex_build_command_uses_resume_subcommand_when_session_available() -> None:
    command = CodexAdapter().build_command(
        SpawnParams(
            prompt="Retry this task.",
            model=ModelId("gpt-5.3-codex"),
            continue_harness_session_id="session-456",
            continue_fork=True,
        ),
        StubPermissionResolver(),
    )

    assert command[:5] == ["codex", "exec", "--json", "resume", "session-456"]
    assert "--model" in command
    assert "--fork" not in command
    assert command[-1] == "-"


def test_codex_build_command_interactive_resume_uses_resume_subcommand() -> None:
    command = CodexAdapter().build_command(
        SpawnParams(
            prompt="space prompt",
            model=ModelId("gpt-5.3-codex"),
            interactive=True,
            continue_harness_session_id="session-456",
        ),
        StubPermissionResolver(),
    )

    assert command[:3] == ["codex", "resume", "session-456"]
    assert "--model" in command


def test_codex_build_command_includes_output_flag_when_report_path_set() -> None:
    command = CodexAdapter().build_command(
        SpawnParams(
            prompt="Task.",
            model=ModelId("gpt-5.3-codex"),
            report_output_path="/tmp/spawns/r1/report.md",
        ),
        StubPermissionResolver(),
    )

    assert "-o" in command
    assert "/tmp/spawns/r1/report.md" in command
    idx = command.index("-o")
    assert command[idx + 1] == "/tmp/spawns/r1/report.md"


def test_codex_build_command_omits_output_flag_when_no_report_path() -> None:
    command = CodexAdapter().build_command(
        _sample_run(model="gpt-5.3-codex"),
        StubPermissionResolver(),
    )

    assert "-o" not in command


def test_codex_build_command_omits_output_flag_for_interactive() -> None:
    command = CodexAdapter().build_command(
        SpawnParams(
            prompt="space prompt",
            model=ModelId("gpt-5.3-codex"),
            interactive=True,
            report_output_path="/tmp/spawns/r1/report.md",
        ),
        StubPermissionResolver(),
    )

    assert "-o" not in command


def test_opencode_build_command_strips_model_prefix_and_uses_positional_prompt() -> None:
    command = OpenCodeAdapter().build_command(
        _sample_run(model="opencode-gpt-5.3-codex"),
        StubPermissionResolver(),
    )

    assert command == [
        "opencode",
        "run",
        "--model",
        "gpt-5.3-codex",
        "--perm",
        "opencode",
        "-",
    ]
    assert "--agent" not in command
    assert "--skills" not in command


def test_opencode_build_command_interactive_uses_primary_base_command() -> None:
    command = OpenCodeAdapter().build_command(
        SpawnParams(
            prompt="space prompt",
            model=ModelId("opencode-gpt-5.3-codex"),
            interactive=True,
        ),
        StubPermissionResolver(),
    )

    assert command[0] == "opencode"
    assert "run" not in command[:2]
    assert "--model" in command
    assert command[-1] == "space prompt"


def test_opencode_build_command_resume_and_fork() -> None:
    command = OpenCodeAdapter().build_command(
        SpawnParams(
            prompt="Retry this task.",
            model=ModelId("opencode-gpt-5.3-codex"),
            continue_harness_session_id="session-789",
            continue_fork=True,
        ),
        StubPermissionResolver(),
    )

    assert "--session" in command
    assert "session-789" in command
    assert "--fork" in command
