"""Unit tests for SpawnLifecycleService and LifecycleEvent."""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from meridian.lib.core.lifecycle import (
    LifecycleEvent,
    SpawnLifecycleService,
    generate_event_id,
)
from meridian.lib.state import spawn_store
from tests.support.fakes import FakeSpawnRepository


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class RecordingHook:
    """Captures every dispatched event for assertions."""

    def __init__(self) -> None:
        self.events: list[LifecycleEvent] = []

    def on_event(self, event: LifecycleEvent) -> None:
        self.events.append(event)


class FailingHook:
    """Always raises to verify failure isolation."""

    def on_event(self, event: LifecycleEvent) -> None:
        raise RuntimeError("deliberate hook failure")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_service(
    state_root: Path,
    hooks: list[Any] | None = None,
    repository: FakeSpawnRepository | None = None,
) -> SpawnLifecycleService:
    repo = repository if repository is not None else FakeSpawnRepository()
    return SpawnLifecycleService(state_root, hooks=hooks, repository=repo)


def _start_spawn(svc: SpawnLifecycleService, **overrides: Any) -> str:
    """Start a spawn with sensible defaults."""
    defaults: dict[str, Any] = dict(
        chat_id="chat-1",
        model="claude-3-5-haiku-20241022",
        agent="coder",
        harness="claude-code",
        prompt="do the thing",
        status="queued",
    )
    defaults.update(overrides)
    return svc.start(**defaults)


# ---------------------------------------------------------------------------
# 1. Delegation to spawn_store
# ---------------------------------------------------------------------------


def test_start_creates_spawn_record(tmp_path: Path) -> None:
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)

    spawn_id = _start_spawn(svc)

    records = spawn_store.list_spawns(tmp_path, repository=repo)
    assert len(records) == 1
    assert records[0].id == spawn_id
    assert records[0].agent == "coder"
    assert records[0].harness == "claude-code"


def test_mark_running_updates_spawn_status(tmp_path: Path) -> None:
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="queued")

    svc.mark_running(spawn_id)

    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.status == "running"


def test_record_exited_stores_exit_code(tmp_path: Path) -> None:
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    svc.record_exited(spawn_id, exit_code=42)

    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.process_exit_code == 42


def test_finalize_transitions_spawn_to_terminal(tmp_path: Path) -> None:
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    transitioned = svc.finalize(spawn_id, "succeeded", 0, origin="runner")

    assert transitioned is True
    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.status == "succeeded"
    assert record.terminal_origin == "runner"


def test_mark_finalizing_transitions_running_to_finalizing(tmp_path: Path) -> None:
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    result = svc.mark_finalizing(spawn_id)

    assert result is True
    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.status == "finalizing"


def test_cancel_finalizes_with_cancelled_status(tmp_path: Path) -> None:
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    transitioned = svc.cancel(spawn_id)

    assert transitioned is True
    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.status == "cancelled"
    assert record.terminal_origin == "cancel"


# ---------------------------------------------------------------------------
# 2. spawn.created event dispatched after start
# ---------------------------------------------------------------------------


def test_spawn_created_event_dispatched_after_start(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc)

    assert len(hook.events) == 1
    event = hook.events[0]
    assert event.event_type == "spawn.created"
    assert event.spawn_id == spawn_id
    assert event.agent == "coder"
    assert event.harness == "claude-code"
    assert event.status is None
    assert event.origin is None


def test_spawn_created_event_carries_context_fields(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])

    _start_spawn(svc, chat_id="chat-42", work_id="W1", model="claude-opus-4-5")

    event = hook.events[0]
    assert event.chat_id == "chat-42"
    assert event.work_id == "W1"
    assert event.model == "claude-opus-4-5"


# ---------------------------------------------------------------------------
# 3. spawn.running event dispatched after mark_running
# ---------------------------------------------------------------------------


def test_spawn_running_event_dispatched_after_mark_running(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc, status="queued")

    svc.mark_running(spawn_id)

    running_events = [e for e in hook.events if e.event_type == "spawn.running"]
    assert len(running_events) == 1
    event = running_events[0]
    assert event.spawn_id == spawn_id
    assert event.status is None
    assert event.origin is None


def test_mark_running_does_not_dispatch_finalized_event(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc, status="queued")

    svc.mark_running(spawn_id)

    finalized = [e for e in hook.events if e.event_type == "spawn.finalized"]
    assert finalized == []


# ---------------------------------------------------------------------------
# 4. spawn.finalized dispatched only when finalize returns True
# ---------------------------------------------------------------------------


def test_spawn_finalized_dispatched_on_first_terminal_transition(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc, status="running")

    transitioned = svc.finalize(spawn_id, "succeeded", 0, origin="runner")

    assert transitioned is True
    finalized = [e for e in hook.events if e.event_type == "spawn.finalized"]
    assert len(finalized) == 1
    event = finalized[0]
    assert event.status == "succeeded"
    assert event.origin == "runner"
    assert event.spawn_id == spawn_id


def test_spawn_finalized_event_has_status_and_origin(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc, status="running")

    svc.finalize(spawn_id, "failed", 1, origin="launcher", error="timeout")

    event = next(e for e in hook.events if e.event_type == "spawn.finalized")
    assert event.status == "failed"
    assert event.origin == "launcher"


# ---------------------------------------------------------------------------
# 5. spawn.finalized NOT dispatched when finalize returns False
# ---------------------------------------------------------------------------


def test_spawn_finalized_not_dispatched_when_already_terminal(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc, status="running")

    # First finalize — active → terminal; returns True
    svc.finalize(spawn_id, "succeeded", 0, origin="runner")
    hook.events.clear()

    # Second finalize — already terminal; returns False
    transitioned = svc.finalize(spawn_id, "failed", 1, origin="launcher")

    assert transitioned is False
    assert hook.events == []


def test_cancel_dispatches_finalized_only_once(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc, status="running")

    svc.cancel(spawn_id)
    hook.events.clear()

    # Second cancel — already terminal; no new event
    second = svc.cancel(spawn_id)

    assert second is False
    assert hook.events == []


# ---------------------------------------------------------------------------
# 6. Hook exceptions don't block transitions
# ---------------------------------------------------------------------------


def test_hook_exception_does_not_block_transition(tmp_path: Path) -> None:
    failing = FailingHook()
    recording = RecordingHook()
    svc = _make_service(tmp_path, hooks=[failing, recording])

    spawn_id = _start_spawn(svc)

    # Transition completed despite failing hook
    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=svc._repository)
    assert record is not None

    # Subsequent hooks still received the event
    assert len(recording.events) == 1
    assert recording.events[0].event_type == "spawn.created"


def test_hook_exception_does_not_block_finalize(tmp_path: Path) -> None:
    failing = FailingHook()
    svc = _make_service(tmp_path, hooks=[failing])
    spawn_id = _start_spawn(svc, status="running")

    transitioned = svc.finalize(spawn_id, "succeeded", 0, origin="runner")

    assert transitioned is True  # Store write succeeded despite hook failure
    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=svc._repository)
    assert record is not None
    assert record.status == "succeeded"


# ---------------------------------------------------------------------------
# 7. LifecycleEvent is frozen (immutable)
# ---------------------------------------------------------------------------


def test_lifecycle_event_is_frozen(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    _start_spawn(svc)

    event = hook.events[0]
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        event.spawn_id = "mutated"  # type: ignore[misc]


def test_lifecycle_event_dataclass_is_frozen_flag() -> None:
    """LifecycleEvent must be declared with frozen=True at the class level."""
    assert dataclasses.is_dataclass(LifecycleEvent)
    # dataclass frozen flag is recorded in __dataclass_params__
    assert LifecycleEvent.__dataclass_params__.frozen is True  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 8. Event IDs are stable for same spawn_id/event_type/sequence
# ---------------------------------------------------------------------------


def test_generate_event_id_is_deterministic() -> None:
    id1 = generate_event_id("p1", "spawn.created", 0)
    id2 = generate_event_id("p1", "spawn.created", 0)

    assert id1 == id2
    assert isinstance(id1, UUID)


def test_generate_event_id_differs_by_event_type() -> None:
    created = generate_event_id("p1", "spawn.created", 0)
    running = generate_event_id("p1", "spawn.running", 0)

    assert created != running


def test_generate_event_id_differs_by_spawn_id() -> None:
    id_p1 = generate_event_id("p1", "spawn.created", 0)
    id_p2 = generate_event_id("p2", "spawn.created", 0)

    assert id_p1 != id_p2


def test_generate_event_id_differs_by_sequence() -> None:
    seq0 = generate_event_id("p1", "spawn.running", 0)
    seq1 = generate_event_id("p1", "spawn.running", 1)

    assert seq0 != seq1


def test_event_id_stable_in_dispatched_events(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc)

    event = hook.events[0]
    expected = generate_event_id(spawn_id, "spawn.created", 0)
    assert event.event_id == expected


# ---------------------------------------------------------------------------
# 9. Metrics may be None on spawn.finalized
# ---------------------------------------------------------------------------


def test_finalized_event_metrics_may_be_none(tmp_path: Path) -> None:
    """spawn.finalized fires even when no metrics are provided."""
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc, status="running")

    svc.finalize(spawn_id, "succeeded", 0, origin="runner")

    event = next(e for e in hook.events if e.event_type == "spawn.finalized")
    assert event.duration_secs is None
    assert event.total_cost_usd is None
    assert event.input_tokens is None
    assert event.output_tokens is None


def test_finalized_event_includes_metrics_when_provided(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc, status="running")

    svc.finalize(
        spawn_id,
        "succeeded",
        0,
        origin="runner",
        duration_secs=12.5,
        total_cost_usd=0.003,
        input_tokens=1000,
        output_tokens=500,
    )

    event = next(e for e in hook.events if e.event_type == "spawn.finalized")
    assert event.duration_secs == 12.5
    assert event.total_cost_usd == 0.003
    assert event.input_tokens == 1000
    assert event.output_tokens == 500


def test_created_and_running_events_never_carry_metrics(tmp_path: Path) -> None:
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    spawn_id = _start_spawn(svc, status="queued")

    svc.mark_running(spawn_id)

    for event in hook.events:
        assert event.duration_secs is None
        assert event.total_cost_usd is None
        assert event.input_tokens is None
        assert event.output_tokens is None
