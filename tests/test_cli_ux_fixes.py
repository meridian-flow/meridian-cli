"""Regression tests for CLI UX bug fixes in Slice A."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from meridian.lib import logging as cli_logging

cli_main = importlib.import_module("meridian.cli.main")


def _write_skill(repo_root: Path, name: str, body: str) -> None:
    skill_file = repo_root / ".agents" / "skills" / name / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(
        (
            "---\n"
            f"name: {name}\n"
            f"description: {name} skill\n"
            "---\n\n"
            f"{body}\n"
        ),
        encoding="utf-8",
    )


def _run_cli(
    *,
    package_root: Path,
    cli_env: dict[str, str],
    repo_root: Path,
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    env = dict(cli_env)
    env["MERIDIAN_REPO_ROOT"] = repo_root.as_posix()
    return subprocess.run(
        [sys.executable, "-m", "meridian", *args],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=20,
    )


def _seed_base_skills(repo_root: Path) -> None:
    _write_skill(repo_root, "run-agent", "Base run-agent skill.")
    _write_skill(repo_root, "agent", "Base agent skill.")


def test_bug5_prompt_text_uses_rendered_template_not_repr(
    package_root: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    _seed_base_skills(repo_root)

    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=repo_root,
        args=["--json", "run", "--dry-run", "-m", "codex", "-p", "hello"],
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry-run"
    assert "Template(strings" not in payload["composed_prompt"]
    assert "hello" in payload["composed_prompt"]


def test_bug6_gemini_alias_routes_to_opencode(
    package_root: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    _seed_base_skills(repo_root)

    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=repo_root,
        args=["--json", "run", "--dry-run", "-m", "gemini", "-p", "test"],
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["model"] == "gemini-3.1-pro"
    assert payload["harness_id"] == "opencode"


def test_bug8_unknown_model_fails_fast_with_clean_error(
    package_root: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    _seed_base_skills(repo_root)

    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=repo_root,
        args=["--json", "run", "--dry-run", "-m", "nonexistent-model", "-p", "test"],
    )

    assert result.returncode != 0
    assert "Unknown model 'nonexistent-model'" in result.stderr
    assert "Traceback" not in result.stderr
    # In JSON mode, a structured error is also emitted to stdout for agent callers.
    import json as _json
    if result.stdout.strip():
        error_obj = _json.loads(result.stdout.strip())
        assert "error" in error_obj
        assert "Unknown model" in error_obj["error"]


def test_ol10_unknown_model_error_includes_available_models_and_suggestion(
    package_root: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    _seed_base_skills(repo_root)

    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=repo_root,
        args=["run", "--dry-run", "-m", "codxe", "-p", "test"],
    )

    assert result.returncode != 0
    assert "Unknown model alias 'codxe'" in result.stderr
    assert "Available models:" in result.stderr
    assert "[codex]" in result.stderr
    assert "Did you mean: gpt-5.3-codex?" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "args,error_fragment",
    [
        pytest.param(
            ["skills", "show", "nonexistent-skill"],
            "Unknown skills: nonexistent-skill",
            id="skills-show",
        ),
        pytest.param(
            ["run", "show", "nonexistent-run"],
            "Run 'nonexistent-run' not found",
            id="run-show",
        ),
    ],
)
def test_bug16_show_unknown_resource_emits_clean_error(
    args: list[str],
    error_fragment: str,
    package_root: Path,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _seed_base_skills(repo_root)
    if args[:2] == ["run", "show"]:
        cli_env["MERIDIAN_SPACE_ID"] = "s1"

    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=repo_root,
        args=args,
    )

    assert result.returncode != 0
    assert error_fragment in result.stderr
    assert "Traceback" not in result.stderr


def test_bug17_run_create_requires_nonempty_prompt(
    package_root: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    _seed_base_skills(repo_root)

    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=repo_root,
        args=["run", "--dry-run"],
    )

    assert result.returncode != 0
    assert "prompt required" in result.stderr.lower()
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "flag",
    ["--no-json", "--no-porcelain", "--no-yes", "--no-no-input"],
)
def test_bug3_no_prefixed_global_flags_are_accepted(
    flag: str, package_root: Path, cli_env: dict[str, str], tmp_path: Path
) -> None:
    repo_root = tmp_path / "repo"
    _seed_base_skills(repo_root)

    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=repo_root,
        args=[flag, "--json", "run", "--dry-run", "-m", "codex", "-p", "hello"],
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "run.spawn"
    assert payload["status"] == "dry-run"


def test_dx2_unknown_top_level_command_has_clean_error(
    package_root: Path,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=tmp_path / "repo",
        args=["foo"],
    )

    assert result.returncode == 1
    assert "Unknown command: foo" in result.stderr
    assert "Invalid value for \"JSON\"" not in result.stderr


def test_dx2_init_alias_routes_to_config_init(
    package_root: Path,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=repo_root,
        args=["init"],
    )

    assert result.returncode == 0
    assert (repo_root / ".meridian" / "config.toml").is_file()


def test_dx3_help_uses_descriptions_and_hides_empty_flags(
    package_root: Path,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _seed_base_skills(repo_root)
    result = _run_cli(
        package_root=package_root,
        cli_env=cli_env,
        repo_root=repo_root,
        args=["run", "spawn", "--help"],
    )

    assert result.returncode == 0
    assert "--empty-" not in result.stdout
    assert "Prompt text for the run." in result.stdout
    assert "--skills" not in result.stdout
    assert ": [default:" not in result.stdout


def test_dx5_timeout_error_returns_exit_code_124(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli_logging, "configure_logging", lambda json_mode, verbosity: None)
    monkeypatch.setattr(cli_main, "cleanup_orphaned_locks", lambda repo_root: None)
    monkeypatch.setattr(
        cli_main,
        "cleanup_stale_sessions",
        lambda space_dir, repo_root=None: [],
    )
    monkeypatch.setattr(cli_main, "resolve_repo_root", lambda: Path.cwd())
    monkeypatch.setattr(cli_main, "resolve_all_spaces_dir", lambda repo_root: Path.cwd() / ".missing")

    def _raise_timeout(_: list[str]) -> None:
        raise TimeoutError("Timed out waiting for run 'r-timeout'")

    monkeypatch.setattr(cli_main, "app", _raise_timeout)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["run", "wait", "r-timeout"])

    assert int(exc_info.value.code) == 124
    stderr = capsys.readouterr().err
    assert "Timed out waiting for run 'r-timeout'" in stderr
    assert "Traceback" not in stderr
