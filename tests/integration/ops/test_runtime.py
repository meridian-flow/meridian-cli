from pathlib import Path

import pytest

from meridian.lib.ops.runtime import resolve_state_root
from meridian.lib.state.paths import resolve_spawn_log_dir


@pytest.fixture(autouse=True)
def _clear_state_root_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_STATE_ROOT", raising=False)


def test_resolve_state_root_honors_state_root_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    override_root = tmp_path / "override-state" / ".meridian"
    repo_root.mkdir()
    override_root.parent.mkdir(parents=True)
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", override_root.as_posix())

    assert resolve_state_root(repo_root) == override_root


def test_spawn_bookkeeping_and_artifact_paths_share_override_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    override_root = tmp_path / "override-state" / ".meridian"
    repo_root.mkdir()
    override_root.parent.mkdir(parents=True)
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", override_root.as_posix())

    state_root = resolve_state_root(repo_root)
    log_dir = resolve_spawn_log_dir(repo_root, "p1")

    assert state_root == override_root
    assert log_dir == override_root / "spawns" / "p1"
