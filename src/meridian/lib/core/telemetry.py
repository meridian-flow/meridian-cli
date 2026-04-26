"""Lifecycle event model and observer contracts."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from meridian.lib.core.types import SpawnId


class LifecycleObserverTier(Enum):
    """Observer tier determines exception handling and ordering."""

    DIAGNOSTIC = "diagnostic"  # best-effort, exceptions logged and swallowed
    POLICY = "policy"  # control path, exceptions propagate


class LifecycleObserver(Protocol):
    """Observer of spawn lifecycle events."""

    def on_event(self, event: LifecycleEvent) -> None:
        """Handle a lifecycle event.

        Called synchronously. Async observers should wrap their async
        dispatch in asyncio.create_task() inside this method.
        """
        ...


@dataclass(frozen=True)
class LifecycleEvent:
    """Lifecycle event carrying full context.

    Base fields are frozen after Phase 0 ships — mars hook compilation
    depends on this shape.
    """

    # --- Base fields (frozen) ---
    event: str
    spawn_id: str
    harness_id: str
    model: str
    agent: str | None
    ts: datetime
    seq: int
    # Event-specific fields
    payload: dict[str, Any] = field(default_factory=dict[str, Any])


class SpawnEventCounter:
    """Thread-safe monotonic counter per spawn.

    Allocated at spawn.queued time and passed to StartupPhaseEmitter
    so all event sources share one counter.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def allocate(self, spawn_id: SpawnId | str) -> int:
        """Allocate initial sequence number for a new spawn."""
        with self._lock:
            spawn_key = str(spawn_id)
            self._counters[spawn_key] = 0
            return 0

    def next(self, spawn_id: SpawnId | str) -> int:
        """Get next sequence number for an existing spawn."""
        with self._lock:
            spawn_key = str(spawn_id)
            if spawn_key not in self._counters:
                self._counters[spawn_key] = 0
            self._counters[spawn_key] += 1
            return self._counters[spawn_key]

    def release(self, spawn_id: SpawnId | str) -> None:
        """Clean up counter for a terminated spawn (optional)."""
        with self._lock:
            self._counters.pop(str(spawn_id), None)


# Event names for core state transitions
CORE_EVENTS = frozenset(
    {
        "spawn.queued",
        "spawn.running",
        "spawn.finalizing",
        "spawn.succeeded",
        "spawn.failed",
        "spawn.cancelled",
        "spawn.archived",
    }
)

# Observability signal event names
SIGNAL_EVENTS = frozenset(
    {
        "launching_subprocess",
        "waiting_for_connection",
        "initializing_session",
        "harness.ready",
        "skills.loading",
        "sending_prompt",
        "waiting_for_response",
        "spawn.streaming",
        "spawn.updated",
        "harness.failed",
    }
)
