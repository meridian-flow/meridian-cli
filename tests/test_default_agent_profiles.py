"""Slice 3 default agent profile resolution tests."""

from __future__ import annotations

from pathlib import Path

import pytest

import meridian.lib.ops.spawn as run_ops
import meridian.lib.safety.permissions as permission_safety
import meridian.lib.space.launch as space_launch
from meridian.lib.config._paths import bundled_agents_root
from meridian.lib.config.agent import _BUILTIN_PATH, load_agent_profile
from meridian.lib.ops.spawn import SpawnCreateInput
from meridian.lib.types import SpaceId
from meridian.lib.space.launch import (
    SpaceLaunchRequest,
    _build_interactive_command,
    _resolve_primary_session_metadata,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_config(repo_root: Path, content: str) -> None:
    _write(repo_root / ".meridian" / "config.toml", content)


def _write_skill(repo_root: Path, name: str, body: str) -> None:
    _write(
        repo_root / ".agents" / "skills" / name / "SKILL.md",
        (
            "---\n"
            f"name: {name}\n"
            f"description: {name} skill\n"
            "---\n\n"
            f"{body}\n"
        ),
    )


def _write_agent(
    repo_root: Path,
    *,
    name: str,
    model: str,
    skills: list[str],
    sandbox: str | None = None,
    mcp_tools: list[str] | None = None,
    allowed_tools: list[str] | None = None,
) -> None:
    lines = [
        "---",
        f"name: {name}",
        f"model: {model}",
        f"skills: [{', '.join(skills)}]",
    ]
    if sandbox is not None:
        lines.append(f"sandbox: {sandbox}")
    if mcp_tools is not None:
        lines.append(f"mcp-tools: [{', '.join(mcp_tools)}]")
    if allowed_tools is not None:
        lines.append(f"allowed-tools: [{', '.join(allowed_tools)}]")
    lines.append("---")
    lines.extend(["", f"# {name}", "", "Agent body."])
    _write(repo_root / ".agents" / "agents" / f"{name}.md", "\n".join(lines) + "\n")


def _allowed_tools_from_command(command: tuple[str, ...]) -> tuple[str, ...]:
    payload = command[command.index("--allowedTools") + 1]
    return tuple(item.strip() for item in payload.split(",") if item.strip())


def _flag_count(command: tuple[str, ...], flag: str) -> int:
    return sum(1 for token in command if token == flag)


def test_run_uses_default_agent_profile_and_profile_skills(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "[defaults]\nagent = 'reviewer'\n",
    )
    _write_agent(
        tmp_path,
        name="reviewer",
        model="gpt-5.3-codex",
        skills=["reviewing"],
        sandbox="workspace-write",
    )
    _write_skill(tmp_path, "reviewing", "Review skill content")

    result = run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="review the changes",
            dry_run=True,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "dry-run"
    assert result.model == "gpt-5.3-codex"
    assert result.agent == "reviewer"


def test_run_falls_back_to_bundled_agent_when_configured_profile_missing(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        "[defaults]\nagent = 'missing-profile'\n",
    )
    _write_skill(tmp_path, "run-agent", "Spawn delegation skill")
    _write_skill(tmp_path, "agent", "Agent baseline skill")

    result = run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="fallback behavior",
            model="gpt-5.3-codex",
            dry_run=True,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "dry-run"
    assert result.agent == "agent"


def test_space_primary_profile_controls_model_skills_and_sandbox(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "[defaults]\ndefault_primary_agent = 'lead-primary'\n",
    )
    _write_agent(
        tmp_path,
        name="lead-primary",
        model="claude-sonnet-4-6",
        skills=["orchestrate"],
        sandbox="unrestricted",
    )
    _write_skill(tmp_path, "orchestrate", "Primary orchestration content")

    request = SpaceLaunchRequest(space_id=SpaceId("w1"))
    command = _build_interactive_command(
        repo_root=tmp_path,
        request=request,
        prompt="space prompt",
        passthrough_args=(),
        chat_id="c1",
    )

    assert command[command.index("--model") + 1] == "claude-sonnet-4-6"
    assert "--allowedTools" in command
    assert "--agent" in command
    assert command[command.index("--agent") + 1] == "_meridian-c1-lead-primary"
    assert "--append-system-prompt" in command
    assert "Primary orchestration content" in command[command.index("--append-system-prompt") + 1]
    assert "--system-prompt" not in command


def test_space_primary_profile_without_skills_omits_skill_injection(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "[defaults]\ndefault_primary_agent = 'lead-primary'\n",
    )
    _write_agent(
        tmp_path,
        name="lead-primary",
        model="claude-sonnet-4-6",
        skills=[],
        sandbox="unrestricted",
    )

    command = _build_interactive_command(
        repo_root=tmp_path,
        request=SpaceLaunchRequest(space_id=SpaceId("w1")),
        prompt="space prompt",
        passthrough_args=(),
        chat_id="c1",
    )

    assert "--append-system-prompt" not in command


def test_space_primary_profile_missing_falls_back_to_bundled_primary(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        "[defaults]\ndefault_primary_agent = 'missing-primary'\n",
    )

    metadata = _resolve_primary_session_metadata(
        repo_root=tmp_path,
        request=SpaceLaunchRequest(space_id=SpaceId("w1")),
        config=space_launch.load_config(tmp_path),
    )

    assert metadata.agent == "primary"
    assert metadata.model == "claude-opus-4-6"


def test_space_primary_profile_missing_sandbox_uses_default_permission_tier(
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        (
            "[defaults]\n"
            "default_primary_agent = 'lead-primary'\n"
            "\n"
            "[permissions]\n"
            "default_tier = 'workspace-write'\n"
            "\n"
            "[primary]\n"
            "permission_tier = 'workspace-write'\n"
        ),
    )
    _write_agent(
        tmp_path,
        name="lead-primary",
        model="claude-sonnet-4-6",
        skills=["orchestrate"],
    )
    _write_skill(tmp_path, "orchestrate", "Primary orchestration content")

    command = _build_interactive_command(
        repo_root=tmp_path,
        request=SpaceLaunchRequest(space_id=SpaceId("w1")),
        prompt="space prompt",
        passthrough_args=(),
        chat_id="c1",
    )

    assert "--allowedTools" in command
    allowed_tools = _allowed_tools_from_command(command)
    assert "Edit" in allowed_tools
    assert "Write" in allowed_tools


def test_space_primary_profile_unknown_sandbox_uses_default_permission_tier_with_warning(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        (
            "[defaults]\n"
            "default_primary_agent = 'lead-primary'\n"
            "\n"
            "[permissions]\n"
            "default_tier = 'read-only'\n"
            "\n"
            "[primary]\n"
            "permission_tier = 'read-only'\n"
        ),
    )
    _write_agent(
        tmp_path,
        name="lead-primary",
        model="claude-sonnet-4-6",
        skills=["orchestrate"],
        sandbox="full_access",
    )
    _write_skill(tmp_path, "orchestrate", "Primary orchestration content")

    class _Logger:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def warning(self, message: str, *args: object) -> None:
            self.messages.append(message % args if args else message)

    stub_logger = _Logger()
    monkeypatch.setattr(space_launch, "logger", stub_logger)

    command = _build_interactive_command(
        repo_root=tmp_path,
        request=SpaceLaunchRequest(space_id=SpaceId("w1")),
        prompt="space prompt",
        passthrough_args=(),
        chat_id="c1",
    )

    assert "--allowedTools" in command
    allowed_tools = _allowed_tools_from_command(command)
    assert "Edit" not in allowed_tools
    assert "Write" not in allowed_tools
    assert any(
        message
        == (
            "Agent profile 'lead-primary' has unsupported sandbox 'full_access'; "
            "falling back to default permission tier 'read-only'."
        )
        for message in stub_logger.messages
    )


def test_space_primary_profile_non_claude_model_raises_clear_error(tmp_path: Path) -> None:
    _write_config(
        tmp_path,
        "[defaults]\ndefault_primary_agent = 'lead-primary'\n",
    )
    _write_agent(
        tmp_path,
        name="lead-primary",
        model="gpt-5.3-codex",
        skills=[],
        sandbox="workspace-write",
    )

    with pytest.raises(
        ValueError,
        match=(
            r"Primary agent only supports Claude harness models. "
            "Model 'gpt-5.3-codex' routes to harness 'codex'."
        ),
    ):
        _build_interactive_command(
            repo_root=tmp_path,
            request=SpaceLaunchRequest(space_id=SpaceId("w1")),
            prompt="space prompt",
            passthrough_args=(),
            chat_id="c1",
        )


def test_agent_profile_parses_mcp_tools_and_defaults_to_empty_tuple(tmp_path: Path) -> None:
    _write_agent(
        tmp_path,
        name="mcp-agent",
        model="gpt-5.3-codex",
        skills=["agent"],
        mcp_tools=["spawn_list", "spawn_show"],
    )
    _write_agent(
        tmp_path,
        name="plain-agent",
        model="gpt-5.3-codex",
        skills=["agent"],
    )

    mcp_profile = load_agent_profile("mcp-agent", repo_root=tmp_path)
    plain_profile = load_agent_profile("plain-agent", repo_root=tmp_path)

    assert mcp_profile.mcp_tools == ("spawn_list", "spawn_show")
    assert plain_profile.mcp_tools == ()


def test_builtin_agent_profile_used_when_no_file_on_disk(tmp_path: Path) -> None:
    """When no agent.md exists on disk, load_agent_profile returns bundled defaults."""
    profile = load_agent_profile("agent", repo_root=tmp_path)
    bundled_root = bundled_agents_root()
    assert bundled_root is not None
    assert profile.name == "agent"
    assert profile.model == "gpt-5.3-codex"
    assert profile.sandbox == "workspace-write"
    assert profile.path == (bundled_root / "agents" / "agent.md").resolve()
    assert profile.path != _BUILTIN_PATH


def test_builtin_primary_profile_used_when_no_file_on_disk(tmp_path: Path) -> None:
    """When no primary.md exists on disk, load_agent_profile returns bundled defaults."""
    profile = load_agent_profile("primary", repo_root=tmp_path)
    bundled_root = bundled_agents_root()
    assert bundled_root is not None
    assert profile.name == "primary"
    assert profile.model == "claude-opus-4-6"
    assert profile.sandbox == "unrestricted"
    assert profile.skills == ("orchestrate", "meridian-spawn-agent")
    assert profile.path == (bundled_root / "agents" / "primary.md").resolve()
    assert profile.path != _BUILTIN_PATH


def test_disk_profile_takes_precedence_over_builtin(tmp_path: Path) -> None:
    """A file on disk should shadow the built-in profile of the same name."""
    _write_agent(
        tmp_path,
        name="agent",
        model="claude-sonnet-4-6",
        skills=["custom-skill"],
        sandbox="read-only",
    )
    profile = load_agent_profile("agent", repo_root=tmp_path)
    assert profile.model == "claude-sonnet-4-6"
    assert profile.path != _BUILTIN_PATH


def test_run_uses_builtin_default_agent_when_no_profile_on_disk(tmp_path: Path) -> None:
    """spawn_create_sync should resolve the built-in 'agent' profile as default."""
    result = run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="hello",
            dry_run=True,
            repo_root=tmp_path.as_posix(),
        )
    )
    assert result.status == "dry-run"
    assert result.model == "gpt-5.3-codex"
    assert result.agent == "agent"
    assert "--config" in result.cli_command
    assert any(
        token.startswith("mcp_servers.meridian.command=") for token in result.cli_command
    )


def test_claude_command_merges_permission_and_mcp_allowed_tools(tmp_path: Path) -> None:
    _write_agent(
        tmp_path,
        name="claude-reviewer",
        model="claude-sonnet-4-6",
        skills=[],
        sandbox="workspace-write",
        mcp_tools=["spawn_list", "spawn_show"],
    )

    result = run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="review changes",
            dry_run=True,
            agent="claude-reviewer",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "dry-run"
    assert result.harness_id == "claude"
    assert "--agent" in result.cli_command
    assert (
        result.cli_command[result.cli_command.index("--agent") + 1] == "claude-reviewer"
    )
    assert "--mcp-config" in result.cli_command
    assert _flag_count(result.cli_command, "--allowedTools") == 1
    allowed_tools = _allowed_tools_from_command(result.cli_command)
    assert "Edit" in allowed_tools
    assert "Write" in allowed_tools
    assert "mcp__meridian__spawn_list" in allowed_tools
    assert "mcp__meridian__spawn_show" in allowed_tools


def test_run_logs_warning_when_profile_sandbox_exceeds_config_default(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _write_config(
        tmp_path,
        (
            "[defaults]\n"
            "agent = 'unsafe-agent'\n"
            "\n"
            "[permissions]\n"
            "default_tier = 'read-only'\n"
        ),
    )
    _write_agent(
        tmp_path,
        name="unsafe-agent",
        model="gpt-5.3-codex",
        skills=["run-agent", "agent"],
        sandbox="unrestricted",
    )
    _write_skill(tmp_path, "run-agent", "Spawn delegation skill")
    _write_skill(tmp_path, "agent", "Agent baseline skill")

    class _Logger:
        def __init__(self) -> None:
            self.messages: list[str] = []

        def warning(self, message: str) -> None:
            self.messages.append(message)

    stub_logger = _Logger()
    monkeypatch.setattr(run_ops, "logger", stub_logger)
    monkeypatch.setattr(permission_safety, "logger", stub_logger)

    # Warning only fires when agent is explicitly requested (not implicit default)
    run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="check warning",
            agent="unsafe-agent",
            dry_run=True,
            repo_root=tmp_path.as_posix(),
        )
    )

    assert any(
        message
        == (
            "Agent profile 'unsafe-agent' infers full-access "
            "(config default: read-only). Use --permission to override."
        )
        for message in stub_logger.messages
    )


def test_explicit_allowed_tools_replace_tier_tools_for_claude(tmp_path: Path) -> None:
    """When allowed-tools is set, Claude gets exactly those tools instead of tier-derived ones."""
    _write_agent(
        tmp_path,
        name="researcher",
        model="claude-sonnet-4-6",
        skills=[],
        sandbox="read-only",
        allowed_tools=["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
    )

    result = run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="research task",
            dry_run=True,
            agent="researcher",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "dry-run"
    assert result.harness_id == "claude"
    allowed_tools = _allowed_tools_from_command(result.cli_command)
    # Should have exactly the profile tools (plus MCP tools), NOT tier tools
    assert "Read" in allowed_tools
    assert "Glob" in allowed_tools
    assert "WebSearch" in allowed_tools
    assert "WebFetch" in allowed_tools
    # Tier read-only tools that are NOT in the explicit list should be absent
    assert "Bash(git status)" not in allowed_tools
    assert "Bash(git log)" not in allowed_tools


def test_explicit_allowed_tools_codex_falls_back_to_sandbox(tmp_path: Path) -> None:
    """Codex doesn't support per-tool allowlists; sandbox tier is used as fallback."""
    _write_agent(
        tmp_path,
        name="codex-researcher",
        model="gpt-5.3-codex",
        skills=[],
        sandbox="read-only",
        allowed_tools=["Read", "Glob", "WebSearch"],
    )

    result = run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="research task",
            dry_run=True,
            agent="codex-researcher",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "dry-run"
    assert result.harness_id == "codex"
    # Codex should use --sandbox from the sandbox field, not --allowedTools
    assert "--sandbox" in result.cli_command
    sandbox_value = result.cli_command[result.cli_command.index("--sandbox") + 1]
    assert sandbox_value == "read-only"
    assert "--allowedTools" not in result.cli_command


def test_cli_permission_overrides_explicit_allowed_tools(tmp_path: Path) -> None:
    """CLI --permission flag takes precedence over profile allowed-tools."""
    _write_agent(
        tmp_path,
        name="restricted",
        model="claude-sonnet-4-6",
        skills=[],
        sandbox="read-only",
        allowed_tools=["Read", "Glob"],
    )

    result = run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="override test",
            dry_run=True,
            agent="restricted",
            permission_tier="full-access",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "dry-run"
    allowed_tools = _allowed_tools_from_command(result.cli_command)
    # Full-access tier tools should be present, not the explicit list
    assert "Bash" in allowed_tools
    assert "WebFetch" in allowed_tools
    assert "Edit" in allowed_tools


def test_explicit_allowed_tools_merge_with_mcp_tools(tmp_path: Path) -> None:
    """Profile allowed-tools and mcp-tools should both appear in --allowedTools."""
    _write_agent(
        tmp_path,
        name="mcp-researcher",
        model="claude-sonnet-4-6",
        skills=[],
        sandbox="read-only",
        allowed_tools=["Read", "Glob", "Grep"],
        mcp_tools=["spawn_list", "spawn_show"],
    )

    result = run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="merge test",
            dry_run=True,
            agent="mcp-researcher",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "dry-run"
    assert _flag_count(result.cli_command, "--allowedTools") == 1
    allowed_tools = _allowed_tools_from_command(result.cli_command)
    # Explicit profile tools
    assert "Read" in allowed_tools
    assert "Glob" in allowed_tools
    assert "Grep" in allowed_tools
    # MCP tools
    assert "mcp__meridian__spawn_list" in allowed_tools
    assert "mcp__meridian__spawn_show" in allowed_tools


def test_empty_allowed_tools_falls_back_to_tier(tmp_path: Path) -> None:
    """When no allowed-tools are specified, tier-based behavior is unchanged."""
    _write_agent(
        tmp_path,
        name="tier-agent",
        model="claude-sonnet-4-6",
        skills=[],
        sandbox="workspace-write",
    )

    result = run_ops.spawn_create_sync(
        SpawnCreateInput(
            prompt="tier test",
            dry_run=True,
            agent="tier-agent",
            repo_root=tmp_path.as_posix(),
        )
    )

    assert result.status == "dry-run"
    allowed_tools = _allowed_tools_from_command(result.cli_command)
    assert "Edit" in allowed_tools
    assert "Write" in allowed_tools
    assert "Bash(git add)" in allowed_tools
