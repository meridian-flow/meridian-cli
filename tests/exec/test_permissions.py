import json

import pytest

from meridian.lib.launch.env import build_harness_child_env, inherit_child_env, sanitize_child_env
from meridian.lib.launch.command import build_launch_env
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.launch.types import LaunchRequest
from meridian.lib.safety.permissions import (
    PermissionConfig,
    PermissionTier,
    build_permission_config,
    opencode_permission_json,
    permission_flags_for_harness,
)
from meridian.lib.core.types import HarnessId, ModelId


def test_auto_approval_bypass_and_invalid_approval() -> None:
    config = build_permission_config("full-access", approval="auto")
    assert config.tier is PermissionTier.FULL_ACCESS
    assert config.approval == "auto"
    assert permission_flags_for_harness(HarnessId("claude"), config) == [
        "--dangerously-skip-permissions"
    ]
    assert permission_flags_for_harness(HarnessId("codex"), config) == [
        "--dangerously-bypass-approvals-and-sandbox"
    ]

    with pytest.raises(ValueError, match="Unsupported approval mode"):
        build_permission_config("full-access", approval="sometimes")


def test_none_tier_defaults_to_harness_choice() -> None:
    config = build_permission_config(None)
    assert config.tier is None
    assert permission_flags_for_harness(HarnessId("claude"), config) == []
    assert permission_flags_for_harness(HarnessId("codex"), config) == []


@pytest.mark.parametrize(
    ("tier", "expected"),
    (
        (
            PermissionTier.READ_ONLY,
            {"*": "deny", "read": "allow", "grep": "allow", "glob": "allow", "list": "allow"},
        ),
        (
            PermissionTier.WORKSPACE_WRITE,
            {
                "*": "deny",
                "read": "allow",
                "grep": "allow",
                "glob": "allow",
                "list": "allow",
                "edit": "allow",
                "bash": "deny",
            },
        ),
        (PermissionTier.FULL_ACCESS, {"*": "allow"}),
    ),
)
def test_opencode_permission_json_matches_expected_mappings(
    tier: PermissionTier,
    expected: dict[str, str],
) -> None:
    assert json.loads(opencode_permission_json(tier)) == expected


def test_sanitize_child_env_filters_parent_secrets_and_keeps_explicit_overrides() -> None:
    base_env = {
        "PATH": "/usr/bin",
        "HOME": "/home/tester",
        "LANG": "en_US.UTF-8",
        "LC_ALL": "C.UTF-8",
        "XDG_RUNTIME_DIR": "/tmp/xdg",
        "UV_CACHE_DIR": "/tmp/uv",
        "EXAMPLE_TOKEN": "drop-me",
        "EXAMPLE_KEY": "drop-me-too",
        "ANTHROPIC_API_KEY": "allowed-credential",
    }
    env_overrides = {
        "MERIDIAN_DEPTH": "2",
        "CUSTOM_SECRET": "explicit-override",
    }

    sanitized = sanitize_child_env(
        base_env=base_env,
        env_overrides=env_overrides,
        pass_through={"ANTHROPIC_API_KEY"},
    )

    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["HOME"] == "/home/tester"
    assert sanitized["LC_ALL"] == "C.UTF-8"
    assert sanitized["XDG_RUNTIME_DIR"] == "/tmp/xdg"
    assert sanitized["UV_CACHE_DIR"] == "/tmp/uv"
    assert sanitized["ANTHROPIC_API_KEY"] == "allowed-credential"
    assert sanitized["MERIDIAN_DEPTH"] == "2"
    assert sanitized["CUSTOM_SECRET"] == "explicit-override"
    assert "EXAMPLE_TOKEN" not in sanitized
    assert "EXAMPLE_KEY" not in sanitized


def test_sanitize_child_env_does_not_leak_primary_autocompact_override() -> None:
    sanitized = sanitize_child_env(
        base_env={
            "PATH": "/usr/bin",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
        },
        env_overrides={"MERIDIAN_DEPTH": "2"},
        pass_through=set(),
    )

    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["MERIDIAN_DEPTH"] == "2"
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in sanitized


def test_inherit_child_env_keeps_parent_env_but_drops_internal_launch_overrides() -> None:
    inherited = inherit_child_env(
        base_env={
            "PATH": "/usr/bin",
            "UNRELATED_TOKEN": "keep-me",
            "MISC_VALUE": "keep-too",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
            "MERIDIAN_PRIMARY_PROMPT": "stale",
        },
        env_overrides={"MERIDIAN_DEPTH": "2"},
    )

    assert inherited["PATH"] == "/usr/bin"
    assert inherited["UNRELATED_TOKEN"] == "keep-me"
    assert inherited["MISC_VALUE"] == "keep-too"
    assert inherited["MERIDIAN_DEPTH"] == "2"
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in inherited
    assert "MERIDIAN_PRIMARY_PROMPT" not in inherited


def test_build_harness_child_env_uses_claude_specific_blocklist() -> None:
    child_env = build_harness_child_env(
        base_env={
            "PATH": "/usr/bin",
            "CLAUDECODE": "1",
            "UNRELATED_TOKEN": "keep-me",
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "67",
        },
        adapter=ClaudeAdapter(),
        run_params=SpawnParams(prompt="test", model=ModelId("claude-sonnet-4-6")),
        permission_config=PermissionConfig(),
        runtime_env_overrides={"MERIDIAN_DEPTH": "2"},
    )

    assert child_env["PATH"] == "/usr/bin"
    assert child_env["UNRELATED_TOKEN"] == "keep-me"
    assert child_env["MERIDIAN_DEPTH"] == "2"
    assert "CLAUDECODE" not in child_env
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in child_env


def test_build_launch_env_seeds_effective_permission_tier(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("MERIDIAN_PERMISSION_TIER", raising=False)

    env = build_launch_env(
        tmp_path,
        LaunchRequest(model="gpt-5.3-codex"),
        adapter=ClaudeAdapter(),
        run_params=SpawnParams(prompt="test", model=ModelId("claude-sonnet-4-6")),
        permission_config=PermissionConfig(tier=PermissionTier.WORKSPACE_WRITE),
    )

    assert env["MERIDIAN_PERMISSION_TIER"] == "workspace-write"


def test_build_launch_env_omits_permission_tier_when_unset(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.delenv("MERIDIAN_PERMISSION_TIER", raising=False)

    env = build_launch_env(
        tmp_path,
        LaunchRequest(model="gpt-5.3-codex"),
        adapter=ClaudeAdapter(),
        run_params=SpawnParams(prompt="test", model=ModelId("claude-sonnet-4-6")),
        permission_config=PermissionConfig(),
    )

    assert "MERIDIAN_PERMISSION_TIER" not in env
