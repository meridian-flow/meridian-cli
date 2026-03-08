"""Filesystem path helpers for file-authoritative Meridian state."""


import os
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.types import SpawnId

_MERIDIAN_DIR = ".meridian"
_GITIGNORE_CONTENT = (
    "# Ignore everything by default\n"
    "*\n"
    "\n"
    "# Track .gitignore itself\n"
    "!.gitignore\n"
    "\n"
    "# Track fs/ and work/\n"
    "!fs/\n"
    "!fs/**\n"
    "!work/\n"
    "!work/**\n"
)


class SpacePaths(BaseModel):
    """Resolved paths for one Meridian state root."""

    model_config = ConfigDict(frozen=True)

    space_dir: Path
    spawns_jsonl: Path
    spawns_lock: Path
    sessions_jsonl: Path
    sessions_lock: Path
    sessions_dir: Path
    fs_dir: Path
    spawns_dir: Path

    @classmethod
    def from_space_dir(cls, space_dir: Path) -> Self:
        """Build state-root-relative paths from an absolute state directory."""

        return cls(
            space_dir=space_dir,
            spawns_jsonl=space_dir / "spawns.jsonl",
            spawns_lock=space_dir / "spawns.lock",
            sessions_jsonl=space_dir / "sessions.jsonl",
            sessions_lock=space_dir / "sessions.lock",
            sessions_dir=space_dir / "sessions",
            fs_dir=space_dir / "fs",
            spawns_dir=space_dir / "spawns",
        )


class StatePaths(BaseModel):
    """Resolved on-disk Meridian state paths."""

    model_config = ConfigDict(frozen=True)

    root_dir: Path
    artifacts_dir: Path
    spawns_dir: Path
    active_primary_lock: Path
    cache_dir: Path
    sync_lock_path: Path
    sync_cache_dir: Path
    config_path: Path
    models_path: Path


def _resolve_state_root(repo_root: Path) -> Path:
    """Resolve state root from env override or default `.meridian` location."""

    override = os.getenv("MERIDIAN_STATE_ROOT", "").strip()
    if not override:
        return repo_root / _MERIDIAN_DIR

    candidate = Path(override).expanduser()
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def resolve_state_paths(repo_root: Path) -> StatePaths:
    """Resolve all state paths rooted under `.meridian/`."""

    root_dir = _resolve_state_root(repo_root)
    return StatePaths(
        root_dir=root_dir,
        artifacts_dir=root_dir / "artifacts",
        spawns_dir=root_dir / "spawns",
        active_primary_lock=root_dir / "active-primary.lock",
        cache_dir=root_dir / "cache",
        sync_lock_path=root_dir / "sync.lock",
        sync_cache_dir=root_dir / "cache" / "sync",
        config_path=root_dir / "config.toml",
        models_path=root_dir / "models.toml",
    )


def resolve_cache_dir(repo_root: Path) -> Path:
    """Return `.meridian/cache/` for a repository root."""

    return resolve_state_paths(repo_root).cache_dir


def resolve_all_spaces_dir(repo_root: Path) -> Path:
    """Return the compatibility `.meridian/.spaces/` directory path."""

    return resolve_state_paths(repo_root).root_dir / ".spaces"


def resolve_space_dir(repo_root: Path, space_id: str) -> Path:
    """Return the compatibility state root path for a space lookup."""

    del space_id
    return resolve_state_paths(repo_root).root_dir


def resolve_fs_dir(repo_root: Path) -> Path:
    """Return `.meridian/fs/` for a repository root."""

    return resolve_state_paths(repo_root).root_dir / "fs"


def spawn_log_subpath(spawn_id: SpawnId | str) -> Path:
    """Return spawn log path relative to the Meridian state root."""

    return Path("spawns") / str(spawn_id)


def resolve_spawn_log_dir(repo_root: Path, spawn_id: SpawnId | str) -> Path:
    """Resolve absolute spawn log directory for a spawn ID."""

    return resolve_state_paths(repo_root).root_dir / spawn_log_subpath(spawn_id)


def ensure_gitignore(repo_root: Path) -> Path:
    """Seed `.meridian/.gitignore` on first init. Never overwrites user edits."""

    meridian_dir = repo_root / _MERIDIAN_DIR
    meridian_dir.mkdir(parents=True, exist_ok=True)
    gitignore_path = meridian_dir / ".gitignore"

    if gitignore_path.exists():
        return gitignore_path

    tmp_path = meridian_dir / ".gitignore.tmp"
    with tmp_path.open("w", encoding="utf-8") as handle:
        handle.write(_GITIGNORE_CONTENT)
    os.replace(tmp_path, gitignore_path)
    return gitignore_path
