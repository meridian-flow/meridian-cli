"""Shared spawn application service for all surfaces."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.core.lifecycle import SpawnLifecycleService
from meridian.lib.core.types import SpawnId
from meridian.lib.state import spawn_store
from meridian.lib.state.liveness import is_process_alive
from meridian.lib.state.spawn_store import SpawnOrigin
from meridian.lib.streaming.signal_canceller import CancelOutcome as SignalCancelOutcome

if TYPE_CHECKING:
    from meridian.lib.state.primary_meta import PrimaryMetadata
    from meridian.lib.state.spawn_store import SpawnRecord
    from meridian.lib.streaming.spawn_manager import SpawnManager


_WAIT_POLL_INTERVAL_SECS = 0.1
_MANAGED_CANCEL_GRACE_SECS = 5.0
_MANAGED_CANCEL_FALLBACK_WAIT_SECS = 1.0


@dataclass(frozen=True)
class CancelOutcome:
    """Surface-neutral result of cancelling a spawn."""

    spawn_id: str
    status: SpawnStatus
    origin: SpawnOrigin
    exit_code: int
    already_terminal: bool = False
    finalizing: bool = False
    model: str | None = None
    harness: str | None = None


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
        *,
        spawn_manager: SpawnManager | None = None,
    ) -> None:
        self._runtime_root = runtime_root
        self._lifecycle = lifecycle_service
        self._spawn_manager = spawn_manager
        self._locks = KeyedLockRegistry()

    # ---- Query Helpers ----

    def get_spawn(self, spawn_id: SpawnId | str) -> SpawnRecord | None:
        """Get spawn record by ID."""
        return spawn_store.get_spawn(self._runtime_root, spawn_id)

    def require_spawn(self, spawn_id: SpawnId | str) -> SpawnRecord:
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

    async def cancel(self, spawn_id: SpawnId) -> CancelOutcome:
        """Cancel a spawn through the shared surface-neutral pipeline."""
        lock = await self._locks.acquire(str(spawn_id))
        async with lock:
            record = self.require_spawn(spawn_id)
            if self.is_terminal(record.status):
                return _cancel_outcome_from_record(str(spawn_id), record, already_terminal=True)

            if record.status == "finalizing":
                terminal = await self._wait_for_terminal(spawn_id, timeout=5.0)
                latest = terminal or self.get_spawn(spawn_id) or record
                return _cancel_outcome_from_record(
                    str(spawn_id),
                    latest,
                    already_terminal=terminal is not None,
                    finalizing=terminal is None,
                )

            from meridian.lib.state.primary_meta import read_primary_metadata

            primary_metadata = read_primary_metadata(self._runtime_root, str(spawn_id))
            if primary_metadata is not None and primary_metadata.managed_backend:
                return await self._cancel_managed_primary(spawn_id, record, primary_metadata)

            from meridian.lib.streaming.signal_canceller import SignalCanceller

            signal_outcome = await SignalCanceller(
                runtime_root=self._runtime_root,
                manager=self._spawn_manager,
            ).cancel(spawn_id)
            latest = self.get_spawn(spawn_id) or record
            return _cancel_outcome_from_signal(str(spawn_id), signal_outcome, latest)

    async def _wait_for_terminal(
        self,
        spawn_id: SpawnId,
        *,
        timeout: float,
    ) -> SpawnRecord | None:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            current = self.get_spawn(spawn_id)
            if current is not None and self.is_terminal(current.status):
                return current
            now = time.monotonic()
            if now >= deadline:
                return None
            await asyncio.sleep(min(_WAIT_POLL_INTERVAL_SECS, deadline - now))

    async def _cancel_managed_primary(
        self,
        spawn_id: SpawnId,
        record: SpawnRecord,
        primary_metadata: PrimaryMetadata,
    ) -> CancelOutcome:
        from meridian.lib.state.managed_primary import terminate_managed_primary_processes

        if self.is_terminal(record.status):
            return _cancel_outcome_from_record(str(spawn_id), record, already_terminal=True)

        started_epoch = _started_at_epoch(record.started_at)
        launcher_pid = primary_metadata.launcher_pid
        launcher_alive = (
            launcher_pid is not None
            and is_process_alive(launcher_pid, created_after_epoch=started_epoch)
        )
        if launcher_alive:
            terminate_managed_primary_processes(
                primary_metadata,
                started_epoch=started_epoch,
                include_launcher=True,
                include_runtime_children=False,
            )
        else:
            terminate_managed_primary_processes(
                primary_metadata,
                started_epoch=started_epoch,
                include_launcher=False,
            )

        latest = await self._wait_for_terminal(
            spawn_id,
            timeout=_MANAGED_CANCEL_GRACE_SECS,
        )
        if latest is None and launcher_alive:
            terminate_managed_primary_processes(
                primary_metadata,
                started_epoch=started_epoch,
                include_launcher=False,
            )
            latest = await self._wait_for_terminal(
                spawn_id,
                timeout=_MANAGED_CANCEL_FALLBACK_WAIT_SECS,
            )

        if latest is None:
            latest = self.get_spawn(spawn_id) or record
            if latest.status == "finalizing":
                return _cancel_outcome_from_record(str(spawn_id), latest, finalizing=True)
            if self.is_terminal(latest.status):
                return _cancel_outcome_from_record(
                    str(spawn_id),
                    latest,
                    already_terminal=True,
                )

            if self._lifecycle.mark_finalizing(str(spawn_id)):
                latest = self.get_spawn(spawn_id) or latest
            else:
                latest = self.get_spawn(spawn_id) or latest
                if latest.status == "finalizing":
                    return _cancel_outcome_from_record(str(spawn_id), latest, finalizing=True)
                if self.is_terminal(latest.status):
                    return _cancel_outcome_from_record(
                        str(spawn_id),
                        latest,
                        already_terminal=True,
                    )
                self._lifecycle.finalize(
                    str(spawn_id),
                    "failed",
                    1,
                    origin="cancel",
                    error="cancel_timeout",
                )
                latest = self.get_spawn(spawn_id) or latest

        return _cancel_outcome_from_record(
            str(spawn_id),
            latest,
            finalizing=latest.status == "finalizing",
        )

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


def _cancel_outcome_from_signal(
    spawn_id: str,
    outcome: SignalCancelOutcome,
    record: SpawnRecord,
) -> CancelOutcome:
    return CancelOutcome(
        spawn_id=spawn_id,
        status=outcome.status,
        origin=outcome.origin,
        exit_code=outcome.exit_code,
        already_terminal=outcome.already_terminal,
        finalizing=outcome.finalizing,
        model=record.model,
        harness=record.harness,
    )


def _cancel_outcome_from_record(
    spawn_id: str,
    record: SpawnRecord,
    *,
    already_terminal: bool = False,
    finalizing: bool = False,
) -> CancelOutcome:
    return CancelOutcome(
        spawn_id=spawn_id,
        status=_coerce_cancel_status(record.status),
        origin=record.terminal_origin or "cancel",
        exit_code=record.exit_code if record.exit_code is not None else 1,
        already_terminal=already_terminal,
        finalizing=finalizing,
        model=record.model,
        harness=record.harness,
    )


def _coerce_cancel_status(status: str) -> SpawnStatus:
    if status in {"queued", "running", "finalizing", "succeeded", "failed", "cancelled"}:
        return cast("SpawnStatus", status)
    return "failed"


def _started_at_epoch(started_at: str | None) -> float | None:
    normalized = (started_at or "").strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


__all__ = ["CancelOutcome", "KeyedLockRegistry", "SpawnApplicationService"]
