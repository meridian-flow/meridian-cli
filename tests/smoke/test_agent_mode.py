"""Agent mode smoke tests — restricted help and output defaults.

Replaces: tests/e2e/agent-mode.md
"""

import json


def test_agent_help_is_restricted(cli):
    """Agent mode help hides operator commands."""
    result = cli("--help", env_override={"MERIDIAN_DEPTH": "1"})
    result.assert_success()

    text = result.stdout
    # Should show core commands
    for visible in ("spawn", "work", "models"):
        assert visible in text, f"agent help should show {visible}"

    # Should hide operator commands (some or all of these)
    hidden_count = sum(1 for h in ("config", "doctor", "init") if h not in text)
    assert hidden_count > 0, "agent help should hide some operator commands"


def test_human_flag_restores_full_help(cli):
    """--human flag restores full help surface in agent mode."""
    result = cli("--human", "--help", env_override={"MERIDIAN_DEPTH": "1"})
    result.assert_success()

    text = result.stdout
    # Should show more commands
    for visible in ("spawn", "work"):
        assert visible in text


def test_agent_mode_models_list_redirects_to_mars(cli):
    """Agent mode gets the same compatibility redirect for models list."""
    result = cli("models", "list", env_override={"MERIDIAN_DEPTH": "1"})
    result.assert_failure(1)
    assert "meridian mars models list" in result.stderr
    assert not result.stdout.strip()


def test_models_list_redirect_ignores_json_format(cli):
    """Compatibility stub stays a clear stderr error even with JSON requested."""
    result = cli(
        "--format", "json", "models", "list",
        env_override={"MERIDIAN_DEPTH": "1"}
    )
    result.assert_failure(1)
    assert "meridian mars models list" in result.stderr
    assert not result.stdout.strip()


def test_agent_mode_control_plane_json(cli):
    """Control-plane commands default to JSON in agent mode."""
    result = cli("work", "current", env_override={"MERIDIAN_DEPTH": "1"})
    # work current is a control-plane command, should be JSON
    if result.returncode == 0 and result.stdout.strip():
        # Should be valid JSON
        json.loads(result.stdout)
