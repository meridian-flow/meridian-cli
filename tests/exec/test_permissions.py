import json

import pytest

from meridian.lib.core.types import ModelId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.claude import ClaudeAdapter
from meridian.lib.launch.command import build_launch_env
from meridian.lib.launch.env import build_harness_child_env, inherit_child_env, sanitize_child_env
from meridian.lib.launch.types import LaunchRequest
from meridian.lib.safety.permissions import (
    ExplicitToolsResolver,
    PermissionConfig,
    PermissionTier,
    build_permission_config,
    opencode_permission_json_for_allowed_tools,
    resolve_permission_pipeline,
)


def test_invalid_approval_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported approval mode"):
        build_permission_config("full-access", approval="sometimes")


def test_opencode_permission_json_for_allowed_tools_normalizes_tool_names() -> None:
    allowed_tools = ("Read", "Glob", "Grep", "Bash(git status)", "WebSearch")
    expected = {
        "*": "deny",
        "read": "allow",
        "glob": "allow",
        "grep": "allow",
        "bash": "allow",
        "websearch": "allow",
    }
    assert json.loads(opencode_permission_json_for_allowed_tools(allowed_tools)) == expected


def test_resolve_permission_pipeline_sets_opencode_override_for_explicit_tools() -> None:
    config, resolver = resolve_permission_pipeline(
        sandbox="workspace-write",
        allowed_tools=("Read", "Write"),
        approval="confirm",
    )

    assert isinstance(resolver, ExplicitToolsResolver)
    assert config.tier is PermissionTier.WORKSPACE_WRITE
    assert config.opencode_permission_override is not None
    assert json.loads(config.opencode_permission_override) == {
        "*": "deny",
        "read": "allow",
        "write": "allow",
    }


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


def test_inherit_child_env_keeps_parent_env_and_drops_autocompact_override() -> None:
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
    assert inherited["MERIDIAN_PRIMARY_PROMPT"] == "stale"
    assert "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE" not in inherited


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


def test_build_launch_env_never_exports_permission_tier(
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

    assert "MERIDIAN_PERMISSION_TIER" not in env
