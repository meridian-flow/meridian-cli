"""Command projection parity tests for subprocess harness adapters."""

from __future__ import annotations

import pytest

from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.harness.adapter import PermissionResolver, SpawnParams
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter


class _StaticPermissionResolver(PermissionResolver):
    def __init__(self, flags_by_harness: dict[HarnessId, tuple[str, ...]] | None = None) -> None:
        self._flags_by_harness = flags_by_harness or {}

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        return list(self._flags_by_harness.get(harness_id, ()))


def _spawn(**kwargs: object) -> SpawnParams:
    return SpawnParams(prompt="prompt text", **kwargs)


def test_claude_build_command_parity_cases() -> None:
    adapter = ClaudeAdapter()

    no_flags = _StaticPermissionResolver()
    with_flags = _StaticPermissionResolver({HarnessId.CLAUDE: ("--perm-claude",)})

    assert adapter.build_command(_spawn(), no_flags) == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            model=ModelId("claude-sonnet-4-6"),
            effort="medium",
            agent="coder",
            extra_args=("--extra", "1"),
            continue_harness_session_id=" session-1 ",
        ),
        with_flags,
    ) == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
        "--model",
        "claude-sonnet-4-6",
        "--effort",
        "medium",
        "--agent",
        "coder",
        "--perm-claude",
        "--extra",
        "1",
        "--resume",
        "session-1",
    ]
    assert adapter.build_command(
        _spawn(continue_harness_session_id="session-1", continue_fork=True),
        with_flags,
    ) == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
        "--perm-claude",
        "--resume",
        "session-1",
        "--fork-session",
    ]
    assert adapter.build_command(_spawn(continue_fork=True), no_flags) == [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            interactive=True,
            model=ModelId("claude-sonnet-4-6"),
            effort="xhigh",
            agent="coder",
            extra_args=("--extra", "1"),
            continue_harness_session_id="session-2",
            continue_fork=True,
            appended_system_prompt="system text",
            adhoc_agent_payload=' {"worker":{"prompt":"x"}} ',
        ),
        with_flags,
    ) == [
        "claude",
        "--model",
        "claude-sonnet-4-6",
        "--effort",
        "max",
        "--agent",
        "coder",
        "--perm-claude",
        "--extra",
        "1",
        "--append-system-prompt",
        "system text",
        "--agents",
        '{"worker":{"prompt":"x"}}',
        "--resume",
        "session-2",
        "--fork-session",
    ]


@pytest.mark.parametrize(
    ("effort", "expected_effort"),
    [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("xhigh", "max"),
        ("", None),
        (None, None),
    ],
)
def test_claude_build_command_effort_levels(
    effort: str | None, expected_effort: str | None
) -> None:
    command = ClaudeAdapter().build_command(
        _spawn(model=ModelId("claude-sonnet-4-6"), effort=effort),
        _StaticPermissionResolver(),
    )

    expected = [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
        "--model",
        "claude-sonnet-4-6",
    ]
    if expected_effort is not None:
        expected.extend(["--effort", expected_effort])
    assert command == expected


def test_codex_build_command_parity_cases() -> None:
    adapter = CodexAdapter()

    no_flags = _StaticPermissionResolver()
    with_flags = _StaticPermissionResolver({HarnessId.CODEX: ("--perm-codex",)})

    assert adapter.build_command(_spawn(), no_flags) == ["codex", "exec", "--json", "-"]
    assert adapter.build_command(
        _spawn(
            model=ModelId("gpt-5.3-codex"),
            effort="high",
            extra_args=("--extra", "1"),
            report_output_path="report.md",
            continue_harness_session_id="session-1",
        ),
        with_flags,
    ) == [
        "codex",
        "exec",
        "--json",
        "--model",
        "gpt-5.3-codex",
        "-c",
        'model_reasoning_effort="high"',
        "--perm-codex",
        "resume",
        "session-1",
        "--extra",
        "1",
        "-o",
        "report.md",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            model=ModelId("gpt-5.3-codex"),
            effort="high",
            continue_harness_session_id="session-1",
            continue_fork=True,
        ),
        with_flags,
    ) == [
        "codex",
        "exec",
        "--json",
        "--model",
        "gpt-5.3-codex",
        "-c",
        'model_reasoning_effort="high"',
        "--perm-codex",
        "resume",
        "session-1",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            interactive=True,
            model=ModelId("gpt-5.3-codex"),
            effort="xhigh",
            extra_args=("--extra", "1"),
        ),
        with_flags,
    ) == [
        "codex",
        "--model",
        "gpt-5.3-codex",
        "-c",
        'model_reasoning_effort="xhigh"',
        "--perm-codex",
        "--extra",
        "1",
        "prompt text\n\nDO NOT DO ANYTHING. WAIT FOR USER INPUT.",
    ]
    assert adapter.build_command(
        _spawn(
            interactive=True,
            model=ModelId("gpt-5.3-codex"),
            effort="xhigh",
            extra_args=("--extra", "1"),
            continue_harness_session_id="session-2",
            continue_fork=True,
            appended_system_prompt="ignored",
            adhoc_agent_payload=' {"ignored":true} ',
        ),
        with_flags,
    ) == [
        "codex",
        "--model",
        "gpt-5.3-codex",
        "-c",
        'model_reasoning_effort="xhigh"',
        "--perm-codex",
        "resume",
        "session-2",
        "--extra",
        "1",
        "prompt text",
    ]


@pytest.mark.parametrize(
    ("effort", "expected_effort"),
    [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("xhigh", "xhigh"),
        ("", None),
        (None, None),
    ],
)
def test_codex_build_command_effort_levels(
    effort: str | None, expected_effort: str | None
) -> None:
    command = CodexAdapter().build_command(
        _spawn(model=ModelId("gpt-5.3-codex"), effort=effort),
        _StaticPermissionResolver(),
    )

    expected = ["codex", "exec", "--json", "--model", "gpt-5.3-codex"]
    if expected_effort is not None:
        expected.extend(["-c", f'model_reasoning_effort="{expected_effort}"'])
    expected.append("-")
    assert command == expected


def test_opencode_build_command_parity_cases() -> None:
    adapter = OpenCodeAdapter()

    no_flags = _StaticPermissionResolver()
    with_flags = _StaticPermissionResolver({HarnessId.OPENCODE: ("--perm-opencode",)})

    assert adapter.build_command(_spawn(), no_flags) == ["opencode", "run", "-"]
    assert adapter.build_command(
        _spawn(
            model=ModelId("opencode-gpt-5.3-codex"),
            effort="medium",
            extra_args=("--extra", "1"),
            continue_harness_session_id="session-1",
        ),
        with_flags,
    ) == [
        "opencode",
        "run",
        "--model",
        "gpt-5.3-codex",
        "--variant",
        "medium",
        "--perm-opencode",
        "--extra",
        "1",
        "-",
        "--session",
        "session-1",
    ]
    assert adapter.build_command(
        _spawn(
            model=ModelId("opencode-gpt-5.3-codex"),
            effort="medium",
            continue_harness_session_id="session-1",
            continue_fork=True,
        ),
        with_flags,
    ) == [
        "opencode",
        "run",
        "--model",
        "gpt-5.3-codex",
        "--variant",
        "medium",
        "--perm-opencode",
        "-",
        "--session",
        "session-1",
        "--fork",
    ]
    assert adapter.build_command(_spawn(continue_fork=True), no_flags) == [
        "opencode",
        "run",
        "-",
    ]
    assert adapter.build_command(
        _spawn(
            interactive=True,
            model=ModelId("opencode-gpt-5.3-codex"),
            effort="high",
            extra_args=("--extra", "1"),
            continue_harness_session_id="session-2",
            continue_fork=True,
            appended_system_prompt="ignored",
            adhoc_agent_payload=' {"ignored":true} ',
        ),
        with_flags,
    ) == [
        "opencode",
        "--model",
        "gpt-5.3-codex",
        "--variant",
        "high",
        "--perm-opencode",
        "--extra",
        "1",
        "prompt text",
        "--session",
        "session-2",
        "--fork",
    ]


@pytest.mark.parametrize(
    ("effort", "expected_effort"),
    [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("xhigh", "xhigh"),
        ("", None),
        (None, None),
    ],
)
def test_opencode_build_command_effort_levels(
    effort: str | None, expected_effort: str | None
) -> None:
    command = OpenCodeAdapter().build_command(
        _spawn(model=ModelId("opencode-gpt-5.3-codex"), effort=effort),
        _StaticPermissionResolver(),
    )

    expected = ["opencode", "run", "--model", "gpt-5.3-codex"]
    if expected_effort is not None:
        expected.extend(["--variant", expected_effort])
    expected.append("-")
    assert command == expected
