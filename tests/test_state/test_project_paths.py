from pathlib import Path

import pytest
from pydantic import ValidationError

from meridian.lib.config.project_paths import (
    PROJECT_ROOT_IGNORE_TARGETS,
    ProjectPaths,
    resolve_project_paths,
)


@pytest.fixture(autouse=True)
def _clear_state_root_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_STATE_ROOT", raising=False)


def test_project_paths_is_frozen(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    paths = ProjectPaths(repo_root=repo_root.resolve(), execution_cwd=repo_root.resolve())

    with pytest.raises(ValidationError, match="frozen"):
        paths.repo_root = tmp_path


def test_resolve_project_paths_resolves_repo_root_and_execution_cwd(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    execution_cwd = tmp_path / "exec"
    repo_root.mkdir()
    execution_cwd.mkdir()

    paths = resolve_project_paths(repo_root=repo_root, execution_cwd=execution_cwd)

    assert paths.repo_root == repo_root.resolve()
    assert paths.execution_cwd == execution_cwd.resolve()


def test_resolve_project_paths_defaults_execution_cwd_to_repo_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    paths = resolve_project_paths(repo_root=repo_root)

    assert paths.repo_root == repo_root.resolve()
    assert paths.execution_cwd == repo_root.resolve()


def test_project_paths_exposes_root_file_policy(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    paths = resolve_project_paths(repo_root=repo_root)

    assert paths.meridian_toml == repo_root.resolve() / "meridian.toml"
    assert paths.workspace_local_toml == repo_root.resolve() / "workspace.local.toml"
    assert paths.workspace_ignore_targets == PROJECT_ROOT_IGNORE_TARGETS


def test_project_paths_workspace_local_toml_uses_state_root_parent_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    override_root = tmp_path / "custom-state" / ".meridian"
    repo_root.mkdir()
    override_root.parent.mkdir(parents=True)
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", override_root.as_posix())

    paths = resolve_project_paths(repo_root=repo_root)

    assert paths.workspace_local_toml == override_root.parent / "workspace.local.toml"
