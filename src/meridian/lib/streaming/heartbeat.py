"""Heartbeat helpers shared by launch runners."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from meridian.lib.core.types import SpawnId
from meridian.lib.state import paths


async def heartbeat_loop(
    state_root: Path,
    spawn_id: SpawnId,
    interval: float = 30.0,
    touch: Callable[[Path, SpawnId], None] | None = None,
) -> None:
    """Touch the per-spawn heartbeat sentinel on a fixed interval."""

    sentinel = paths.heartbeat_path(state_root, spawn_id)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    while True:
        if touch is None:
            sentinel.touch()
        else:
            touch(state_root, spawn_id)
        await asyncio.sleep(interval)
