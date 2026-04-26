"""Shared spawn application service for all surfaces."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from meridian.lib.core.lifecycle import SpawnLifecycleService
from meridian.lib.core.types import SpawnId
from meridian.lib.state import spawn_store

if TYPE_CHECKING:
    from meridian.lib.state.spawn_store import SpawnRecord


class KeyedLockRegistry:
    """In-process keyed lock registry for spawn serialization."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._registry_lock = asyncio.Lock()

    async def acquire(self, key: str) -> asyncio.Lock:
        """Get or create a lock for the given key."""
        async with self._registry_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def release(self, key: str) -> None:
        """Keep lock mappings for the process lifetime.

        Removing a key can race with waiters that already hold the old lock
        instance, allowing a later caller to create a second lock for the same
        key and break per-key serialization. The registry is in-process and
        spawn keys are bounded enough that retaining locks is the safer tradeoff.
        """
        _ = key


class SpawnApplicationService:
    """Shared spawn application logic for all surfaces.

    Owns: validation, creation prep, cancel orchestration, finalize orchestration,
          archive, query, lifecycle broadcasting.
    Does NOT own: execution backend selection, surface-specific formatting.
    """

    def __init__(
        self,
        runtime_root: Path,
        lifecycle_service: SpawnLifecycleService,
    ) -> None:
        self._runtime_root = runtime_root
        self._lifecycle = lifecycle_service
        self._locks = KeyedLockRegistry()

    # ---- Query Helpers ----

    def get_spawn(self, spawn_id: SpawnId) -> SpawnRecord | None:
        """Get spawn record by ID."""
        return spawn_store.get_spawn(self._runtime_root, spawn_id)

    def require_spawn(self, spawn_id: SpawnId) -> SpawnRecord:
        """Get spawn or raise ValueError."""
        record = self.get_spawn(spawn_id)
        if record is None:
            raise ValueError(f"Spawn '{spawn_id}' not found")
        return record

    def is_terminal(self, status: str) -> bool:
        """Check if status is terminal."""
        from meridian.lib.core.spawn_lifecycle import TERMINAL_SPAWN_STATUSES

        return status in TERMINAL_SPAWN_STATUSES

    def require_not_terminal(self, record: SpawnRecord) -> None:
        """Raise if spawn is already terminal."""
        if self.is_terminal(record.status):
            raise ValueError(f"Spawn is already {record.status}")

    def require_not_finalizing(self, record: SpawnRecord) -> None:
        """Raise if spawn is currently finalizing."""
        if record.status == "finalizing":
            raise ValueError("Spawn is finalizing")

    # ---- Spawn Operations (stubs for 0B.2 and 0B.3) ----

    async def cancel(self, spawn_id: SpawnId) -> dict[str, Any]:
        """Cancel a spawn. Full implementation in 0B.2."""
        raise NotImplementedError("Implemented in 0B.2")

    async def complete_spawn(
        self,
        spawn_id: SpawnId,
        status: str,
        exit_code: int,
        *,
        origin: str,
        duration_secs: float | None = None,
        **metrics: object,
    ) -> bool:
        """Finalize a spawn. Full implementation in 0B.3."""
        raise NotImplementedError("Implemented in 0B.3")
