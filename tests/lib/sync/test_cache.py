from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from meridian.lib.sync import cache
from meridian.lib.sync.cache import (
    SourceResolution,
    cache_dir_for_source,
    cleanup_failed_clone,
    resolve_source,
)
from meridian.lib.sync.config import SyncSourceConfig


def test_resolve_source_local_path_returns_absolute_resolution(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    source_dir = repo_root / "shared-skills"
    source_dir.mkdir(parents=True)

    resolution = resolve_source(
        SyncSourceConfig(name="local", path="./shared-skills"),
        sync_cache_dir=repo_root / ".meridian" / "cache" / "sync",
        repo_root=repo_root,
    )

    assert resolution == SourceResolution(
        source_dir=source_dir.resolve(),
        resolved_commit=None,
        source_type="path",
        source_value="./shared-skills",
    )


def test_resolve_source_local_path_raises_for_missing_directory(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    with pytest.raises(FileNotFoundError, match="Sync source path not found"):
        resolve_source(
            SyncSourceConfig(name="local", path="./missing"),
            sync_cache_dir=repo_root / ".meridian" / "cache" / "sync",
            repo_root=repo_root,
        )


def test_cache_dir_for_source_computes_remote_cache_directory(tmp_path: Path) -> None:
    sync_cache_dir = tmp_path / ".meridian" / "cache" / "sync"

    assert cache_dir_for_source(
        SyncSourceConfig(name="remote", repo="owner/repo"),
        sync_cache_dir,
    ) == sync_cache_dir / "owner-repo"


def test_cache_dir_for_source_returns_configured_local_path(tmp_path: Path) -> None:
    sync_cache_dir = tmp_path / ".meridian" / "cache" / "sync"

    assert cache_dir_for_source(
        SyncSourceConfig(name="local", path="./skills"),
        sync_cache_dir,
    ) == Path("./skills")


def test_cleanup_failed_clone_removes_partial_directory(tmp_path: Path) -> None:
    cache_dir = tmp_path / ".meridian" / "cache" / "sync" / "owner-repo"
    nested = cache_dir / "objects"
    nested.mkdir(parents=True)
    (nested / "partial.pack").write_text("incomplete", encoding="utf-8")

    cleanup_failed_clone(cache_dir)

    assert not cache_dir.exists()


def test_resolve_source_remote_uses_latest_or_locked_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bare_repo = tmp_path / "remote.git"
    worktree = tmp_path / "worktree"
    repo_root = tmp_path / "repo"
    sync_cache_dir = repo_root / ".meridian" / "cache" / "sync"
    repo_root.mkdir()

    _init_remote_repo(bare_repo, worktree)
    first_commit = _commit_file(worktree, "skills/review/SKILL.md", "# Review\n")
    _git(worktree, "push", "--set-upstream", "origin", "main")

    monkeypatch.setattr(cache, "_github_clone_url", lambda repo: bare_repo.as_uri())

    source = SyncSourceConfig(name="remote", repo="owner/repo", ref="main")

    latest = resolve_source(source, sync_cache_dir=sync_cache_dir, repo_root=repo_root)

    assert latest.source_dir == sync_cache_dir / "owner-repo"
    assert latest.resolved_commit == first_commit
    assert latest.source_type == "repo"
    assert latest.source_value == "owner/repo"
    assert (latest.source_dir / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8") == "# Review\n"

    second_commit = _commit_file(worktree, "skills/review/SKILL.md", "# Review\n\nUpdated\n")
    _git(worktree, "push", "origin", "main")

    locked = resolve_source(
        source,
        sync_cache_dir=sync_cache_dir,
        repo_root=repo_root,
        locked_commit=first_commit,
        upgrade=False,
    )
    assert locked.resolved_commit == first_commit
    assert (locked.source_dir / "skills" / "review" / "SKILL.md").read_text(encoding="utf-8") == "# Review\n"

    upgraded = resolve_source(
        source,
        sync_cache_dir=sync_cache_dir,
        repo_root=repo_root,
        locked_commit=first_commit,
        upgrade=True,
    )
    assert upgraded.resolved_commit == second_commit
    assert (
        upgraded.source_dir / "skills" / "review" / "SKILL.md"
    ).read_text(encoding="utf-8") == "# Review\n\nUpdated\n"


def _init_remote_repo(bare_repo: Path, worktree: Path) -> None:
    _git(bare_repo.parent, "init", "--bare", str(bare_repo))
    _git(worktree.parent, "init", "-b", "main", str(worktree))
    _git(worktree, "config", "user.name", "Meridian Tests")
    _git(worktree, "config", "user.email", "tests@example.com")
    _git(worktree, "remote", "add", "origin", bare_repo.as_uri())


def _git(path: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=path,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _commit_file(repo_dir: Path, relative_path: str, content: str) -> str:
    target = repo_dir / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo_dir, "add", relative_path)
    _git(repo_dir, "commit", "-m", f"Update {relative_path}")
    return _git(repo_dir, "rev-parse", "HEAD")
