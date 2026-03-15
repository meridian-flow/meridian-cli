"""Adapter seams for managed source kinds."""

from __future__ import annotations

import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Protocol, cast
from urllib import parse, request

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.install.config import SourceConfig
from meridian.lib.install.discovery import DiscoveredItem, discover_items
from meridian.lib.install.types import SourceKind


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
        source: SourceConfig,
        *,
        cache_dir: Path,
        repo_root: Path,
        locked_identity: dict[str, object] | None = None,
        upgrade: bool = False,
    ) -> ResolvedSource: ...

    def fetch(self, resolved: ResolvedSource) -> Path: ...

    def describe(self, tree_path: Path) -> tuple[DiscoveredItem, ...]: ...


class GitSourceAdapter:
    """Adapter for git-backed sources."""

    kind: SourceKind = "git"

    def resolve(
        self,
        source: SourceConfig,
        *,
        cache_dir: Path,
        repo_root: Path,
        locked_identity: dict[str, object] | None = None,
        upgrade: bool = False,
    ) -> ResolvedSource:
        _ = repo_root
        if source.url is None:
            raise ValueError("Git source resolution requires 'url'.")

        if not _git_cli_available():
            return _resolve_git_source_without_cli(
                source=source,
                cache_dir=cache_dir,
                locked_identity=locked_identity,
                upgrade=upgrade,
            )

        cache_path = _git_clone_cache_path(cache_dir, source.name)
        _ensure_git_clone_cache(cache_path, source.url)

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

    def describe(self, tree_path: Path) -> tuple[DiscoveredItem, ...]:
        return discover_items(tree_path)


class PathSourceAdapter:
    """Adapter for local path sources."""

    kind: SourceKind = "path"

    def resolve(
        self,
        source: SourceConfig,
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
        if not tree_path.exists():
            raise FileNotFoundError(f"Managed path source does not exist: {tree_path}")
        if not tree_path.is_dir():
            raise ValueError(f"Managed path source is not a directory: {tree_path}")
        return ResolvedSource(
            source_name=source.name,
            kind="path",
            locator=source.path,
            tree_path=tree_path.resolve(),
            resolved_identity={"path": source.path},
        )

    def fetch(self, resolved: ResolvedSource) -> Path:
        return resolved.tree_path

    def describe(self, tree_path: Path) -> tuple[DiscoveredItem, ...]:
        return discover_items(tree_path)


def default_adapters() -> dict[SourceKind, SourceAdapter]:
    """Return the default adapter registry."""

    return {
        "git": GitSourceAdapter(),
        "path": PathSourceAdapter(),
    }


def _git_clone_cache_path(cache_dir: Path, source_name: str) -> Path:
    return cache_dir / "git" / source_name


def _git_archive_cache_path(cache_dir: Path, source_name: str) -> Path:
    return cache_dir / "archive" / source_name


def _ensure_git_clone_cache(cache_path: Path, source_url: str) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        if not (cache_path / ".git").is_dir():
            shutil.rmtree(cache_path, ignore_errors=True)
        else:
            remote_url = _git_remote_url(cache_path)
            if remote_url != source_url:
                shutil.rmtree(cache_path, ignore_errors=True)

    if cache_path.exists():
        return

    try:
        _run_git(["clone", source_url, str(cache_path)])
    except Exception:
        shutil.rmtree(cache_path, ignore_errors=True)
        raise


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


def _git_cli_available() -> bool:
    return shutil.which("git") is not None


def _git_remote_url(cache_path: Path) -> str:
    return _run_git(["config", "--get", "remote.origin.url"], cwd=cache_path).stdout.strip()


def _resolve_git_source_without_cli(
    *,
    source: SourceConfig,
    cache_dir: Path,
    locked_identity: dict[str, object] | None,
    upgrade: bool,
) -> ResolvedSource:
    if source.url is None:
        raise ValueError("Git source resolution requires 'url'.")

    owner_repo = _parse_github_repo(source.url)
    if owner_repo is None:
        raise RuntimeError(
            "Managed git sources require the 'git' binary unless "
            "the source is a public GitHub repo."
        )

    owner, repo = owner_repo
    if not upgrade and locked_identity is not None:
        locked_commit = locked_identity.get("commit")
        if not isinstance(locked_commit, str) or not locked_commit.strip():
            raise ValueError("Locked git sources require a string 'commit' identity.")
        commit = locked_commit
    else:
        commit = _resolve_github_commit(owner, repo, source.ref)

    cache_path = _git_archive_cache_path(cache_dir, source.name)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    _populate_github_archive_cache(owner, repo, commit, cache_path)
    return ResolvedSource(
        source_name=source.name,
        kind="git",
        locator=source.url,
        requested_ref=source.ref,
        resolved_identity={"commit": commit},
        tree_path=cache_path,
    )


def _parse_github_repo(url: str) -> tuple[str, str] | None:
    parsed = parse.urlparse(url)
    if parsed.scheme not in {"https", "http"}:
        return None
    if parsed.netloc.lower() != "github.com":
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return None
    owner = parts[0]
    repo = parts[1]
    if repo.endswith(".git"):
        repo = repo[:-4]
    if not owner or not repo:
        return None
    return owner, repo


def _resolve_github_commit(owner: str, repo: str, ref: str | None) -> str:
    selected_ref = ref or _github_default_branch(owner, repo)
    payload = _read_github_json(
        f"https://api.github.com/repos/{owner}/{repo}/commits/{selected_ref}"
    )
    commit = payload.get("sha")
    if not isinstance(commit, str) or not commit.strip():
        raise RuntimeError(f"Could not resolve GitHub commit for {owner}/{repo}@{selected_ref}.")
    return commit


def _github_default_branch(owner: str, repo: str) -> str:
    payload = _read_github_json(f"https://api.github.com/repos/{owner}/{repo}")
    default_branch = payload.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch.strip():
        raise RuntimeError(f"Could not resolve default branch for GitHub repo {owner}/{repo}.")
    return default_branch


def _read_github_json(url: str) -> dict[str, object]:
    req = request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "meridian-channel",
        },
    )
    with request.urlopen(req) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected GitHub API payload from {url}.")
    return cast("dict[str, object]", payload)


def _populate_github_archive_cache(owner: str, repo: str, commit: str, cache_path: Path) -> None:
    archive_url = f"https://api.github.com/repos/{owner}/{repo}/tarball/{commit}"
    with tempfile.TemporaryDirectory(prefix="meridian-github-", dir=cache_path.parent) as tmp_dir:
        tmp_root = Path(tmp_dir)
        archive_path = tmp_root / "source.tar.gz"
        extract_root = tmp_root / "extract"
        extract_root.mkdir(parents=True, exist_ok=True)
        _download_to_path(archive_url, archive_path)
        with tarfile.open(archive_path, mode="r:gz") as archive:
            _extract_tar_safely(archive, extract_root)
        extracted_root = _single_extracted_root(extract_root)
        shutil.rmtree(cache_path, ignore_errors=True)
        shutil.move(str(extracted_root), str(cache_path))


def _download_to_path(url: str, destination: Path) -> None:
    req = request.Request(url, headers={"User-Agent": "meridian-channel"})
    with request.urlopen(req) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _extract_tar_safely(archive: tarfile.TarFile, destination: Path) -> None:
    for member in archive.getmembers():
        member_path = Path(member.name)
        if member_path.is_absolute() or ".." in member_path.parts:
            raise RuntimeError(f"Refusing to extract unsafe archive path: {member.name}")
    archive.extractall(destination)


def _single_extracted_root(extract_root: Path) -> Path:
    children = [child for child in extract_root.iterdir()]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return extract_root
