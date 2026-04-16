from pathlib import Path

import pytest
from pydantic import ValidationError

from meridian.lib.state.paths import ProjectPaths, resolve_project_paths


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
