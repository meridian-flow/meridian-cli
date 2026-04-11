"""Resolved launch spec tests for harness adapters."""

import pytest
from pydantic import ValidationError

from meridian.lib.core.types import ModelId
from meridian.lib.harness.adapter import SpawnParams, SubprocessHarness
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.launch_spec import (
    _SPEC_HANDLED_FIELDS,
    ClaudeLaunchSpec,
    CodexLaunchSpec,
    OpenCodeLaunchSpec,
    ResolvedLaunchSpec,
)
from meridian.lib.harness.opencode import OpenCodeAdapter
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
    assert spec.skills == ("skill-a", "skill-b")
    assert spec.permission_resolver.config == resolver.config


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


def test_launch_spec_completeness_guard_matches_spawn_params() -> None:
    assert set(SpawnParams.model_fields) == _SPEC_HANDLED_FIELDS


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
