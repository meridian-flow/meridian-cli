"""Heartbeat management with injectable backends."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from meridian.lib.core.clock import Clock, RealClock


type HeartbeatTouch = Callable[[], None]


class FileHeartbeat:
    """File-backed heartbeat implementation."""

    def __init__(self, path: Path, clock: Clock | None = None):
        self._path = path
        self._clock = clock or RealClock()

    def touch(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.touch(exist_ok=True)
        now = self._clock.time()
        os.utime(self._path, (now, now))


__all__ = ["FileHeartbeat", "HeartbeatTouch"]
