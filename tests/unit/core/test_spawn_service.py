"""Unit tests for SpawnApplicationService terminal finalization."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from meridian.lib.core.lifecycle import SpawnLifecycleService
from meridian.lib.core.spawn_service import SpawnApplicationService
from meridian.lib.core.types import SpawnId
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import RuntimePaths
from meridian.lib.state.spawn.repository import FileSpawnRepository


def _start_running_spawn(lifecycle: SpawnLifecycleService) -> SpawnId:
    return SpawnId(
        lifecycle.start(
            chat_id="chat-1",
            model="model-1",
            agent="coder",
            harness="codex",
            prompt="do the thing",
            status="running",
        )
    )


@pytest.mark.asyncio
async def test_complete_spawn_returns_true_for_first_terminal_transition(
    tmp_path: Path,
) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    spawn_id = _start_running_spawn(lifecycle)

    transitioned = await service.complete_spawn(
        spawn_id,
        "succeeded",
        0,
        origin="runner",
        duration_secs=1.5,
        total_cost_usd=0.25,
        input_tokens=10,
        output_tokens=20,
    )

    record = spawn_store.get_spawn(tmp_path, spawn_id)
    assert transitioned is True
    assert record is not None
    assert record.status == "succeeded"
    assert record.exit_code == 0
    assert record.duration_secs == 1.5
    assert record.total_cost_usd == 0.25
    assert record.input_tokens == 10
    assert record.output_tokens == 20
    assert record.terminal_origin == "runner"


@pytest.mark.asyncio
async def test_complete_spawn_returns_false_after_terminal_transition(
    tmp_path: Path,
) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    spawn_id = _start_running_spawn(lifecycle)

    first = await service.complete_spawn(spawn_id, "succeeded", 0, origin="runner")
    second = await service.complete_spawn(spawn_id, "failed", 1, origin="cancel")

    record = spawn_store.get_spawn(tmp_path, spawn_id)
    assert first is True
    assert second is False
    assert record is not None
    assert record.status == "succeeded"
    assert record.terminal_origin == "runner"


@pytest.mark.asyncio
async def test_complete_spawn_serializes_concurrent_terminal_attempts(
    tmp_path: Path,
) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    spawn_id = _start_running_spawn(lifecycle)

    results = await asyncio.gather(
        service.complete_spawn(spawn_id, "succeeded", 0, origin="runner"),
        service.complete_spawn(spawn_id, "cancelled", 130, origin="cancel"),
    )

    events = FileSpawnRepository(RuntimePaths.from_root_dir(tmp_path)).read_events()
    finalize_events = [event for event in events if event.event == "finalize"]
    record = spawn_store.get_spawn(tmp_path, spawn_id)
    assert sorted(results) == [False, True]
    assert len(finalize_events) == 1
    assert record is not None
    assert record.status in {"succeeded", "cancelled"}
