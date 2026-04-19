from pathlib import Path

import pytest

from meridian.lib.ops.workspace import WorkspaceInitInput, workspace_init_sync


@pytest.fixture(autouse=True)
def _clear_state_root_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MERIDIAN_STATE_ROOT", raising=False)


def _repo(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    return repo_root


def test_workspace_init_creates_template_and_local_gitignore_entry(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    (repo_root / ".git").mkdir()

    first = workspace_init_sync(WorkspaceInitInput(repo_root=repo_root.as_posix()))
    second = workspace_init_sync(WorkspaceInitInput(repo_root=repo_root.as_posix()))

    workspace_path = repo_root / "workspace.local.toml"
    exclude_path = repo_root / ".git" / "info" / "exclude"
    content = workspace_path.read_text(encoding="utf-8")
    exclude_lines = exclude_path.read_text(encoding="utf-8").splitlines()

    assert first.created is True
    assert first.path == workspace_path.as_posix()
    assert first.local_gitignore_path == exclude_path.as_posix()
    assert first.local_gitignore_updated is True
    assert second.created is False
    assert second.local_gitignore_updated is False
    assert "Workspace topology — local-only, gitignored." in content
    assert "workspace.local.toml" in exclude_lines
    assert exclude_lines.count("workspace.local.toml") == 1


def test_workspace_init_resolves_worktree_gitdir_pointer(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    git_dir = tmp_path / "detached-git-dir"
    (git_dir / "info").mkdir(parents=True)
    (repo_root / ".git").write_text(f"gitdir: {git_dir.as_posix()}\n", encoding="utf-8")

    result = workspace_init_sync(WorkspaceInitInput(repo_root=repo_root.as_posix()))

    assert result.local_gitignore_path == (git_dir / "info" / "exclude").as_posix()
    assert (git_dir / "info" / "exclude").read_text(encoding="utf-8").count(
        "workspace.local.toml"
    ) == 1


def test_workspace_init_handles_missing_git_metadata_without_failure(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)

    result = workspace_init_sync(WorkspaceInitInput(repo_root=repo_root.as_posix()))

    assert result.created is True
    assert result.local_gitignore_path is None
    assert result.local_gitignore_updated is False


def test_workspace_init_rejects_non_file_workspace_target(tmp_path: Path) -> None:
    repo_root = _repo(tmp_path)
    (repo_root / "workspace.local.toml").mkdir()

    with pytest.raises(ValueError, match="is not a file"):
        workspace_init_sync(WorkspaceInitInput(repo_root=repo_root.as_posix()))


def test_workspace_init_uses_state_root_parent_for_workspace_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = _repo(tmp_path)
    (repo_root / ".git").mkdir()
    override_root = tmp_path / "state-root" / ".meridian"
    override_root.parent.mkdir(parents=True)
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", override_root.as_posix())

    result = workspace_init_sync(WorkspaceInitInput(repo_root=repo_root.as_posix()))

    expected_workspace_path = override_root.parent / "workspace.local.toml"
    assert result.path == expected_workspace_path.as_posix()
    assert expected_workspace_path.is_file()
