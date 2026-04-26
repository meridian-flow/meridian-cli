"""Unit tests for SpawnApplicationService terminal finalization."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from meridian.lib.core.lifecycle import SpawnLifecycleService
from meridian.lib.core.spawn_service import SpawnApplicationService
from meridian.lib.core.telemetry import LifecycleEvent, LifecycleObserverTier
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


def _event() -> LifecycleEvent:
    return LifecycleEvent(
        event="spawn.running",
        spawn_id="p1",
        harness_id="codex",
        model="model-1",
        agent="coder",
        ts=datetime.now(UTC),
        seq=1,
    )


class _RecordingObserver:
    def __init__(
        self,
        label: str,
        calls: list[str],
        *,
        exc: Exception | None = None,
    ) -> None:
        self._label = label
        self._calls = calls
        self._exc = exc

    def on_event(self, event: LifecycleEvent) -> None:
        _ = event
        self._calls.append(self._label)
        if self._exc is not None:
            raise self._exc


def test_register_observer_defaults_to_diagnostic(tmp_path: Path) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    calls: list[str] = []

    service.register_observer(_RecordingObserver("diagnostic", calls))

    service._notify_observers(_event())

    assert calls == ["diagnostic"]


def test_policy_observers_run_before_diagnostic(tmp_path: Path) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    calls: list[str] = []

    service.register_observer(_RecordingObserver("diagnostic-1", calls))
    service.register_observer(
        _RecordingObserver("policy", calls),
        LifecycleObserverTier.POLICY,
    )
    service.register_observer(_RecordingObserver("diagnostic-2", calls))

    service._notify_observers(_event())

    assert calls == ["policy", "diagnostic-1", "diagnostic-2"]


def test_policy_observer_exception_propagates_and_vetoes_diagnostic(
    tmp_path: Path,
) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    calls: list[str] = []

    service.register_observer(
        _RecordingObserver("policy", calls, exc=RuntimeError("veto")),
        LifecycleObserverTier.POLICY,
    )
    service.register_observer(_RecordingObserver("diagnostic", calls))

    with pytest.raises(RuntimeError, match="veto"):
        service._notify_observers(_event())

    assert calls == ["policy"]


def test_diagnostic_observer_exception_is_logged_and_swallowed(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    lifecycle = SpawnLifecycleService(tmp_path)
    service = SpawnApplicationService(tmp_path, lifecycle)
    calls: list[str] = []

    service.register_observer(
        _RecordingObserver("diagnostic-fail", calls, exc=RuntimeError("boom")),
    )
    service.register_observer(_RecordingObserver("diagnostic-ok", calls))

    with caplog.at_level(logging.ERROR, logger="meridian.lib.core.spawn_service"):
        service._notify_observers(_event())

    assert calls == ["diagnostic-fail", "diagnostic-ok"]
    assert "Diagnostic observer failed for event spawn.running" in caplog.text


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
