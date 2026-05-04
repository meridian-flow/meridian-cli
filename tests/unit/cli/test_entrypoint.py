"""Tests for the startup-cheap CLI entrypoint fast paths."""

import pytest

from meridian.cli.entrypoint import (
    _is_root_help_request,
    _is_version_request,
    _validate_root_mode_flags,
)
from meridian.cli.startup.help import render_root_help


def test_root_help_request_detects_plain_help() -> None:
    assert _is_root_help_request(["--help"])
    assert _is_root_help_request(["-h"])


def test_root_help_request_skips_global_flag_values() -> None:
    assert _is_root_help_request(["--format", "json", "--help"])
    assert _is_root_help_request(["--model", "gptmini", "-h"])


def test_root_help_request_rejects_command_help() -> None:
    assert not _is_root_help_request(["spawn", "--help"])
    assert not _is_root_help_request(["--format", "json", "spawn", "-h"])


def test_version_request_detects_root_version() -> None:
    assert _is_version_request(["--version"])
    assert _is_version_request(["--format", "json", "--version"])


def test_version_request_rejects_command_version() -> None:
    assert not _is_version_request(["spawn", "--version"])


def test_validate_root_mode_flags_rejects_agent_and_human_together(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="1"):
        _validate_root_mode_flags(["--agent", "--human", "--help"])
    assert "Cannot combine --agent with --human." in capsys.readouterr().err


def test_render_root_help_agent_mode_matches_agent_help_shape() -> None:
    rendered = render_root_help(agent_mode=True)

    assert rendered.startswith("Usage: meridian COMMAND [ARGS]\n")
    assert "For automation, use --format json" in rendered
    assert "meridian spawn -m MODEL -p \"prompt\" --bg" in rendered
    assert "Commands:\n  spawn" in rendered


def test_render_root_help_human_mode_has_expected_sections() -> None:
    rendered = render_root_help(agent_mode=False)

    assert rendered.startswith("Usage: meridian [ARGS] [COMMAND]\n")
    assert "Options:" in rendered
    assert "Commands:" in rendered
    assert "Primary launch/resume:" in rendered
    assert "Bundled package manager: meridian mars ARGS..." in rendered
    assert "Run \"meridian spawn -h\" for subagent usage." in rendered
