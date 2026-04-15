"""Test CWD isolation logic for claude child spawns."""

from pathlib import Path

import pytest

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.launch.cwd import resolve_child_execution_cwd
from meridian.lib.state.paths import resolve_spawn_log_dir


def test_claude_harness_flips_to_log_dir_under_claudecode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    resolved = resolve_child_execution_cwd(
        repo_root=tmp_path,
        spawn_id="r1",
        harness_id=HarnessId.CLAUDE.value,
    )

    assert resolved == resolve_spawn_log_dir(tmp_path, SpawnId("r1"))


def test_non_claude_harness_keeps_project_cwd_under_claudecode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDECODE", "1")
    resolved = resolve_child_execution_cwd(
        repo_root=tmp_path,
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
        repo_root=tmp_path,
        spawn_id="r1",
        harness_id=HarnessId.CLAUDE.value,
    )

    assert resolved == tmp_path
