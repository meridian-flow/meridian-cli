"""Smoke tests for CLI and server entry points."""

from __future__ import annotations

import json
import subprocess
import sys

from meridian import __version__


def test_help_lists_resource_first_groups(run_meridian) -> None:
    result = run_meridian(["--help"])
    assert result.returncode == 0
    for expected in [
        "serve",
        "space",
        "run",
        "skills",
        "models",
        "doctor",
        "start",
    ]:
        assert expected in result.stdout


def test_help_is_restricted_in_agent_mode(package_root, cli_env) -> None:
    env = dict(cli_env)
    env["MERIDIAN_SPACE_ID"] = "s-test"
    completed = subprocess.run(
        [sys.executable, "-m", "meridian", "--help"],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0
    assert "run" in completed.stdout
    assert "skills" in completed.stdout
    assert "models" in completed.stdout
    assert "doctor" in completed.stdout
    assert "space" not in completed.stdout
    assert "config" not in completed.stdout
    assert "completion" not in completed.stdout
    assert "start" not in completed.stdout
    assert "serve" not in completed.stdout
    assert "init" not in completed.stdout


def test_hidden_human_flag_restores_full_help(package_root, cli_env) -> None:
    env = dict(cli_env)
    env["MERIDIAN_SPACE_ID"] = "s-test"
    completed = subprocess.run(
        [sys.executable, "-m", "meridian", "--human", "--help"],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0
    assert "space" in completed.stdout
    assert "config" in completed.stdout
    assert "serve" in completed.stdout


def test_version_flag_prints_package_version(run_meridian) -> None:
    result = run_meridian(["--version"])
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_serve_exits_cleanly_on_eof(package_root, cli_env) -> None:
    proc = subprocess.Popen(
        [sys.executable, "-m", "meridian", "serve"],
        cwd=package_root,
        env=cli_env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdin is not None
    proc.stdin.close()
    proc.wait(timeout=5)
    assert proc.returncode == 0


def test_json_and_format_flags_output_stdout_only(run_meridian) -> None:
    result = run_meridian(["--json", "run", "--dry-run", "-p", "hello"])
    assert result.returncode == 0
    assert "Traceback" not in result.stderr
    payload = json.loads(result.stdout)
    assert payload["command"] == "run.spawn"
    assert payload["status"] == "dry-run"

    result_format = run_meridian(["--format", "json", "start"])
    assert result_format.returncode == 0
    payload_format = json.loads(result_format.stdout)
    assert payload_format["space_id"].startswith("s")


def test_yes_and_no_input_flags_are_wired(run_meridian) -> None:
    result = run_meridian(
        ["--yes", "--no-input", "--json", "run", "--dry-run", "-p", "prompt text"]
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry-run"


def test_space_start_supports_dry_run(run_meridian) -> None:
    result = run_meridian(["--json", "space", "start", "--dry-run"])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["message"] == "Space launch dry-run."
    assert payload["exit_code"] == 0
    assert "mock_harness.py" in payload["command"][1]


def test_completion_bash_emits_script(run_meridian) -> None:
    result = run_meridian(["completion", "bash"])
    assert result.returncode == 0
    assert "meridian" in result.stdout


def test_doctor_command_runs_standalone(run_meridian) -> None:
    result = run_meridian(["--json", "doctor"])
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["repo_root"]
    assert "spaces_checked" in payload
    assert "runs_checked" in payload
    assert payload["agents_dir"]
    assert payload["skills_dir"]


def test_run_spawn_help_hides_human_flags_in_agent_mode(package_root, cli_env) -> None:
    env = dict(cli_env)
    env["MERIDIAN_SPACE_ID"] = "s-test"
    completed = subprocess.run(
        [sys.executable, "-m", "meridian", "run", "spawn", "--help"],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0
    # Agent-relevant flags should be visible
    assert "--prompt" in completed.stdout
    assert "--model" in completed.stdout
    assert "--agent" in completed.stdout
    assert "--background" in completed.stdout
    assert "--permission" in completed.stdout
    assert "--timeout-secs" in completed.stdout
    # Human-only flags should be hidden
    assert "--verbose" not in completed.stdout
    assert "--quiet" not in completed.stdout
    assert "--report-path" not in completed.stdout
    assert "--budget-usd" not in completed.stdout
    assert "--budget-per-run-usd" not in completed.stdout
    assert "--budget-per-space-usd" not in completed.stdout
    assert "--guardrail" not in completed.stdout
    assert "--secret" not in completed.stdout
    assert "--unsafe" not in completed.stdout
    assert "--stream" not in completed.stdout


def test_run_spawn_help_shows_all_flags_in_human_mode(package_root, cli_env) -> None:
    # No MERIDIAN_SPACE_ID = human mode, all flags visible
    completed = subprocess.run(
        [sys.executable, "-m", "meridian", "run", "spawn", "--help"],
        cwd=package_root,
        env=cli_env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0
    assert "--verbose" in completed.stdout
    assert "--quiet" in completed.stdout
    assert "--report-path" in completed.stdout
    assert "--unsafe" not in completed.stdout
    assert "--budget-per-run-usd" not in completed.stdout
    assert "--budget-per-space-usd" not in completed.stdout
    assert "--budget-usd" not in completed.stdout
    assert "--guardrail" not in completed.stdout
    assert "--secret" not in completed.stdout
