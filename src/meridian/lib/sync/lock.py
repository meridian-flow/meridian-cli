"""File-backed sync lock models and helpers."""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.state.atomic import atomic_write_text


class SyncLockEntry(BaseModel):
    """One provenance record for a synced skill or agent."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    source_type: Literal["repo", "path"]
    source_value: str
    source_item_name: str
    requested_ref: str | None
    locked_commit: str | None
    item_kind: Literal["skill", "agent"]
    dest_path: str
    tree_hash: str
    synced_at: str


class SyncLockFile(BaseModel):
    """Serialized `.meridian/sync.lock` content."""

    version: int = 1
    items: dict[str, SyncLockEntry] = Field(default_factory=dict)

def _flock_path(lock_path: Path) -> Path:
    return lock_path.with_name(f"{lock_path.name}.flock")


def read_lock_file(lock_path: Path) -> SyncLockFile:
    """Read and validate `.meridian/sync.lock`."""

    try:
        raw = lock_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return SyncLockFile()

    payload = json.loads(raw)
    return SyncLockFile.model_validate(cast("dict[str, object]", payload))


def write_lock_file(lock_path: Path, lock: SyncLockFile) -> None:
    """Write `.meridian/sync.lock` atomically."""

    atomic_write_text(
        lock_path,
        json.dumps(lock.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )


@contextmanager
def lock_file_guard(lock_path: Path) -> Iterator[None]:
    """Acquire an exclusive advisory lock for the sync lock file."""

    flock_path = _flock_path(lock_path)
    flock_path.parent.mkdir(parents=True, exist_ok=True)
    with flock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
