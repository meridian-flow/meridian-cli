from __future__ import annotations

import json
import os
import time
from pathlib import Path

import meridian.lib.core.telemetry as core_telemetry
import meridian.lib.telemetry.observer as spawn_observer
import meridian.lib.telemetry.observers as lifecycle_observers
from meridian.lib.core.lifecycle import SpawnLifecycleService
from meridian.lib.core.telemetry import SpawnEventCounter
from meridian.lib.telemetry import emit_telemetry
from meridian.lib.telemetry.init import setup_telemetry
from meridian.lib.telemetry.retention import run_retention_cleanup


def wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met")


def read_telemetry_events(runtime_root: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for segment in sorted((runtime_root / "telemetry").glob("*.jsonl")):
        for line in segment.read_text(encoding="utf-8").splitlines():
            events.append(json.loads(line))
    return events


def start_spawn(service: SpawnLifecycleService, *, status: str = "running") -> str:
    return service.start(
        chat_id="chat-1",
        model="test-model",
        agent="coder",
        harness="test-harness",
        prompt="do the thing",
        status=status,  # type: ignore[arg-type]
    )


def setup_spawn_projection(runtime_root: Path, monkeypatch) -> None:
    monkeypatch.setattr(lifecycle_observers, "_GLOBAL_OBSERVERS", [])
    monkeypatch.setattr(lifecycle_observers, "_debug_trace_registered", False)
    monkeypatch.setattr(spawn_observer, "_registered", False)
    monkeypatch.setattr(core_telemetry, "_GLOBAL_EVENT_COUNTER", SpawnEventCounter())
    setup_telemetry(runtime_root=runtime_root)
    spawn_observer.register_spawn_telemetry_observer()


def test_retention_cleanup_deletes_old_orphaned_files(tmp_path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    telemetry_dir.mkdir()
    old = telemetry_dir / "999999-0001.jsonl"
    old.write_text('{"event":"old"}\n', encoding="utf-8")
    old_time = time.time() - 10 * 24 * 60 * 60
    os.utime(old, (old_time, old_time))

    run_retention_cleanup(telemetry_dir, max_age_days=7)

    assert not old.exists()


def test_retention_preserves_files_from_live_processes(tmp_path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    telemetry_dir.mkdir()
    live = telemetry_dir / f"{os.getpid()}-0001.jsonl"
    live.write_text('{"event":"live"}\n', encoding="utf-8")
    old_time = time.time() - 10 * 24 * 60 * 60
    os.utime(live, (old_time, old_time))

    run_retention_cleanup(telemetry_dir, max_age_days=7, max_total_bytes=1)

    assert live.exists()


def test_full_pipeline_emit_queue_writer_segment(tmp_path) -> None:
    setup_telemetry(runtime_root=tmp_path)
    emit_telemetry("chat", "chat.ws.connected", scope="chat.server.ws", ids={"chat_id": "c1"})

    segment = tmp_path / "telemetry" / f"{os.getpid()}-0001.jsonl"
    wait_for(lambda: segment.exists() and segment.read_text(encoding="utf-8"))
    event = json.loads(segment.read_text(encoding="utf-8").splitlines()[0])
    assert event["event"] == "chat.ws.connected"
    assert event["ids"] == {"chat_id": "c1"}


def test_spawn_process_exited_projects_to_telemetry_segment(tmp_path, monkeypatch) -> None:
    setup_spawn_projection(tmp_path, monkeypatch)
    service = SpawnLifecycleService(tmp_path)
    spawn_id = start_spawn(service)

    service.record_exited(spawn_id, exit_code=42)

    wait_for(
        lambda: any(
            event["event"] == "spawn.process_exited"
            for event in read_telemetry_events(tmp_path)
        )
    )
    projected = [
        event
        for event in read_telemetry_events(tmp_path)
        if event["event"] == "spawn.process_exited"
    ]
    assert projected == [
        {
            **projected[0],
            "domain": "spawn",
            "scope": "core.lifecycle",
            "severity": "info",
            "ids": {"spawn_id": spawn_id},
            "data": {"exit_code": 42},
        }
    ]


def test_spawn_terminal_success_and_failure_project_to_telemetry_segment(
    tmp_path, monkeypatch
) -> None:
    setup_spawn_projection(tmp_path, monkeypatch)
    service = SpawnLifecycleService(tmp_path)
    succeeded_id = start_spawn(service)
    failed_id = start_spawn(service)

    service.finalize(
        succeeded_id,
        "succeeded",
        0,
        origin="runner",
        duration_secs=1.5,
    )
    service.finalize(
        failed_id,
        "failed",
        2,
        origin="runner",
        error="boom",
    )

    wait_for(
        lambda: {
            event["event"] for event in read_telemetry_events(tmp_path)
        }.issuperset({"spawn.succeeded", "spawn.failed"})
    )
    events = read_telemetry_events(tmp_path)
    succeeded = next(event for event in events if event["event"] == "spawn.succeeded")
    failed = next(event for event in events if event["event"] == "spawn.failed")

    assert succeeded["severity"] == "info"
    assert succeeded["ids"] == {"spawn_id": succeeded_id}
    assert succeeded["data"] == {
        "status": "succeeded",
        "exit_code": 0,
        "duration_secs": 1.5,
    }
    assert failed["severity"] == "error"
    assert failed["ids"] == {"spawn_id": failed_id}
    assert failed["data"] == {"status": "failed", "exit_code": 2, "reason": "boom"}


def test_non_terminal_spawn_lifecycle_events_are_not_projected(
    tmp_path, monkeypatch
) -> None:
    setup_spawn_projection(tmp_path, monkeypatch)
    service = SpawnLifecycleService(tmp_path)
    spawn_id = start_spawn(service, status="queued")

    service.mark_running(spawn_id)
    service.mark_finalizing(spawn_id)

    time.sleep(0.05)
    event_names = {event["event"] for event in read_telemetry_events(tmp_path)}
    assert "spawn.queued" not in event_names
    assert "spawn.running" not in event_names
    assert "spawn.finalizing" not in event_names
