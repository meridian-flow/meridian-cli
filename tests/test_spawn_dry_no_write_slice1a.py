"""Slice 1a no-write regressions for dry-run and skill discovery."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tests.helpers.fixtures import write_skill as _write_skill


def test_spawn_dry_run_auto_creates_space(
    package_root: Path,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)
    env = dict(cli_env)
    env["MERIDIAN_REPO_ROOT"] = repo_root.as_posix()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "meridian",
            "--json",
            "spawn",
            "--dry-run",
            "--prompt",
            "test",
        ],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert completed.returncode == 0
    output = json.loads(completed.stdout)
    assert output["status"] == "dry-run"
    assert "Auto-created space" in output.get("warning", "")
    assert (repo_root / ".meridian").exists()


def test_skills_list_does_not_create_state_dir(
    package_root: Path,
    cli_env: dict[str, str],
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _write_skill(repo_root, "sample", description="sample skill")
    env = dict(cli_env)
    env["MERIDIAN_REPO_ROOT"] = repo_root.as_posix()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "meridian",
            "--json",
            "skills",
            "list",
        ],
        cwd=package_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert any(skill["name"] == "sample" for skill in payload["skills"])
    assert not (repo_root / ".meridian").exists()
