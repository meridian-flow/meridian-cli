"""Per-spawn lock registry for control message serialization."""

from __future__ import annotations

import asyncio

from meridian.lib.core.types import SpawnId

_locks: dict[SpawnId, asyncio.Lock] = {}


def get_lock(spawn_id: SpawnId) -> asyncio.Lock:
    """Return the shared inject/interrupt lock for one spawn."""

    return _locks.setdefault(spawn_id, asyncio.Lock())


def drop_lock(spawn_id: SpawnId) -> None:
    """Delete any lock for a completed or removed spawn."""

    _locks.pop(spawn_id, None)
