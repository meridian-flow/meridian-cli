"""Token-efficient pytest wrapper tests."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any, cast

from meridian.dev import pytests

if TYPE_CHECKING:
    import pytest


def test_build_pytest_args_defaults() -> None:
    args = pytests.build_pytest_args(["tests/test_cli_spawn_wait_multi.py"], include_last_failed=False)
    assert args == [
        "pytest",
        "-q",
        "--tb=line",
        "--show-capture=no",
        "--disable-warnings",
        "--maxfail=1",
        "-r",
        "fE",
        "--force-short-summary",
        "tests/test_cli_spawn_wait_multi.py",
    ]


def test_build_pytest_args_with_last_failed() -> None:
    args = pytests.build_pytest_args([], include_last_failed=True)
    assert args == [
        "pytest",
        "-q",
        "--tb=line",
        "--show-capture=no",
        "--disable-warnings",
        "--maxfail=1",
        "-r",
        "fE",
        "--force-short-summary",
        "--lf",
        "--lfnf=all",
    ]


def test_main_reads_last_failed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_run(command: list[str], check: bool) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["check"] = check
        return subprocess.CompletedProcess(command, returncode=7)

    monkeypatch.setattr(pytests.subprocess, "run", cast(Any, fake_run))
    monkeypatch.setenv("PYTESTS_LAST_FAILED", "1")

    exit_code = pytests.main(["tests/test_surface_parity.py"])

    assert exit_code == 7
    assert captured["check"] is False
    assert captured["command"] == [
        "pytest",
        "-q",
        "--tb=line",
        "--show-capture=no",
        "--disable-warnings",
        "--maxfail=1",
        "-r",
        "fE",
        "--force-short-summary",
        "--lf",
        "--lfnf=all",
        "tests/test_surface_parity.py",
    ]
