"""Smoke test fixtures — CLI runner and auto-markers."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


@dataclass
class CLIResult:
    """Result from a CLI invocation."""

    returncode: int
    stdout: str
    stderr: str

    @property
    def json(self) -> dict[str, Any]:
        """Parse stdout as JSON."""
        return json.loads(self.stdout)

    def assert_success(self) -> CLIResult:
        """Assert command succeeded."""
        assert self.returncode == 0, f"exit {self.returncode}\nstderr: {self.stderr}"
        return self

    def assert_failure(self, code: int | None = None) -> CLIResult:
        """Assert command failed with optional specific exit code."""
        if code is not None:
            assert self.returncode == code, f"expected exit {code}, got {self.returncode}"
        else:
            assert self.returncode != 0, "expected failure, got exit 0"
        return self


def _isolated_env() -> dict[str, str]:
    """Minimal env that strips MERIDIAN_* and forces UTF-8."""
    keep = [
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "TMP",
        "TEMP",
        "HOME",
        "USERPROFILE",
        "LOCALAPPDATA",
    ]
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


REPO_ROOT = Path(__file__).resolve().parents[2]


def _cli_cmd(*args: str, json_mode: bool) -> list[str]:
    cmd = ["uv", "run", "--project", str(REPO_ROOT), "meridian"]
    if json_mode:
        cmd.append("--json")
    cmd.extend(args)
    return cmd


@pytest.fixture
def cli(tmp_path: Path):
    """Fixture that returns a CLI runner bound to an isolated scratch directory.

    No git init — Meridian must work without VCS (core principle #8).
    Tests that need a git repo should use the `cli_with_git` fixture instead.
    """
    scratch = tmp_path / "repo"
    scratch.mkdir()

    base_env = _isolated_env()
    base_env["MERIDIAN_PROJECT_DIR"] = str(scratch)
    base_env["MERIDIAN_HOME"] = str(tmp_path / "home")

    def run(
        *args: str,
        env_override: dict[str, str] | None = None,
        timeout: float = 30.0,
        json_mode: bool = False,
    ) -> CLIResult:
        cmd = _cli_cmd(*args, json_mode=json_mode)
        merged_env = {**base_env, **(env_override or {})}
        proc = subprocess.run(
            cmd,
            cwd=str(scratch),
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CLIResult(
            returncode=proc.returncode,
            stdout=proc.stdout.replace("\r\n", "\n"),
            stderr=proc.stderr.replace("\r\n", "\n"),
        )

    return run


@pytest.fixture
def cli_with_git(tmp_path: Path):
    """CLI runner with git initialized — for tests that need VCS context."""
    scratch = tmp_path / "repo"
    scratch.mkdir()

    # Initialize git repo
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=str(scratch),
        check=True,
        capture_output=True,
    )

    base_env = _isolated_env()
    base_env["MERIDIAN_PROJECT_DIR"] = str(scratch)
    base_env["MERIDIAN_HOME"] = str(tmp_path / "home")

    def run(
        *args: str,
        env_override: dict[str, str] | None = None,
        timeout: float = 30.0,
        json_mode: bool = False,
    ) -> CLIResult:
        cmd = _cli_cmd(*args, json_mode=json_mode)
        merged_env = {**base_env, **(env_override or {})}
        proc = subprocess.run(
            cmd,
            cwd=str(scratch),
            env=merged_env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return CLIResult(
            returncode=proc.returncode,
            stdout=proc.stdout.replace("\r\n", "\n"),
            stderr=proc.stderr.replace("\r\n", "\n"),
        )

    return run


@pytest.fixture
def scratch_dir(tmp_path: Path) -> Path:
    """Return the scratch directory path for tests that need to seed files."""
    scratch = tmp_path / "repo"
    if not scratch.exists():
        scratch.mkdir()
    return scratch


def pytest_configure(config: pytest.Config) -> None:
    """Register smoke marker."""
    config.addinivalue_line("markers", "smoke: CLI subprocess invocations")


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-mark all tests in smoke/ as smoke tests."""
    for item in items:
        if "tests/smoke" in str(item.fspath):
            item.add_marker(pytest.mark.smoke)
