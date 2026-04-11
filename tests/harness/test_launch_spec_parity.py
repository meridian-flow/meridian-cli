"""Command projection parity tests for subprocess harness adapters."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import BaseModel

from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import PermissionResolver, SpawnParams
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.claude_preflight import (
    CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
    expand_claude_passthrough_args,
)
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.connections.claude_ws import ClaudeConnection
from meridian.lib.harness.connections.codex_ws import CodexConnection
from meridian.lib.harness.connections.opencode_http import OpenCodeConnection
from meridian.lib.harness.launch_spec import ClaudeLaunchSpec, ResolvedLaunchSpec
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.projections.project_claude import (
    _check_projection_drift,
    project_claude_spec_to_cli_args,
)
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


def _values_for_flag(command: list[str], flag: str) -> list[str]:
    values: list[str] = []
    for index, arg in enumerate(command):
        if arg == flag:
            if index + 1 < len(command):
                values.append(command[index + 1])
            continue
        if arg.startswith(f"{flag}="):
            values.append(arg.split("=", 1)[1])
    return values


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


def test_claude_projection_drift_guard_happy_path() -> None:
    class _Spec(BaseModel):
        alpha: str = ""
        beta: str = ""

    _check_projection_drift(_Spec, frozenset({"alpha"}), frozenset({"beta"}))


def test_claude_projection_drift_guard_missing_field() -> None:
    class _Spec(BaseModel):
        alpha: str = ""
        beta: str = ""

    with pytest.raises(ImportError, match=r"missing=\['beta'\]"):
        _check_projection_drift(_Spec, frozenset({"alpha"}), frozenset())


def test_claude_projection_drift_guard_stale_field() -> None:
    class _Spec(BaseModel):
        alpha: str = ""

    with pytest.raises(ImportError, match=r"stale=\['beta'\]"):
        _check_projection_drift(_Spec, frozenset({"alpha"}), frozenset({"beta"}))


def test_claude_projection_import_fails_when_new_model_field_is_unaccounted() -> None:
    code = """
import sys
from pydantic import Field
import meridian.lib.harness.launch_spec as launch_spec

launch_spec.ClaudeLaunchSpec.model_fields = dict(launch_spec.ClaudeLaunchSpec.model_fields)
launch_spec.ClaudeLaunchSpec.model_fields["future_field"] = Field(default=None)
sys.modules.pop("meridian.lib.harness.projections.project_claude", None)
import meridian.lib.harness.projections.project_claude
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ImportError" in result.stderr
    assert "missing=['future_field']" in result.stderr


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
        "--resume",
        "session-1",
        "--extra",
        "1",
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
        "--append-system-prompt",
        "system text",
        "--agents",
        '{"worker":{"prompt":"x"}}',
        "--resume",
        "session-2",
        "--fork-session",
        "--extra",
        "1",
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


def test_claude_projection_dedupes_resolver_internal_allowed_tools() -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(
            (
                "--allowedTools",
                "Read,Edit",
                "--allowedTools",
                "Read,Bash",
            )
        ),
        extra_args=(
            CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
            "Read,Bash",
        ),
    )

    subprocess_args = project_claude_spec_to_cli_args(spec, base_command=("claude",))
    streaming_args = project_claude_spec_to_cli_args(
        spec,
        base_command=("claude", "--input-format", "stream-json"),
    )

    assert _values_for_flag(subprocess_args, "--allowedTools") == ["Read,Edit,Bash"]
    assert _values_for_flag(streaming_args, "--allowedTools") == ["Read,Edit,Bash"]
    assert CLAUDE_PARENT_ALLOWED_TOOLS_FLAG not in subprocess_args
    assert CLAUDE_PARENT_ALLOWED_TOOLS_FLAG not in streaming_args
    assert subprocess_args[1:] == streaming_args[3:]


def test_claude_projection_resolver_and_user_allowed_tools_are_both_forwarded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(("--allowedTools", "A,B")),
        extra_args=("--foo", "bar", "--allowedTools", "C,D"),
    )

    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_claude"
    ):
        command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert _values_for_flag(command, "--allowedTools") == ["A,B", "C,D"]
    assert command[-4:] == ["--foo", "bar", "--allowedTools", "C,D"]
    assert "known managed flag --allowedTools also present in extra_args" in caplog.text


def test_claude_projection_allows_empty_user_allowed_tools_tail_without_crashing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(("--allowedTools", "Bash")),
        extra_args=("--allowedTools", ""),
    )

    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_claude"
    ):
        command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert _values_for_flag(command, "--allowedTools") == ["Bash", ""]
    assert command[-2:] == ["--allowedTools", ""]
    assert "known managed flag --allowedTools also present in extra_args" in caplog.text


def test_claude_projection_append_system_prompt_collision_logs_and_last_wins(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(),
        appended_system_prompt="managed system text",
        extra_args=("--append-system-prompt", "user system text"),
    )

    with caplog.at_level(
        logging.WARNING, logger="meridian.lib.harness.projections.project_claude"
    ):
        command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert _values_for_flag(command, "--append-system-prompt") == [
        "managed system text",
        "user system text",
    ]
    assert "known managed flag --append-system-prompt also present in extra_args" in caplog.text


def test_claude_projection_keeps_user_tail_when_resolver_emits_no_flags() -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(),
        extra_args=("--append-system-prompt", "user tail", "--allowedTools", "C,D"),
    )

    command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert command == [
        "claude",
        "--append-system-prompt",
        "user tail",
        "--allowedTools",
        "C,D",
    ]


def test_claude_projection_dedupes_duplicate_csv_values_within_managed_allowed_tools() -> None:
    spec = ClaudeLaunchSpec(
        prompt="prompt text",
        permission_resolver=_StaticPermissionResolver(("--allowedTools", "Bash,Bash,Edit")),
        extra_args=(
            CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
            "Edit,Read,Read",
        ),
    )

    command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    assert _values_for_flag(command, "--allowedTools") == ["Bash,Edit,Read"]
    assert CLAUDE_PARENT_ALLOWED_TOOLS_FLAG not in command


def test_claude_projection_field_mapping_table_covers_every_field() -> None:
    spec = ClaudeLaunchSpec(
        model="claude-sonnet-4-6",
        effort="max",
        prompt="prompt text",
        continue_session_id="session-42",
        continue_fork=True,
        permission_resolver=_StaticPermissionResolver(
            (
                "--perm-claude",
                "--allowedTools",
                "Read",
                "--disallowedTools",
                "Bash",
            )
        ),
        extra_args=("--tail-a", "1", "--tail-b", "2"),
        interactive=False,
        mcp_tools=("mcp-one.json", "mcp-two.json"),
        agent_name="coder",
        agents_payload='{"worker":{"prompt":"x"}}',
        appended_system_prompt="system text",
    )
    command = project_claude_spec_to_cli_args(spec, base_command=("claude",))

    field_checks: dict[str, bool] = {
        "agent_name": _value_for_flag(command, "--agent") == "coder",
        "agents_payload": _value_for_flag(command, "--agents") == '{"worker":{"prompt":"x"}}',
        "appended_system_prompt": (
            _values_for_flag(command, "--append-system-prompt") == ["system text"]
        ),
        "continue_fork": "--fork-session" in command,
        "continue_session_id": _value_for_flag(command, "--resume") == "session-42",
        "effort": _value_for_flag(command, "--effort") == "max",
        "extra_args": command[-4:] == ["--tail-a", "1", "--tail-b", "2"],
        "interactive": command[:1] == ["claude"],  # delegated to base command policy
        "mcp_tools": _values_for_flag(command, "--mcp-config")
        == ["mcp-one.json", "mcp-two.json"],
        "model": _value_for_flag(command, "--model") == "claude-sonnet-4-6",
        "permission_resolver": (
            "--perm-claude" in command
            and _values_for_flag(command, "--allowedTools") == ["Read"]
            and _values_for_flag(command, "--disallowedTools") == ["Bash"]
        ),
        "prompt": "prompt text" not in command,  # prompt is delegated to stdin/runner path
    }

    assert set(field_checks) == set(ClaudeLaunchSpec.model_fields)
    assert all(field_checks.values()), field_checks


def test_claude_adapter_preflight_delegates_to_claude_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution_cwd = Path("/tmp/execution")
    child_cwd = Path("/tmp/child")
    passthrough_args = ("--allowedTools", "Read")
    expected = ("--add-dir", str(execution_cwd), *passthrough_args)
    seen: dict[str, object] = {}

    def _fake_expand(
        *,
        execution_cwd: Path,
        child_cwd: Path,
        passthrough_args: tuple[str, ...],
    ) -> tuple[str, ...]:
        seen["execution_cwd"] = execution_cwd
        seen["child_cwd"] = child_cwd
        seen["passthrough_args"] = passthrough_args
        return expected

    monkeypatch.setattr(
        "meridian.lib.harness.claude.expand_claude_passthrough_args",
        _fake_expand,
    )

    result = ClaudeAdapter().preflight(
        execution_cwd=execution_cwd,
        child_cwd=child_cwd,
        passthrough_args=passthrough_args,
    )

    assert seen == {
        "execution_cwd": execution_cwd,
        "child_cwd": child_cwd,
        "passthrough_args": passthrough_args,
    }
    assert result.expanded_passthrough_args == expected


def test_claude_adapter_preflight_expands_parent_permissions_with_helper(tmp_path: Path) -> None:
    execution_cwd = tmp_path / "parent"
    child_cwd = tmp_path / "child"
    execution_cwd.mkdir()
    child_cwd.mkdir()
    (execution_cwd / ".claude").mkdir()
    (execution_cwd / ".claude" / "settings.json").write_text(
        (
            '{"permissions":{"additionalDirectories":["/shared","/shared"],'
            '"allow":["Read","Edit","Read"]}}'
        ),
        encoding="utf-8",
    )

    result = ClaudeAdapter().preflight(
        execution_cwd=execution_cwd,
        child_cwd=child_cwd,
        passthrough_args=("--append-system-prompt", "tail"),
    )

    assert result.expanded_passthrough_args == expand_claude_passthrough_args(
        execution_cwd=execution_cwd,
        child_cwd=child_cwd,
        passthrough_args=("--append-system-prompt", "tail"),
    )
    assert result.expanded_passthrough_args == (
        "--append-system-prompt",
        "tail",
        "--add-dir",
        str(execution_cwd),
        "--add-dir",
        "/shared",
        CLAUDE_PARENT_ALLOWED_TOOLS_FLAG,
        "Read,Edit",
    )


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
    subprocess_base = (
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "-",
    )
    streaming_base = (
        "claude",
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
    )

    assert tuple(subprocess_command[: len(subprocess_base)]) == subprocess_base
    assert tuple(streaming_command[: len(streaming_base)]) == streaming_base
    assert subprocess_command[len(subprocess_base) :] == streaming_command[len(streaming_base) :]


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
