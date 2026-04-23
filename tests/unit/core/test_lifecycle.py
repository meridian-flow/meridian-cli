"""Unit tests for SpawnLifecycleService and LifecycleEvent."""

from __future__ import annotations

import dataclasses
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from meridian.lib.core.lifecycle import (
    LifecycleEvent,
    SpawnLifecycleService,
    create_lifecycle_service,
    generate_event_id,
    generate_lifecycle_event_id,
    get_hook_dispatcher,
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


class StoreSnapshotHook:
    """Reads store state inside hook to prove dispatch happens post-write."""

    def __init__(self, runtime_root: Path, repository: FakeSpawnRepository) -> None:
        self._state_root = runtime_root
        self._repository = repository
        self.snapshots: list[tuple[str, str | None, str | None]] = []

    def on_event(self, event: LifecycleEvent) -> None:
        record = spawn_store.get_spawn(
            self._state_root,
            event.spawn_id,
            repository=self._repository,
        )
        self.snapshots.append(
            (
                event.event_type,
                record.status if record is not None else None,
                record.terminal_origin if record is not None else None,
            )
        )


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_service(
    runtime_root: Path,
    hooks: list[Any] | None = None,
    repository: FakeSpawnRepository | None = None,
) -> SpawnLifecycleService:
    repo = repository if repository is not None else FakeSpawnRepository()
    return SpawnLifecycleService(runtime_root, hooks=hooks, repository=repo)


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
    """Service start() must delegate creation to spawn_store."""
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)

    spawn_id = _start_spawn(svc)

    records = spawn_store.list_spawns(tmp_path, repository=repo)
    assert len(records) == 1
    assert records[0].id == spawn_id
    assert records[0].agent == "coder"
    assert records[0].harness == "claude-code"


def test_mark_running_updates_spawn_status(tmp_path: Path) -> None:
    """Service mark_running() must delegate status transition to spawn_store."""
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="queued")

    svc.mark_running(spawn_id)

    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.status == "running"


def test_record_exited_stores_exit_code(tmp_path: Path) -> None:
    """Service record_exited() must persist process exit code through spawn_store."""
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    svc.record_exited(spawn_id, exit_code=42)

    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.process_exit_code == 42


def test_finalize_transitions_spawn_to_terminal(tmp_path: Path) -> None:
    """Service finalize() must commit terminal status/origin through spawn_store."""
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
    """Service mark_finalizing() must apply CAS running->finalizing via spawn_store."""
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    result = svc.mark_finalizing(spawn_id)

    assert result is True
    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.status == "finalizing"


def test_cancel_finalizes_with_cancelled_status(tmp_path: Path) -> None:
    """Service cancel() must route to finalize(cancelled, origin=cancel)."""
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
    """start() must emit exactly one post-write spawn.created event."""
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
    """spawn.created event must mirror persisted context fields from the created row."""
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
    """mark_running() must emit one spawn.running event after the store transition."""
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


# ---------------------------------------------------------------------------
# 4. spawn.finalized dispatched only when finalize returns True
# ---------------------------------------------------------------------------


def test_spawn_finalized_dispatched_on_first_terminal_transition(tmp_path: Path) -> None:
    """finalize() must emit spawn.finalized exactly once on first terminal write."""
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
    """spawn.finalized payload must include persisted terminal status/origin fields."""
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
    """No spawn.finalized event should be dispatched after terminal idempotent finalize."""
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


# ---------------------------------------------------------------------------
# 6. Hook exceptions don't block transitions
# ---------------------------------------------------------------------------


def test_hook_exception_does_not_block_transition(tmp_path: Path) -> None:
    """Hook failures must not block store writes or downstream hooks."""
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
    """Hook failures during finalize must not roll back terminal state writes."""
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
    """Dispatched LifecycleEvent instances must be immutable."""
    hook = RecordingHook()
    svc = _make_service(tmp_path, hooks=[hook])
    _start_spawn(svc)

    event = hook.events[0]
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        event.spawn_id = "mutated"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 8. Event IDs are stable for same spawn_id/event_type/sequence
# ---------------------------------------------------------------------------


def test_generate_event_id_is_deterministic() -> None:
    """generate_event_id() must be stable for identical inputs."""
    id1 = generate_event_id("p1", "spawn.created", 0)
    id2 = generate_event_id("p1", "spawn.created", 0)

    assert id1 == id2
    assert isinstance(id1, UUID)


def test_generate_event_id_differs_by_event_type() -> None:
    """Event type must participate in event-id identity."""
    created = generate_event_id("p1", "spawn.created", 0)
    running = generate_event_id("p1", "spawn.running", 0)

    assert created != running


def test_generate_event_id_preserves_legacy_spawn_namespace() -> None:
    """spawn.* IDs must keep legacy namespace for backward compatibility."""
    expected = uuid.uuid5(
        uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"),
        "meridian:spawn:p1:spawn.created:0",
    )
    assert generate_event_id("p1", "spawn.created", 0) == expected


def test_generate_lifecycle_event_id_supports_non_spawn_events() -> None:
    """Non-spawn events should use the shared event namespace."""
    expected = uuid.uuid5(
        uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"),
        "meridian:event:w1:work.started:0",
    )
    assert generate_lifecycle_event_id("w1", "work.started", 0) == expected


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
    """spawn.finalized must surface metrics fields when finalize() provides them."""
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


# ---------------------------------------------------------------------------
# 10. Illegal transition attempts — mark_finalizing guards
# ---------------------------------------------------------------------------


def test_mark_finalizing_returns_false_on_queued_spawn(tmp_path: Path) -> None:
    """mark_finalizing requires running status — queued spawn is silently rejected."""
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="queued")

    result = svc.mark_finalizing(spawn_id)

    assert result is False
    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.status == "queued"  # Status must be unchanged


def test_mark_finalizing_idempotent_second_call_returns_false(tmp_path: Path) -> None:
    """Calling mark_finalizing twice: first returns True, second returns False."""
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    first = svc.mark_finalizing(spawn_id)
    second = svc.mark_finalizing(spawn_id)  # Already finalizing, not running

    assert first is True
    assert second is False
    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.status == "finalizing"


# ---------------------------------------------------------------------------
# 11. Repeated finalize calls — second always returns False
# ---------------------------------------------------------------------------


def test_second_finalize_returns_false_with_different_terminal_status(tmp_path: Path) -> None:
    """Second finalize with a *different* terminal status still returns False.

    The first writer to reach the terminal state wins; subsequent calls
    must not overwrite the authoritative outcome.
    """
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    first = svc.finalize(spawn_id, "succeeded", 0, origin="runner")
    second = svc.finalize(spawn_id, "failed", 1, origin="launcher")

    assert first is True
    assert second is False
    record = spawn_store.get_spawn(tmp_path, spawn_id, repository=repo)
    assert record is not None
    assert record.status == "succeeded"  # First terminal status wins


# ---------------------------------------------------------------------------
# 14. Event ID stability across service instances
# ---------------------------------------------------------------------------


def test_event_id_stable_across_service_instances(tmp_path: Path) -> None:
    """Events for the same spawn_id/event_type carry identical IDs regardless
    of which service instance built the event."""
    hook1 = RecordingHook()
    hook2 = RecordingHook()

    svc1 = _make_service(tmp_path, hooks=[hook1])
    spawn_id = _start_spawn(svc1)  # spawns through svc1

    # Second service shares the same repository so it can see the spawn
    svc2 = _make_service(tmp_path, hooks=[hook2], repository=svc1._repository)
    svc2.mark_running(spawn_id)

    expected_created_id = generate_event_id(spawn_id, "spawn.created", 0)
    expected_running_id = generate_event_id(spawn_id, "spawn.running", 0)

    assert hook1.events[0].event_id == expected_created_id
    assert hook2.events[0].event_id == expected_running_id


# ---------------------------------------------------------------------------
# 15. Invalid transition: mark_running on a terminal spawn raises ValueError
# ---------------------------------------------------------------------------


def test_mark_running_on_terminal_spawn_raises_value_error(tmp_path: Path) -> None:
    """mark_running on a terminal spawn (succeeded → running) must raise ValueError.

    Terminal states have no allowed outbound transitions.  The store's
    _validate_transition guard raises ValueError which propagates through the
    service unchanged — the caller must handle the illegal-transition case.
    """
    repo = FakeSpawnRepository()
    svc = _make_service(tmp_path, repository=repo)
    spawn_id = _start_spawn(svc, status="running")
    svc.finalize(spawn_id, "succeeded", 0, origin="runner")

    # Spawn is now in terminal state: succeeded → running is forbidden
    with pytest.raises(ValueError, match="Illegal spawn transition"):
        svc.mark_running(spawn_id)


# ---------------------------------------------------------------------------
# 16. Required lifecycle-path coverage (Phase 5.1)
# ---------------------------------------------------------------------------


def test_required_path_start_and_running_dispatches_post_write(tmp_path: Path) -> None:
    """Required path: start/running events must observe post-write store snapshots."""
    repo = FakeSpawnRepository()
    recording = RecordingHook()
    snapshot = StoreSnapshotHook(tmp_path, repo)
    svc = _make_service(tmp_path, hooks=[recording, snapshot], repository=repo)

    spawn_id = _start_spawn(svc, status="queued")
    svc.mark_running(spawn_id)

    assert [event.event_type for event in recording.events] == ["spawn.created", "spawn.running"]
    assert snapshot.snapshots == [
        ("spawn.created", "queued", None),
        ("spawn.running", "running", None),
    ]


def test_required_path_mark_finalizing_then_finalize(tmp_path: Path) -> None:
    """Required path: finalizing+finalize must emit one finalized event with runner origin."""
    repo = FakeSpawnRepository()
    recording = RecordingHook()
    snapshot = StoreSnapshotHook(tmp_path, repo)
    svc = _make_service(tmp_path, hooks=[recording, snapshot], repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    marked = svc.mark_finalizing(spawn_id)
    finalized = svc.finalize(spawn_id, "succeeded", 0, origin="runner")

    assert marked is True
    assert finalized is True
    assert [event.event_type for event in recording.events] == ["spawn.created", "spawn.finalized"]
    finalized_event = recording.events[-1]
    assert finalized_event.status == "succeeded"
    assert finalized_event.origin == "runner"
    assert snapshot.snapshots[-1] == ("spawn.finalized", "succeeded", "runner")


def test_required_path_cancel_origin_and_post_write_hook(tmp_path: Path) -> None:
    """Required path: cancel must finalize with cancel origin and post-write visibility."""
    repo = FakeSpawnRepository()
    recording = RecordingHook()
    snapshot = StoreSnapshotHook(tmp_path, repo)
    svc = _make_service(tmp_path, hooks=[recording, snapshot], repository=repo)
    spawn_id = _start_spawn(svc, status="running")

    transitioned = svc.cancel(spawn_id)

    assert transitioned is True
    finalized_event = next(
        event for event in recording.events if event.event_type == "spawn.finalized"
    )
    assert finalized_event.status == "cancelled"
    assert finalized_event.origin == "cancel"
    assert snapshot.snapshots[-1] == ("spawn.finalized", "cancelled", "cancel")


# ---------------------------------------------------------------------------
# 17. Lifecycle factory hook wiring
# ---------------------------------------------------------------------------


def test_get_hook_dispatcher_returns_none_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MERIDIAN_HOOKS_ENABLED", "false")

    dispatcher = get_hook_dispatcher(tmp_path, tmp_path / ".meridian")

    assert dispatcher is None


def test_get_hook_dispatcher_returns_dispatcher_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from meridian.lib.hooks.dispatch import HookDispatcher

    monkeypatch.delenv("MERIDIAN_HOOKS_ENABLED", raising=False)

    dispatcher = get_hook_dispatcher(tmp_path, tmp_path / ".meridian")

    assert isinstance(dispatcher, HookDispatcher)


def test_create_lifecycle_service_centralizes_hook_enablement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MERIDIAN_HOOKS_ENABLED", "false")
    disabled_service = create_lifecycle_service(tmp_path, tmp_path / ".meridian")

    monkeypatch.setenv("MERIDIAN_HOOKS_ENABLED", "true")
    enabled_service = create_lifecycle_service(tmp_path, tmp_path / ".meridian")

    assert disabled_service._hooks == []
    assert len(enabled_service._hooks) == 1
    assert enabled_service._hooks[0].__class__.__name__ == "HookDispatcher"
