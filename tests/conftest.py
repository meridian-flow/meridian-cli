"""Shared pytest fixtures for CLI integration checks."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class CliResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@pytest.fixture
def package_root() -> Path:
    return PACKAGE_ROOT


@pytest.fixture(autouse=True)
def _clean_meridian_runtime_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from parent harness runtime state environment."""

    for key in tuple(os.environ):
        if key.startswith("MERIDIAN_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def cli_env(package_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    root = str(package_root / "src")
    env["PYTHONPATH"] = root if not existing else f"{root}:{existing}"
    harness_cmd = " ".join(
        (
            shlex.quote(sys.executable),
            shlex.quote(str(package_root / "tests" / "mock_harness.py")),
            "--duration",
            "0",
        )
    )
    env.setdefault("MERIDIAN_HARNESS_COMMAND", harness_cmd)
    return env


@pytest.fixture
def run_meridian(package_root: Path, cli_env: dict[str, str]) -> Callable[..., CliResult]:
    def _run(args: list[str], timeout: float = 15.0) -> CliResult:
        completed = subprocess.run(
            [sys.executable, "-m", "meridian", *args],
            cwd=package_root,
            env=cli_env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return CliResult(
            args=tuple(args),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    return _run
