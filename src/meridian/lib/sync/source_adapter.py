"""Adapter seams for managed source kinds."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.sync.install_config import ManagedSourceConfig
from meridian.lib.sync.install_types import SourceKind
from meridian.lib.sync.source_tree import ExportedSourceItem, discover_source_items


class ResolvedSource(BaseModel):
    """Resolved source metadata plus a local tree path."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    kind: SourceKind
    locator: str
    requested_ref: str | None = None
    resolved_identity: dict[str, object] = Field(default_factory=dict)
    tree_path: Path


class SourceAdapter(Protocol):
    """Small adapter interface for one managed source kind."""

    kind: SourceKind

    def resolve(
        self,
        source: ManagedSourceConfig,
        *,
        cache_dir: Path,
        repo_root: Path,
        locked_identity: dict[str, object] | None = None,
        upgrade: bool = False,
    ) -> ResolvedSource: ...

    def fetch(self, resolved: ResolvedSource) -> Path: ...

    def describe(self, tree_path: Path) -> tuple[ExportedSourceItem, ...]: ...


class GitSourceAdapter:
    """Adapter for git-backed sources."""

    kind: SourceKind = "git"

    def resolve(
        self,
        source: ManagedSourceConfig,
        *,
        cache_dir: Path,
        repo_root: Path,
        locked_identity: dict[str, object] | None = None,
        upgrade: bool = False,
    ) -> ResolvedSource:
        _ = repo_root
        if source.url is None:
            raise ValueError("Git source resolution requires 'url'.")

        cache_path = cache_dir / source.name
        if not cache_path.exists():
            cache_dir.mkdir(parents=True, exist_ok=True)
            try:
                _run_git(["clone", source.url, str(cache_path)])
            except Exception:
                shutil.rmtree(cache_path, ignore_errors=True)
                raise

        if not upgrade and locked_identity is not None:
            locked_commit = locked_identity.get("commit")
            if not isinstance(locked_commit, str) or not locked_commit.strip():
                raise ValueError("Locked git sources require a string 'commit' identity.")
            _run_git(["fetch", "--tags", "origin"], cwd=cache_path)
            _run_git(["checkout", "--detach", locked_commit], cwd=cache_path)
        else:
            _checkout_git_ref(cache_path, source.ref)

        commit = _run_git(["rev-parse", "HEAD"], cwd=cache_path).stdout.strip()
        return ResolvedSource(
            source_name=source.name,
            kind="git",
            locator=source.url,
            requested_ref=source.ref,
            resolved_identity={"commit": commit},
            tree_path=cache_path,
        )

    def fetch(self, resolved: ResolvedSource) -> Path:
        return resolved.tree_path

    def describe(self, tree_path: Path) -> tuple[ExportedSourceItem, ...]:
        return discover_source_items(tree_path)


class PathSourceAdapter:
    """Adapter for local path sources."""

    kind: SourceKind = "path"

    def resolve(
        self,
        source: ManagedSourceConfig,
        *,
        cache_dir: Path,
        repo_root: Path,
        locked_identity: dict[str, object] | None = None,
        upgrade: bool = False,
    ) -> ResolvedSource:
        _ = cache_dir
        _ = locked_identity
        _ = upgrade
        if source.path is None:
            raise ValueError("Path source resolution requires 'path'.")

        configured = Path(source.path).expanduser()
        tree_path = configured if configured.is_absolute() else repo_root / configured
        return ResolvedSource(
            source_name=source.name,
            kind="path",
            locator=source.path,
            tree_path=tree_path.resolve(),
            resolved_identity={"path": source.path},
        )

    def fetch(self, resolved: ResolvedSource) -> Path:
        return resolved.tree_path

    def describe(self, tree_path: Path) -> tuple[ExportedSourceItem, ...]:
        return discover_source_items(tree_path)


def default_source_adapters() -> dict[SourceKind, SourceAdapter]:
    """Return the default adapter registry."""

    return {
        "git": GitSourceAdapter(),
        "path": PathSourceAdapter(),
    }


def _checkout_git_ref(cache_path: Path, ref: str | None) -> None:
    _run_git(["fetch", "--tags", "origin"], cwd=cache_path)
    if ref is None:
        try:
            head_ref = _run_git(
                ["symbolic-ref", "--quiet", "refs/remotes/origin/HEAD"],
                cwd=cache_path,
            ).stdout.strip()
            _run_git(["checkout", "--detach", head_ref], cwd=cache_path)
            return
        except RuntimeError:
            _run_git(["checkout", "--detach", "HEAD"], cwd=cache_path)
            return

    candidates = (f"origin/{ref}", f"refs/tags/{ref}", ref)
    for candidate in candidates:
        completed = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", candidate],
            cwd=cache_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            _run_git(["checkout", "--detach", candidate], cwd=cache_path)
            return

    try:
        _run_git(["fetch", "origin", ref], cwd=cache_path)
        _run_git(["checkout", "--detach", "FETCH_HEAD"], cwd=cache_path)
        return
    except RuntimeError:
        pass

    raise RuntimeError(f"Remote ref not found for managed git source: {ref}")


def _run_git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
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
