import pytest

from meridian.lib.core.types import HarnessId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.harness.codex import CodexAdapter
from meridian.lib.harness.opencode import OpenCodeAdapter

type _HarnessAdapter = ClaudeAdapter | CodexAdapter | OpenCodeAdapter


class _NoopResolver:
    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        _ = harness_id
        return []


def test_claude_thinking_maps_xhigh_to_max() -> None:
    command = ClaudeAdapter().build_command(
        SpawnParams(prompt="do work", thinking="xhigh"),
        _NoopResolver(),
    )

    assert "--effort" in command
    assert command[command.index("--effort") + 1] == "max"


def test_codex_thinking_emits_reasoning_effort_config() -> None:
    command = CodexAdapter().build_command(
        SpawnParams(prompt="do work", thinking="high"),
        _NoopResolver(),
    )

    assert "-c" in command
    assert 'model_reasoning_effort="high"' in command


def test_opencode_thinking_emits_variant_flag() -> None:
    command = OpenCodeAdapter().build_command(
        SpawnParams(prompt="do work", thinking="medium"),
        _NoopResolver(),
    )

    assert "--variant" in command
    assert command[command.index("--variant") + 1] == "medium"


@pytest.mark.parametrize(
    ("adapter", "flag"),
    (
        (ClaudeAdapter(), "--effort"),
        (CodexAdapter(), "-c"),
        (OpenCodeAdapter(), "--variant"),
    ),
)
def test_missing_or_none_thinking_emits_no_flags(
    adapter: _HarnessAdapter,
    flag: str,
) -> None:
    command_default = adapter.build_command(
        SpawnParams(prompt="do work"),
        _NoopResolver(),
    )
    command_none = adapter.build_command(
        SpawnParams(prompt="do work", thinking=None),
        _NoopResolver(),
    )

    assert flag not in command_default
    assert flag not in command_none
