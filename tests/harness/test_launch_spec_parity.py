"""Command projection parity tests for subprocess harness adapters."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import PermissionResolver, SpawnParams
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.connections.claude_ws import ClaudeConnection
from meridian.lib.harness.connections.codex_ws import CodexConnection
from meridian.lib.harness.connections.opencode_http import OpenCodeConnection
from meridian.lib.harness.launch_spec import ResolvedLaunchSpec
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.safety.permissions import PermissionConfig


class _StaticPermissionResolver(PermissionResolver):
    def __init__(
        self,
        flags: tuple[str, ...] = (),
        *,
        config: PermissionConfig | None = None,
    ) -> None:
        self._flags = flags
        self._config = config or PermissionConfig()

    @property
    def config(self) -> PermissionConfig:
        return self._config

    def resolve_flags(self) -> tuple[str, ...]:
        return self._flags


def _spawn(**kwargs: object) -> SpawnParams:
    return SpawnParams(prompt="prompt text", **kwargs)


def _value_for_flag(command: list[str], flag: str) -> str | None:
    for index, arg in enumerate(command):
        if arg == flag:
            if index + 1 < len(command):
                return command[index + 1]
            return None
        if arg.startswith(f"{flag}="):
            return arg.split("=", 1)[1]
    return None


class _TestableClaudeConnection(ClaudeConnection):
    def build_streaming_command(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> list[str]:
        return self._build_command(config, spec)


class _TestableCodexConnection(CodexConnection):
    def build_bootstrap_request(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> tuple[str, dict[str, object]]:
        self._config = config
        return self._thread_bootstrap_request(spec)


class _TestableOpenCodeConnection(OpenCodeConnection):
    def __init__(self, responses: list[tuple[int, object | None, str]]) -> None:
        super().__init__()
        self.requests: list[tuple[str, dict[str, object]]] = []
        self._responses = iter(responses)

    async def _post_json(  # type: ignore[override]
        self,
        path: str,
        payload: dict[str, object],
        *,
        skip_body_on_statuses: frozenset[int] | None = None,
        tolerate_incomplete_body: bool = False,
    ) -> tuple[int, object | None, str]:
        _ = skip_body_on_statuses, tolerate_incomplete_body
        self.requests.append((path, dict(payload)))
        try:
            return next(self._responses)
        except StopIteration as exc:
            raise AssertionError("Unexpected _post_json call in test") from exc


def _connection_config(harness_id: HarnessId, repo_root: Path) -> ConnectionConfig:
    return ConnectionConfig(
        spawn_id=SpawnId("p-parity"),
        harness_id=harness_id,
        prompt="prompt text",
        repo_root=repo_root,
        env_overrides={},
    )


def _reasoning_effort_from_codex_command(command: list[str]) -> str | None:
    for index, arg in enumerate(command):
        if arg != "-c":
            continue
        if index + 1 >= len(command):
            continue
        setting = command[index + 1]
        if setting.startswith('model_reasoning_effort="') and setting.endswith('"'):
            return setting.removeprefix('model_reasoning_effort="').removesuffix('"')
    return None


def test_claude_build_command_parity_cases() -> None:
    adapter = ClaudeAdapter()

    no_flags = _StaticPermissionResolver()
    with_flags = _StaticPermissionResolver(("--perm-claude",))

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
    with_flags = _StaticPermissionResolver(("--perm-codex",))

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
    with_flags = _StaticPermissionResolver(("--perm-opencode",))

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


def test_claude_cross_transport_parity_on_semantic_fields(tmp_path: Path) -> None:
    adapter = ClaudeAdapter()
    perms = _StaticPermissionResolver(("--perm-claude",))
    run = _spawn(
        model=ModelId("claude-sonnet-4-6"),
        effort="xhigh",
        agent="coder",
        extra_args=("--extra", "1"),
        continue_harness_session_id="session-1",
        continue_fork=True,
        appended_system_prompt="system text",
        adhoc_agent_payload='{"worker":{"prompt":"x"}}',
    )
    spec = adapter.resolve_launch_spec(run, perms)

    subprocess_command = adapter.build_command(run, perms)
    streaming_command = _TestableClaudeConnection().build_streaming_command(
        _connection_config(HarnessId.CLAUDE, tmp_path),
        spec,
    )

    assert _value_for_flag(subprocess_command, "--model") == spec.model
    assert _value_for_flag(streaming_command, "--model") == spec.model
    assert _value_for_flag(subprocess_command, "--effort") == spec.effort
    assert _value_for_flag(streaming_command, "--effort") == spec.effort
    assert _value_for_flag(subprocess_command, "--agent") == spec.agent_name
    assert _value_for_flag(streaming_command, "--agent") == spec.agent_name
    assert (
        _value_for_flag(subprocess_command, "--append-system-prompt")
        == spec.appended_system_prompt
    )
    assert (
        _value_for_flag(streaming_command, "--append-system-prompt")
        == spec.appended_system_prompt
    )
    assert _value_for_flag(subprocess_command, "--agents") == spec.agents_payload
    assert _value_for_flag(streaming_command, "--agents") == spec.agents_payload
    assert _value_for_flag(subprocess_command, "--resume") == spec.continue_session_id
    assert _value_for_flag(streaming_command, "--resume") == spec.continue_session_id
    assert "--fork-session" in subprocess_command
    assert "--fork-session" in streaming_command
    assert "--perm-claude" in subprocess_command
    assert "--perm-claude" in streaming_command
    assert "--extra" in subprocess_command and "1" in subprocess_command
    assert "--extra" in streaming_command and "1" in streaming_command


def test_codex_cross_transport_parity_on_semantic_fields(tmp_path: Path) -> None:
    adapter = CodexAdapter()
    perms = _StaticPermissionResolver(("--perm-codex",))
    run = _spawn(
        model=ModelId("gpt-5.3-codex"),
        effort="high",
        continue_harness_session_id="thread-123",
    )
    spec = adapter.resolve_launch_spec(run, perms)
    subprocess_command = adapter.build_command(run, perms)
    method, payload = _TestableCodexConnection().build_bootstrap_request(
        _connection_config(HarnessId.CODEX, tmp_path),
        spec,
    )

    assert method == "thread/resume"
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["threadId"] == "thread-123"
    assert payload["config"] == {"model_reasoning_effort": "high"}
    assert _value_for_flag(subprocess_command, "--model") == "gpt-5.3-codex"
    assert _reasoning_effort_from_codex_command(subprocess_command) == "high"
    assert "resume" in subprocess_command
    assert "thread-123" in subprocess_command


@pytest.mark.asyncio
async def test_opencode_cross_transport_parity_with_known_streaming_asymmetries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = OpenCodeAdapter()
    perms = _StaticPermissionResolver(("--perm-opencode",))
    run = _spawn(
        model=ModelId("opencode-gpt-5.3-codex"),
        effort="medium",
        continue_harness_session_id="sess-1",
        continue_fork=True,
    )
    spec = adapter.resolve_launch_spec(run, perms)
    subprocess_command = adapter.build_command(run, perms)

    connection = _TestableOpenCodeConnection(responses=[(200, {"session_id": "sess-1"}, "")])
    with caplog.at_level(logging.DEBUG, logger="meridian.lib.harness.connections.opencode_http"):
        await connection._create_session(spec)

    assert connection.requests
    payload = connection.requests[0][1]
    assert _value_for_flag(subprocess_command, "--model") == "gpt-5.3-codex"
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["modelID"] == "gpt-5.3-codex"
    assert "--session" in subprocess_command and "sess-1" in subprocess_command
    assert payload["session_id"] == "sess-1"
    assert payload["continue_session_id"] == "sess-1"

    # Known asymmetry: streaming OpenCode currently has no effort/fork transport fields.
    assert _value_for_flag(subprocess_command, "--variant") == "medium"
    assert "--fork" in subprocess_command
    assert "does not support effort override" in caplog.text
    assert "does not support session fork" in caplog.text
