"""Resolved launch spec tests for harness adapters."""

import logging

import pytest
from pydantic import ValidationError

from meridian.lib.core.types import ModelId
from meridian.lib.harness.adapter import RunPromptPolicy, SpawnParams, SubprocessHarness
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.launch_spec import (
    ClaudeLaunchSpec,
    CodexLaunchSpec,
    OpenCodeLaunchSpec,
    ResolvedLaunchSpec,
)
from meridian.lib.harness.opencode import OpenCodeAdapter
from meridian.lib.harness.projections.project_opencode_streaming import (
    _ACCOUNTED_FIELDS as _OPENCODE_STREAMING_ACCOUNTED_FIELDS,
)
from meridian.lib.harness.projections.project_opencode_subprocess import (
    _PROJECTED_FIELDS as _OPENCODE_SUBPROCESS_PROJECTED_FIELDS,
)
from meridian.lib.harness.projections.project_opencode_subprocess import (
    HarnessCapabilityMismatch,
    project_opencode_spec_to_cli_args,
)
from meridian.lib.safety.permissions import PermissionConfig, TieredPermissionResolver


def _resolver(*, sandbox: str = "default", approval: str = "default") -> TieredPermissionResolver:
    return TieredPermissionResolver(config=PermissionConfig(sandbox=sandbox, approval=approval))


def test_claude_resolve_launch_spec_normalizes_effort_and_maps_fields() -> None:
    resolver = _resolver()
    run = SpawnParams(
        prompt="test prompt",
        model=ModelId("claude-sonnet-4-6"),
        effort="xhigh",
        agent="coder",
        adhoc_agent_payload='{"agent":"payload"}   ',
        continue_harness_session_id="  claude-session  ",
        continue_fork=True,
        appended_system_prompt="system-prompt",
    )

    spec = ClaudeAdapter().resolve_launch_spec(run, resolver)

    assert spec.model == "claude-sonnet-4-6"
    assert spec.effort == "max"
    assert spec.prompt == "test prompt"
    assert spec.continue_session_id == "claude-session"
    assert spec.continue_fork is True
    assert spec.appended_system_prompt == "system-prompt"
    assert spec.agents_payload == '{"agent":"payload"}'
    assert spec.agent_name == "coder"
    assert spec.permission_resolver.config == resolver.config
    assert spec.permission_resolver is resolver


def test_codex_resolve_launch_spec_uses_permission_config_values() -> None:
    resolver = _resolver(sandbox="workspace-write", approval="confirm")
    run = SpawnParams(
        prompt="test prompt",
        model=ModelId("gpt-5.3-codex"),
        effort="xhigh",
    )

    spec = CodexAdapter().resolve_launch_spec(run, resolver)

    assert spec.model == "gpt-5.3-codex"
    assert spec.effort == "xhigh"
    assert spec.permission_resolver.config.approval == "confirm"
    assert spec.permission_resolver.config.sandbox == "workspace-write"


def test_codex_launch_spec_keeps_report_output_path_as_codex_only_field() -> None:
    codex_fields = set(CodexLaunchSpec.model_fields)

    assert "report_output_path" in codex_fields
    assert "permission_resolver" in codex_fields
    assert "sandbox_mode" not in codex_fields
    assert "approval_mode" not in codex_fields


def test_codex_adapter_accounts_for_every_spawn_param_field() -> None:
    adapter = CodexAdapter()

    assert adapter.handled_fields == frozenset(SpawnParams.model_fields)
    assert adapter.consumed_fields | adapter.explicitly_ignored_fields == adapter.handled_fields
    assert adapter.consumed_fields & adapter.explicitly_ignored_fields == frozenset()


def test_opencode_resolve_launch_spec_strips_prefix_and_maps_fields() -> None:
    resolver = _resolver()
    run = SpawnParams(
        prompt="test prompt",
        model=ModelId("opencode-gpt-5.3-codex"),
        effort="high",
        agent="worker",
        skills=("skill-a", "skill-b"),
    )

    spec = OpenCodeAdapter().resolve_launch_spec(run, resolver)

    assert spec.model == "gpt-5.3-codex"
    assert spec.effort == "high"
    assert spec.agent_name == "worker"
    assert spec.skills == ()
    assert spec.permission_resolver.config == resolver.config


def test_opencode_resolve_launch_spec_normalizes_provider_model_once() -> None:
    resolver = _resolver()
    run_prefixed = SpawnParams(
        prompt="test prompt",
        model=ModelId("opencode-openrouter/qwen/qwen3-coder:free"),
    )
    run_unprefixed = SpawnParams(
        prompt="test prompt",
        model=ModelId("openrouter/qwen/qwen3-coder:free"),
    )

    prefixed_spec = OpenCodeAdapter().resolve_launch_spec(run_prefixed, resolver)
    unprefixed_spec = OpenCodeAdapter().resolve_launch_spec(run_unprefixed, resolver)

    assert prefixed_spec.model == "openrouter/qwen/qwen3-coder:free"
    assert unprefixed_spec.model == "openrouter/qwen/qwen3-coder:free"


@pytest.mark.parametrize(
    ("raw_model", "expected_model"),
    (
        (ModelId("gpt-5.3-codex"), "gpt-5.3-codex"),
        (ModelId("anthropic/claude-sonnet-4-5"), "anthropic/claude-sonnet-4-5"),
        (ModelId("opencode-anthropic/claude-sonnet-4-5"), "anthropic/claude-sonnet-4-5"),
        (
            ModelId("opencode-openrouter/anthropic/claude-sonnet-4-5"),
            "openrouter/anthropic/claude-sonnet-4-5",
        ),
        (
            ModelId("opencode-opencode-anthropic/claude-sonnet-4-5"),
            "opencode-anthropic/claude-sonnet-4-5",
        ),
        (ModelId(""), None),
        (None, None),
    ),
)
def test_opencode_resolve_launch_spec_handles_model_shapes_exactly_once(
    raw_model: ModelId | None,
    expected_model: str | None,
) -> None:
    resolver = _resolver()
    run = SpawnParams(prompt="test prompt", model=raw_model)

    spec = OpenCodeAdapter().resolve_launch_spec(run, resolver)

    assert spec.model == expected_model


def test_opencode_resolve_launch_spec_preserves_skills_when_policy_disables_inline() -> None:
    class _NoInlineSkillsOpenCodeAdapter(OpenCodeAdapter):
        def run_prompt_policy(self) -> RunPromptPolicy:
            return RunPromptPolicy(include_skills=False)

    resolver = _resolver()
    run = SpawnParams(
        prompt="test prompt",
        model=ModelId("opencode-gpt-5.3-codex"),
        skills=("skill-a", "skill-b"),
    )

    spec = _NoInlineSkillsOpenCodeAdapter().resolve_launch_spec(run, resolver)

    assert spec.skills == ("skill-a", "skill-b")


def test_opencode_subprocess_rejects_mcp_tools() -> None:
    resolver = _resolver()
    run = SpawnParams(
        prompt="test prompt",
        model=ModelId("opencode-gpt-5.3-codex"),
        mcp_tools=("tool-a=echo a",),
    )

    with pytest.raises(HarnessCapabilityMismatch, match="does not support per-spawn mcp_tools"):
        OpenCodeAdapter().build_command(run, resolver)


def test_opencode_projection_field_accounting_covers_spawn_and_launch_spec_fields() -> None:
    adapter = OpenCodeAdapter()
    launch_spec_fields = frozenset(OpenCodeLaunchSpec.model_fields)

    assert adapter.handled_fields == frozenset(SpawnParams.model_fields)
    assert adapter.consumed_fields | adapter.explicitly_ignored_fields == adapter.handled_fields
    assert adapter.consumed_fields & adapter.explicitly_ignored_fields == frozenset()
    assert launch_spec_fields == _OPENCODE_SUBPROCESS_PROJECTED_FIELDS
    assert launch_spec_fields == _OPENCODE_STREAMING_ACCOUNTED_FIELDS


def test_opencode_build_command_does_not_emit_dangerous_skip_permissions() -> None:
    command = OpenCodeAdapter().build_command(
        SpawnParams(prompt="test prompt", model=ModelId("opencode-gpt-5.3-codex")),
        _resolver(approval="yolo"),
    )

    assert "--dangerously-skip-permissions" not in command


def test_opencode_subprocess_projection_logs_model_flag_collision_and_keeps_tail(
    caplog: pytest.LogCaptureFixture,
) -> None:
    spec = OpenCodeLaunchSpec(
        prompt="test prompt",
        model="anthropic/claude-sonnet-4-5",
        extra_args=("-m", "override-model"),
        permission_resolver=_resolver(),
    )

    with caplog.at_level(
        logging.DEBUG, logger="meridian.lib.harness.projections.project_opencode_subprocess"
    ):
        command = project_opencode_spec_to_cli_args(spec, base_command=("opencode", "run"))

    assert command[-3:] == ["-m", "override-model", "-"]
    assert "model" in caplog.text.lower()
    assert "extra" in caplog.text.lower()


def test_opencode_primary_projection_uses_prompt_flag_instead_of_project_positional() -> None:
    command = project_opencode_spec_to_cli_args(
        OpenCodeLaunchSpec(
            prompt="prompt text",
            interactive=True,
            permission_resolver=_resolver(),
        ),
        base_command=("opencode",),
    )

    assert command == ["opencode", "--prompt", "prompt text"]


@pytest.mark.parametrize(
    "adapter",
    (
        ClaudeAdapter(),
        CodexAdapter(),
        OpenCodeAdapter(),
    ),
)
def test_resolve_launch_spec_keeps_none_effort(adapter: SubprocessHarness) -> None:
    resolver = _resolver()
    run = SpawnParams(prompt="test prompt", effort=None)

    spec = adapter.resolve_launch_spec(run, resolver)

    assert spec.effort is None


@pytest.mark.parametrize(
    "spec_cls",
    (
        ClaudeLaunchSpec,
        CodexLaunchSpec,
        OpenCodeLaunchSpec,
    ),
)
def test_continue_fork_requires_continue_session_id(spec_cls: type[ResolvedLaunchSpec]) -> None:
    with pytest.raises(ValidationError) as exc_info:
        spec_cls(
            prompt="test",
            continue_fork=True,
            permission_resolver=_resolver(),
        )

    assert "continue_fork=True requires continue_session_id" in str(exc_info.value)
    errors = exc_info.value.errors()
    assert len(errors) == 1
    assert errors[0]["type"] == "value_error"
    underlying = errors[0]["ctx"]["error"]
    assert isinstance(underlying, ValueError)
    assert str(underlying) == "continue_fork=True requires continue_session_id"


@pytest.mark.parametrize(
    ("spec_cls", "continue_session_id", "continue_fork"),
    (
        (ClaudeLaunchSpec, None, False),
        (ClaudeLaunchSpec, "claude-session", True),
        (CodexLaunchSpec, None, False),
        (CodexLaunchSpec, "codex-session", True),
        (OpenCodeLaunchSpec, None, False),
        (OpenCodeLaunchSpec, "opencode-session", True),
    ),
)
def test_continue_fork_valid_combinations_pass(
    spec_cls: type[ResolvedLaunchSpec],
    continue_session_id: str | None,
    continue_fork: bool,
) -> None:
    spec = spec_cls(
        prompt="test",
        continue_session_id=continue_session_id,
        continue_fork=continue_fork,
        permission_resolver=_resolver(),
    )

    assert spec.continue_session_id == continue_session_id
    assert spec.continue_fork is continue_fork
