"""Slice B space launch regressions."""

from __future__ import annotations

import json
from pathlib import Path

from meridian.lib.ops.space import SpaceStartInput, space_start_sync
from meridian.lib.types import SpaceId
from meridian.lib.space.launch import (
    SpaceLaunchRequest,
    _build_space_env,
    _build_harness_command,
    _build_interactive_command,
    build_primary_prompt,
    cleanup_orphaned_locks,
)
from meridian.lib.space.space_file import create_space, get_space


def _install_config(repo_root: Path, content: str) -> None:
    config_path = repo_root / ".meridian" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content, encoding="utf-8")


def test_build_interactive_command_uses_system_prompt_model_and_passthrough(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)

    request = SpaceLaunchRequest(
        space_id=SpaceId("s42"),
        model="claude-opus-4-6",
        fresh=True,
    )
    prompt = build_primary_prompt(request)

    command = _build_interactive_command(
        repo_root=tmp_path,
        request=request,
        prompt=prompt,
        passthrough_args=("--permission-mode", "acceptEdits"),
    )

    assert command[0] == "claude"
    assert "-p" not in command
    assert "--system-prompt" in command
    assert prompt in command[command.index("--system-prompt") + 1]
    assert "--model" in command
    assert command[command.index("--model") + 1] == "claude-opus-4-6"
    assert "--permission-mode" in command
    assert "acceptEdits" in command


def test_build_space_env_sanitizes_parent_env_and_keeps_space_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("PATH", "/usr/local/bin:/usr/bin")
    monkeypatch.setenv("HOME", "/home/sliceb")
    monkeypatch.setenv("LANG", "C.UTF-8")
    monkeypatch.setenv("MY_SECRET_TOKEN", "do-not-forward")
    monkeypatch.setenv("RANDOM_PARENT_VALUE", "drop-me")
    monkeypatch.setenv("MERIDIAN_DEPTH", "5")

    request = SpaceLaunchRequest(
        space_id=SpaceId("s99"),
        autocompact=80,
    )
    env = _build_space_env(tmp_path, request, "space prompt")

    assert env["PATH"] == "/usr/local/bin:/usr/bin"
    assert env["HOME"] == "/home/sliceb"
    assert env["LANG"] == "C.UTF-8"
    assert "MY_SECRET_TOKEN" not in env
    assert "RANDOM_PARENT_VALUE" not in env
    assert env["MERIDIAN_SPACE_ID"] == "s99"
    assert env["MERIDIAN_DEPTH"] == "5"
    assert env["MERIDIAN_SPACE_PROMPT"] == "space prompt"
    assert env["MERIDIAN_STATE_ROOT"] == (tmp_path / ".meridian").as_posix()
    assert env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "80"


def test_primary_settings_apply_to_harness_command_and_env(tmp_path: Path) -> None:
    _install_config(
        tmp_path,
        (
            "[permissions]\n"
            "default_tier = 'read-only'\n"
            "\n"
            "[primary]\n"
            "autocompact_pct = 67\n"
            "permission_tier = 'workspace-write'\n"
        ),
    )
    request = SpaceLaunchRequest(space_id=SpaceId("s100"))

    command = _build_harness_command(
        repo_root=tmp_path,
        request=request,
        prompt="space prompt",
    )

    assert "--autocompact" not in command
    assert "--allowedTools" in command
    allowed_tools = command[command.index("--allowedTools") + 1]
    assert "Edit" in allowed_tools
    assert "Write" in allowed_tools

    env = _build_space_env(
        tmp_path,
        request,
        "space prompt",
        default_autocompact_pct=67,
    )
    assert env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "67"
    assert env["MERIDIAN_STATE_ROOT"] == (tmp_path / ".meridian").as_posix()


def test_cleanup_orphaned_locks_removes_stale_lock_and_pauses_space(tmp_path: Path) -> None:
    space = create_space(tmp_path, name="orphaned")

    lock_path = tmp_path / ".meridian" / "active-spaces" / f"{space.id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "space_id": str(space.id),
                "child_pid": 999_999,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cleaned = cleanup_orphaned_locks(tmp_path)

    assert cleaned == (SpaceId(space.id),)
    assert not lock_path.exists()

    refreshed = get_space(tmp_path, space.id)
    assert refreshed is not None
    assert refreshed.status == "closed"


def test_space_start_dry_run_returns_interactive_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("MERIDIAN_HARNESS_COMMAND", raising=False)

    result = space_start_sync(
        SpaceStartInput(
            repo_root=tmp_path.as_posix(),
            dry_run=True,
        )
    )

    assert result.state == "active"
    assert result.exit_code == 0
    assert result.message == "Space launch dry-run."
    assert result.lock_path is not None
    assert not Path(result.lock_path).exists()
    assert result.command[0] == "claude"
    assert "-p" not in result.command
    assert "--system-prompt" in result.command
