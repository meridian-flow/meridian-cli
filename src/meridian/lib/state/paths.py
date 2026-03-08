"""Filesystem path helpers for file-authoritative Meridian state."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.types import SpawnId, SpaceId

_MERIDIAN_DIR = ".meridian"
_SPACES_DIR = ".spaces"
_GITIGNORE_CONTENT = (
    ".spaces/**\n"
    "!.spaces/*/\n"
    "!.spaces/*/fs/\n"
    "!.spaces/*/fs/**\n"
)


class SpacePaths(BaseModel):
    """Resolved paths for one space directory."""

    model_config = ConfigDict(frozen=True)

    space_dir: Path
    space_json: Path
    space_lock: Path
    spawns_jsonl: Path
    spawns_lock: Path
    sessions_jsonl: Path
    sessions_lock: Path
    sessions_dir: Path
    fs_dir: Path
    spawns_dir: Path

    @classmethod
    def from_space_dir(cls, space_dir: Path) -> SpacePaths:
        """Build space-relative paths from an absolute space directory."""

        return cls(
            space_dir=space_dir,
            space_json=space_dir / "space.json",
            space_lock=space_dir / "space.lock",
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
    all_spaces_dir: Path
    active_spaces_dir: Path
    cache_dir: Path
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
        all_spaces_dir=root_dir / _SPACES_DIR,
        active_spaces_dir=root_dir / "active-spaces",
        cache_dir=root_dir / "cache",
        config_path=root_dir / "config.toml",
        models_path=root_dir / "models.toml",
    )


def resolve_all_spaces_dir(repo_root: Path) -> Path:
    """Return `.meridian/.spaces/` for a repository root."""

    return resolve_state_paths(repo_root).all_spaces_dir


def resolve_cache_dir(repo_root: Path) -> Path:
    """Return `.meridian/cache/` for a repository root."""

    return resolve_state_paths(repo_root).cache_dir


def resolve_space_dir(repo_root: Path, space_id: SpaceId | str) -> Path:
    """Return `.meridian/.spaces/<space-id>/` for a repository root."""

    return resolve_all_spaces_dir(repo_root) / str(space_id)


def spawn_log_subpath(spawn_id: SpawnId | str, space_id: SpaceId | str | None) -> Path:
    """Return spawn log path relative to the Meridian state root."""

    if space_id is None:
        return Path("spawns") / str(spawn_id)
    return Path(_SPACES_DIR) / str(space_id) / "spawns" / str(spawn_id)


def resolve_spawn_log_dir(
    repo_root: Path, spawn_id: SpawnId | str, space_id: SpaceId | str | None
) -> Path:
    """Resolve absolute spawn log directory for spawn/space IDs."""

    return resolve_state_paths(repo_root).root_dir / spawn_log_subpath(spawn_id, space_id)


def ensure_gitignore(repo_root: Path) -> Path:
    """Create `.meridian/.gitignore` with file-authority ignore rules."""

    meridian_dir = repo_root / _MERIDIAN_DIR
    meridian_dir.mkdir(parents=True, exist_ok=True)
    gitignore_path = meridian_dir / ".gitignore"

    if gitignore_path.exists():
        current = gitignore_path.read_text(encoding="utf-8")
        if current == _GITIGNORE_CONTENT:
            return gitignore_path

    tmp_path = meridian_dir / ".gitignore.tmp"
    with tmp_path.open("w", encoding="utf-8") as handle:
        handle.write(_GITIGNORE_CONTENT)
    os.replace(tmp_path, gitignore_path)
    return gitignore_path
