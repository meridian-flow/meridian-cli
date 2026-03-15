from __future__ import annotations

# pyright: reportPrivateUsage=false
import asyncio
import time
from pathlib import Path

import pytest

from meridian.lib.launch import heartbeat as heartbeat_module
from meridian.lib.launch.heartbeat import (
    heartbeat_scope,
    threaded_heartbeat_scope,
)


@pytest.mark.asyncio
async def test_heartbeat_scope_writes_and_cancels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat_path = tmp_path / "heartbeat.txt"

    created_task: asyncio.Task[None] | None = None
    real_create_task = heartbeat_module.asyncio.create_task

    def _recording_create_task(coro: object) -> asyncio.Task[None]:
        nonlocal created_task
        created_task = real_create_task(coro)  # type: ignore[arg-type]
        return created_task

    monkeypatch.setattr(heartbeat_module.asyncio, "create_task", _recording_create_task)

    async with heartbeat_scope(heartbeat_path, interval_secs=0.1):
        await asyncio.sleep(0.03)
        assert heartbeat_path.is_file()
        assert time.time() - heartbeat_path.stat().st_mtime < 1.0

    assert heartbeat_path.is_file()
    assert created_task is not None
    assert created_task.done()
    assert created_task.cancelled()


@pytest.mark.asyncio
async def test_heartbeat_scope_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat_path = tmp_path / "heartbeat.txt"

    touches: list[float] = []
    real_touch = heartbeat_module._touch_heartbeat

    def _recording_touch(path: Path) -> None:
        real_touch(path)
        touches.append(path.stat().st_mtime)

    monkeypatch.setattr(heartbeat_module, "_touch_heartbeat", _recording_touch)

    async with heartbeat_scope(heartbeat_path, interval_secs=0.05):
        await asyncio.sleep(0.16)

    assert len(touches) >= 2
    assert touches[-1] > touches[0]


def test_threaded_heartbeat_scope_writes_and_stops(tmp_path: Path) -> None:
    heartbeat_path = tmp_path / "heartbeat.txt"

    start = time.monotonic()
    with threaded_heartbeat_scope(heartbeat_path, interval_secs=1.0):
        while not heartbeat_path.exists() and time.monotonic() - start < 0.2:
            time.sleep(0.01)
        assert heartbeat_path.is_file()
        first_mtime = heartbeat_path.stat().st_mtime

    assert heartbeat_path.is_file()
    time.sleep(1.1)
    assert heartbeat_path.stat().st_mtime == first_mtime


def test_threaded_heartbeat_scope_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat_path = tmp_path / "heartbeat.txt"

    touches: list[float] = []
    real_touch = heartbeat_module._touch_heartbeat

    def _recording_touch(path: Path) -> None:
        real_touch(path)
        touches.append(path.stat().st_mtime)

    monkeypatch.setattr(heartbeat_module, "_touch_heartbeat", _recording_touch)

    with threaded_heartbeat_scope(heartbeat_path, interval_secs=0.05):
        time.sleep(0.18)

    assert len(touches) >= 2
    assert touches[-1] > touches[0]
