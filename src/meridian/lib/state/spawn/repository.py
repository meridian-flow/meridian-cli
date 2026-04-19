"""Spawn event persistence with injectable backends."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from meridian.lib.core.clock import Clock, RealClock
from meridian.lib.core.types import SpawnId
from meridian.lib.state import spawn_store
from meridian.lib.state.event_store import append_event as _append_event
from meridian.lib.state.event_store import read_events as _read_events
from meridian.lib.state.paths import StateRootPaths

if TYPE_CHECKING:
    from meridian.lib.state.spawn_store import SpawnEvent


class SpawnRepository(Protocol):
    """Protocol for spawn event persistence."""

    def append_event(self, event: SpawnEvent) -> None: ...

    def read_events(self) -> list[SpawnEvent]: ...

    def next_id(self) -> SpawnId: ...


class FileSpawnRepository:
    """Filesystem-backed spawn event repository."""

    def __init__(self, paths: StateRootPaths, clock: Clock | None = None):
        self._paths = paths
        self._clock = clock or RealClock()

    def append_event(self, event: SpawnEvent) -> None:
        _append_event(
            self._paths.spawns_jsonl,
            self._paths.spawns_flock,
            event,
            exclude_none=True,
        )

    def read_events(self) -> list[SpawnEvent]:
        return _read_events(self._paths.spawns_jsonl, spawn_store._parse_event)

    def next_id(self) -> SpawnId:
        starts = sum(1 for event in self.read_events() if event.event == "start")
        return SpawnId(f"p{starts + 1}")


__all__ = ["FileSpawnRepository", "SpawnRepository"]
