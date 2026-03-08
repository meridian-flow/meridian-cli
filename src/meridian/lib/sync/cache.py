"""Source resolution and cache management for sync sources."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from meridian.lib.sync.config import SyncSourceConfig


class SourceResolution(BaseModel):
    """Resolved source location for one sync source."""

    model_config = ConfigDict(frozen=True)

    source_dir: Path
    resolved_commit: str | None
    source_type: Literal["repo", "path"]
    source_value: str


def cache_dir_for_source(source: SyncSourceConfig, sync_cache_dir: Path) -> Path:
    """Return the cache location for a sync source."""

    if source.repo is not None:
        return sync_cache_dir / source.repo.replace("/", "-")
    if source.path is None:
        raise ValueError("Sync source must define either 'repo' or 'path'.")
    return Path(source.path)


def cleanup_failed_clone(cache_dir: Path) -> None:
    """Remove a partially cloned cache directory."""

    shutil.rmtree(cache_dir, ignore_errors=True)


def resolve_source(
    source: SyncSourceConfig,
    *,
    sync_cache_dir: Path,
    repo_root: Path,
    locked_commit: str | None = None,
    upgrade: bool = False,
) -> SourceResolution:
    """Resolve a sync source to a local directory and commit."""

    if source.repo is not None:
        cache_dir = cache_dir_for_source(source, sync_cache_dir)
        clone_url = _github_clone_url(source.repo)
        should_resolve_upstream = upgrade or locked_commit is None

        if not cache_dir.exists():
            sync_cache_dir.mkdir(parents=True, exist_ok=True)
            try:
                _run_git(["clone", clone_url, str(cache_dir)])
            except Exception:
                cleanup_failed_clone(cache_dir)
                raise

        if should_resolve_upstream:
            _checkout_resolved_ref(cache_dir, source.ref)
        else:
            if locked_commit is None:
                raise ValueError("locked_commit is required when upgrade is false.")
            _run_git(["fetch", "origin"], cwd=cache_dir)
            _run_git(["checkout", locked_commit], cwd=cache_dir)

        resolved_commit = _run_git(
            ["rev-parse", "HEAD"],
            cwd=cache_dir,
        ).stdout.strip()

        return SourceResolution(
            source_dir=cache_dir,
            resolved_commit=resolved_commit,
            source_type="repo",
            source_value=source.repo,
        )

    if source.path is None:
        raise ValueError("Sync source must define either 'repo' or 'path'.")

    configured_path = Path(source.path).expanduser()
    resolved_path = configured_path if configured_path.is_absolute() else repo_root / configured_path
    resolved_path = resolved_path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Sync source path not found: {source.path}")

    return SourceResolution(
        source_dir=resolved_path,
        resolved_commit=None,
        source_type="path",
        source_value=source.path,
    )


def _checkout_resolved_ref(cache_dir: Path, ref: str | None) -> None:
    if ref is None:
        _run_git(["fetch", "origin"], cwd=cache_dir)
        _run_git(["checkout", "origin/HEAD"], cwd=cache_dir)
        return

    if _ref_exists(cache_dir, "--heads", ref):
        _run_git(["fetch", "origin", ref], cwd=cache_dir)
        _run_git(["checkout", "FETCH_HEAD"], cwd=cache_dir)
        return

    if _ref_exists(cache_dir, "--tags", ref):
        _run_git(["fetch", "origin", "tag", ref], cwd=cache_dir)
        _run_git(["checkout", f"tags/{ref}"], cwd=cache_dir)
        return

    raise RuntimeError(f"Remote ref not found for source cache checkout: {ref}")


def _ref_exists(cache_dir: Path, flag: str, ref: str) -> bool:
    completed = subprocess.run(
        ["git", "ls-remote", "--exit-code", flag, "origin", ref],
        cwd=cache_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _github_clone_url(repo: str) -> str:
    return f"https://github.com/{repo}.git"


def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "git command failed"
        raise RuntimeError(f"git {' '.join(args)} failed: {message}")
    return completed
