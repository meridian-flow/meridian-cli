"""Test child CWD resolution for managed spawns."""

from pathlib import Path

import pytest

from meridian.lib.core.types import HarnessId
from meridian.lib.launch.cwd import resolve_child_execution_cwd


def test_claude_harness_returns_project_root_under_claudecode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    resolved = resolve_child_execution_cwd(
        project_root=tmp_path,
        spawn_id="r1",
        harness_id=HarnessId.CLAUDE.value,
    )

    assert resolved == tmp_path


def test_non_claude_harness_keeps_project_cwd_under_claudecode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    resolved = resolve_child_execution_cwd(
        project_root=tmp_path,
        spawn_id="r1",
        harness_id=HarnessId.CODEX.value,
    )

    assert resolved == tmp_path


def test_claude_harness_keeps_project_cwd_without_claudecode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDECODE", raising=False)
    resolved = resolve_child_execution_cwd(
        project_root=tmp_path,
        spawn_id="r1",
        harness_id=HarnessId.CLAUDE.value,
    )

    assert resolved == tmp_path
