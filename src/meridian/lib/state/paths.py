"""Filesystem path helpers for file-authoritative Meridian state."""

import os
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.types import SpawnId
from meridian.lib.state.atomic import atomic_write_text

_MERIDIAN_DIR = ".meridian"
_GITIGNORE_CONTENT = (
    "# Ignore everything by default\n"
    "*\n"
    "\n"
    "# Track .gitignore itself\n"
    "!.gitignore\n"
    "\n"
    "# Track shared install manifest and lock\n"
    "!agents.toml\n"
    "!agents.lock\n"
    "\n"
    "# Track shared repo state\n"
    "!fs/\n"
    "!fs/**\n"
    "!work-items/\n"
    "!work-items/**\n"
    "!work/\n"
    "!work/**\n"
    "!work-archive/\n"
    "!work-archive/**\n"
)


class StateRootPaths(BaseModel):
    """Resolved paths for one Meridian state root."""

    model_config = ConfigDict(frozen=True)

    root_dir: Path
    spawns_jsonl: Path
    spawns_flock: Path
    sessions_jsonl: Path
    sessions_flock: Path
    session_id_counter: Path
    session_id_counter_flock: Path
    sessions_dir: Path
    fs_dir: Path
    work_dir: Path
    work_archive_dir: Path
    work_items_dir: Path
    work_items_flock: Path
    work_items_rename_intent: Path
    spawns_dir: Path

    @classmethod
    def from_root_dir(cls, root_dir: Path) -> Self:
        """Build state-root-relative paths from an absolute state directory."""

        return cls(
            root_dir=root_dir,
            spawns_jsonl=root_dir / "spawns.jsonl",
            spawns_flock=root_dir / "spawns.jsonl.flock",
            sessions_jsonl=root_dir / "sessions.jsonl",
            sessions_flock=root_dir / "sessions.jsonl.flock",
            session_id_counter=root_dir / "session-id-counter",
            session_id_counter_flock=root_dir / "session-id-counter.flock",
            sessions_dir=root_dir / "sessions",
            fs_dir=root_dir / "fs",
            work_dir=root_dir / "work",
            work_archive_dir=root_dir / "work-archive",
            work_items_dir=root_dir / "work-items",
            work_items_flock=root_dir / "work-items.flock",
            work_items_rename_intent=root_dir / "work-items.rename.intent.json",
            spawns_dir=root_dir / "spawns",
        )


class StatePaths(BaseModel):
    """Resolved on-disk Meridian state paths."""

    model_config = ConfigDict(frozen=True)

    root_dir: Path
    artifacts_dir: Path
    spawns_dir: Path
    cache_dir: Path
    agents_manifest_path: Path
    agents_local_manifest_path: Path
    agents_lock_path: Path
    agents_cache_dir: Path
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
        cache_dir=root_dir / "cache",
        agents_manifest_path=root_dir / "agents.toml",
        agents_local_manifest_path=root_dir / "agents.local.toml",
        agents_lock_path=root_dir / "agents.lock",
        agents_cache_dir=root_dir / "cache" / "agents",
        config_path=root_dir / "config.toml",
        models_path=root_dir / "models.toml",
    )


def resolve_cache_dir(repo_root: Path) -> Path:
    """Return `.meridian/cache/` for a repository root."""

    return resolve_state_paths(repo_root).cache_dir


def resolve_fs_dir(repo_root: Path) -> Path:
    """Return `.meridian/fs/` for a repository root."""

    return resolve_state_paths(repo_root).root_dir / "fs"


def resolve_work_dir(repo_root: Path) -> Path:
    """Return `.meridian/work/` for a repository root."""

    return resolve_state_paths(repo_root).root_dir / "work"


def resolve_work_archive_dir(repo_root: Path) -> Path:
    """Return `.meridian/work-archive/` for a repository root."""

    return resolve_state_paths(repo_root).root_dir / "work-archive"


def resolve_work_items_dir(repo_root: Path) -> Path:
    """Return `.meridian/work-items/` for a repository root."""

    return resolve_state_paths(repo_root).root_dir / "work-items"


def resolve_work_scratch_dir(state_root: Path, work_id: str) -> Path:
    """Return the work-scoped scratch directory for a work item."""

    return StateRootPaths.from_root_dir(state_root).work_dir / work_id


def resolve_work_archive_scratch_dir(state_root: Path, work_id: str) -> Path:
    """Return the archived work-scoped scratch directory for a work item."""

    return StateRootPaths.from_root_dir(state_root).work_archive_dir / work_id


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

    atomic_write_text(gitignore_path, _GITIGNORE_CONTENT)
    return gitignore_path
