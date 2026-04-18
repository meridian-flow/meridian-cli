"""Filesystem path helpers for file-authoritative Meridian state."""

import os
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.types import SpawnId
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.user_paths import get_or_create_project_uuid, get_project_state_root

_MERIDIAN_DIR = ".meridian"
_GITIGNORE_CONTENT = (
    "# Ignore everything by default\n"
    "*\n"
    "\n"
    "# Track .gitignore itself\n"
    "!.gitignore\n"
    "\n"
    "# Ignore the project UUID\n"
    "id\n"
    "\n"
    "# Track shared repo state\n"
    "!fs/\n"
    "!fs/**\n"
    "!work/\n"
    "!work/**\n"
    "!work-archive/\n"
    "!work-archive/**\n"
)
_REQUIRED_GITIGNORE_LINES = (
    "!.gitignore",
    "!fs/",
    "!fs/**",
    "!work/",
    "!work/**",
    "!work-archive/",
    "!work-archive/**",
)
_DEPRECATED_GITIGNORE_LINES = (
    "!work-items/",
    "!work-items/**",
    "!agents.toml",
    "!agents.lock",
    "!config.toml",
)


class StateRootPaths(BaseModel):
    """Resolved runtime paths for one Meridian state root.

    This object models runtime state roots (spawn/session indexes and per-spawn
    artifacts). Legacy work-item path fields are still present for transitional
    callers and will be removed when all work-store callers move to repo paths.
    """

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
    """Resolved on-disk Meridian repo state paths."""

    model_config = ConfigDict(frozen=True)

    root_dir: Path
    id_file: Path
    fs_dir: Path
    work_dir: Path
    work_archive_dir: Path

    @classmethod
    def from_root_dir(cls, root_dir: Path) -> Self:
        """Build repo-state-relative paths from one state directory."""

        return cls(
            root_dir=root_dir,
            id_file=root_dir / "id",
            fs_dir=root_dir / "fs",
            work_dir=root_dir / "work",
            work_archive_dir=root_dir / "work-archive",
        )


def _resolve_state_root(repo_root: Path) -> Path:
    """Resolve state root from env override or default `.meridian` location."""

    override = os.getenv("MERIDIAN_STATE_ROOT", "").strip()
    if not override:
        return repo_root / _MERIDIAN_DIR

    candidate = Path(override).expanduser()
    if candidate.is_absolute():
        return candidate
    return repo_root / candidate


def resolve_repo_state_paths(repo_root: Path) -> StatePaths:
    """Resolve repo-owned `.meridian/` paths only (ignores runtime overrides)."""

    return StatePaths.from_root_dir(repo_root / _MERIDIAN_DIR)


def resolve_state_paths(repo_root: Path) -> StatePaths:
    """Resolve all state paths rooted under `.meridian/`."""

    root_dir = _resolve_state_root(repo_root)
    return StatePaths.from_root_dir(root_dir)


def resolve_runtime_state_root(repo_root: Path) -> Path:
    """Resolve runtime state root (spawns/sessions/cache) for a repository."""

    override = os.getenv("MERIDIAN_STATE_ROOT", "").strip()
    if override:
        candidate = Path(override).expanduser()
        return candidate if candidate.is_absolute() else repo_root / candidate

    project_uuid = get_or_create_project_uuid(resolve_repo_state_paths(repo_root).root_dir)
    return get_project_state_root(project_uuid)


def resolve_cache_dir(repo_root: Path) -> Path:
    """Return runtime cache directory for a repository root."""

    return resolve_runtime_state_root(repo_root) / "cache"


def resolve_fs_dir(repo_root: Path) -> Path:
    """Return `.meridian/fs/` for a repository root."""

    return resolve_repo_state_paths(repo_root).fs_dir


def resolve_work_scratch_dir(state_root: Path, work_id: str) -> Path:
    """Return the work-scoped scratch directory for a work item."""

    return StateRootPaths.from_root_dir(state_root).work_dir / work_id


def spawn_log_subpath(spawn_id: SpawnId | str) -> Path:
    """Return spawn log path relative to the Meridian state root."""

    return Path("spawns") / str(spawn_id)


def resolve_spawn_log_dir(repo_root: Path, spawn_id: SpawnId | str) -> Path:
    """Resolve absolute spawn log directory for a spawn ID."""

    return resolve_runtime_state_root(repo_root) / spawn_log_subpath(spawn_id)


def heartbeat_path(state_root: Path, spawn_id: SpawnId | str) -> Path:
    """Return heartbeat sentinel path for a spawn under a state root."""

    return StateRootPaths.from_root_dir(state_root).spawns_dir / str(spawn_id) / "heartbeat"


def ensure_gitignore(repo_root: Path) -> Path:
    """Seed `.meridian/.gitignore` and non-destructively add required tracked entries."""

    meridian_dir = resolve_repo_state_paths(repo_root).root_dir
    meridian_dir.mkdir(parents=True, exist_ok=True)
    gitignore_path = meridian_dir / ".gitignore"

    if gitignore_path.exists():
        existing_text = gitignore_path.read_text(encoding="utf-8")
        updated_text = _merge_required_gitignore_lines(existing_text)
        if updated_text != existing_text:
            atomic_write_text(gitignore_path, updated_text)
        return gitignore_path

    atomic_write_text(gitignore_path, _GITIGNORE_CONTENT)
    return gitignore_path


def _merge_required_gitignore_lines(existing_text: str) -> str:
    filtered_lines = [
        line
        for line in existing_text.splitlines()
        if line.strip() not in _DEPRECATED_GITIGNORE_LINES
    ]
    normalized_existing = "\n".join(filtered_lines)
    if existing_text.endswith("\n"):
        normalized_existing += "\n"

    present_lines = {line.strip() for line in filtered_lines}
    missing_lines = [line for line in _REQUIRED_GITIGNORE_LINES if line not in present_lines]
    if not missing_lines:
        return normalized_existing

    suffix = "\n".join(
        [
            "",
            "# Added by Meridian to keep required project state tracked",
            *missing_lines,
            "",
        ]
    )
    if not normalized_existing.endswith("\n"):
        return normalized_existing + suffix
    return normalized_existing + suffix.lstrip("\n")
