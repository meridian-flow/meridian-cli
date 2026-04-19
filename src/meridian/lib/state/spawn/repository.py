"""Spawn event persistence for spawn_store internals.

This protocol is an internal test seam for spawn_store event IO. Meridian has a
single filesystem backend; this module is not a runtime backend abstraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from meridian.lib.state import spawn_store
from meridian.lib.state.event_store import append_event as _append_event
from meridian.lib.state.event_store import read_events as _read_events
from meridian.lib.state.paths import StateRootPaths

if TYPE_CHECKING:
    from meridian.lib.state.spawn_store import SpawnEvent


class SpawnRepository(Protocol):
    """Internal seam for spawn_store event persistence tests."""

    def append_event(self, event: SpawnEvent) -> None: ...

    def read_events(self) -> list[SpawnEvent]: ...


class FileSpawnRepository:
    """Filesystem-backed spawn event repository."""

    def __init__(self, paths: StateRootPaths):
        self._paths = paths

    def append_event(self, event: SpawnEvent) -> None:
        _append_event(
            self._paths.spawns_jsonl,
            self._paths.spawns_flock,
            event,
            exclude_none=True,
        )

    def read_events(self) -> list[SpawnEvent]:
        return _read_events(self._paths.spawns_jsonl, spawn_store._parse_event)


__all__ = ["FileSpawnRepository", "SpawnRepository"]
