"""CLI integration checks for skills/models commands."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def repo_with_skill(tmp_path: Path) -> Path:
    """Create a minimal repo with one skill for CLI integration tests."""
    skill_dir = tmp_path / ".agents" / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: test-skill\ndescription: A test skill\n---\n\nTest skill body.\n",
        encoding="utf-8",
    )
    (tmp_path / ".meridian").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _spawn_cli(cwd: Path, args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1] / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src if not existing else f"{src}:{existing}"
    return subprocess.run(
        [sys.executable, "-m", "meridian", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def test_skills_cli_commands_work(repo_with_skill: Path) -> None:
    listed = _spawn_cli(repo_with_skill, ["--json", "skills", "list"])
    assert listed.returncode == 0
    listed_payload = json.loads(listed.stdout)
    assert listed_payload["skills"]
    assert any(item["name"] == "test-skill" for item in listed_payload["skills"])

    searched = _spawn_cli(repo_with_skill, ["--json", "skills", "search", "test"])
    assert searched.returncode == 0
    searched_payload = json.loads(searched.stdout)
    assert any(item["name"] == "test-skill" for item in searched_payload["skills"])

    shown = _spawn_cli(repo_with_skill, ["--json", "skills", "show", "test-skill"])
    assert shown.returncode == 0
    shown_payload = json.loads(shown.stdout)
    assert shown_payload["name"] == "test-skill"
    assert "Test skill body" in shown_payload["content"]


def test_models_cli_commands_work(run_meridian) -> None:
    listed = run_meridian(["--json", "models", "list"])
    assert listed.returncode == 0
    listed_payload = json.loads(listed.stdout)
    assert listed_payload["models"]
    assert any(item["model_id"] == "gpt-5.3-codex" for item in listed_payload["models"])

    shown = run_meridian(["--json", "models", "show", "codex"])
    assert shown.returncode == 0
    shown_payload = json.loads(shown.stdout)
    assert shown_payload["model_id"] == "gpt-5.3-codex"
