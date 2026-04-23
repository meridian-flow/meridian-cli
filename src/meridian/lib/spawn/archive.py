"""Archive-state helpers for spawn visibility."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.event_store import lock_file


def archived_spawns_path(runtime_root: Path) -> Path:
    """Path to the archived spawns JSON file."""
    return runtime_root / "app" / "archived_spawns.json"


def archived_spawns_lock_path(runtime_root: Path) -> Path:
    """Lock path for archived spawns file."""
    return runtime_root / "app" / "archived_spawns.flock"


def read_archived_spawns(runtime_root: Path) -> set[str]:
    """Read the set of archived spawn IDs."""
    path = archived_spawns_path(runtime_root)
    lock_path = archived_spawns_lock_path(runtime_root)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_file(lock_path):
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                raw_items = cast("list[object]", data)
                return {item for item in raw_items if isinstance(item, str)}
            return set()
        except (json.JSONDecodeError, OSError):
            return set()


def write_archived_spawns(runtime_root: Path, archived: set[str]) -> None:
    """Write the set of archived spawn IDs atomically."""
    path = archived_spawns_path(runtime_root)
    lock_path = archived_spawns_lock_path(runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)

    with lock_file(lock_path):
        atomic_write_text(path, json.dumps(sorted(archived), indent=2) + "\n")


def archive_spawn(runtime_root: Path, spawn_id: str) -> None:
    """Add a spawn ID to the archived set."""
    archived = read_archived_spawns(runtime_root)
    archived.add(spawn_id)
    write_archived_spawns(runtime_root, archived)


def unarchive_spawn(runtime_root: Path, spawn_id: str) -> None:
    """Remove a spawn ID from the archived set."""
    archived = read_archived_spawns(runtime_root)
    archived.discard(spawn_id)
    write_archived_spawns(runtime_root, archived)


def is_spawn_archived(runtime_root: Path, spawn_id: str) -> bool:
    """Check if a spawn is archived."""
    return spawn_id in read_archived_spawns(runtime_root)


__all__ = [
    "archive_spawn",
    "archived_spawns_lock_path",
    "archived_spawns_path",
    "is_spawn_archived",
    "read_archived_spawns",
    "unarchive_spawn",
    "write_archived_spawns",
]
