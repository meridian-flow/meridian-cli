import json
from pathlib import Path

from meridian.lib.state.spawn_store import (
    cleanup_terminal_spawn_runtime_artifacts,
    finalize_spawn,
    get_spawn,
    list_spawns,
    record_spawn_exited,
    start_spawn,
    update_spawn,
)


def _state_root(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _write_mixed_valid_and_malformed_spawns_jsonl(state_root: Path) -> None:
    spawns_jsonl = state_root / "spawns.jsonl"
    with spawns_jsonl.open("w", encoding="utf-8") as handle:
        # valid start row
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "start",
                    "id": "p1",
                    "chat_id": "c1",
                    "model": "gpt-5.3-codex",
                    "agent": "coder",
                    "harness": "codex",
                    "status": "running",
                    "started_at": "2026-03-01T00:00:00Z",
                    "prompt": "hello",
                }
            )
            + "\n"
        )
        # invalid JSON
        handle.write("{ this is not json }\n")
        # valid JSON but invalid schema (status does not match SpawnStatus)
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "finalize",
                    "id": "broken",
                    "status": "definitely-not-a-status",
                    "exit_code": 1,
                }
            )
            + "\n"
        )
        # truncated JSON line
        handle.write('{"v":1,"event":"update","id":"p1","status":"running"\n')
        # valid finalize row for p1
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "finalize",
                    "id": "p1",
                    "status": "succeeded",
                    "exit_code": 0,
                    "finished_at": "2026-03-01T00:01:00Z",
                }
            )
            + "\n"
        )
        # second valid start row
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "start",
                    "id": "p2",
                    "chat_id": "c2",
                    "model": "gpt-5.4",
                    "agent": "coder",
                    "harness": "codex",
                    "status": "running",
                    "started_at": "2026-03-01T00:02:00Z",
                    "prompt": "world",
                }
            )
            + "\n"
        )


def test_list_runs_skips_truncated_trailing_json(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawns_jsonl = state_root / "spawns.jsonl"
    with spawns_jsonl.open("w", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "start",
                    "id": "r1",
                    "chat_id": "c1",
                    "model": "gpt-5.3-codex",
                    "agent": "coder",
                    "harness": "codex",
                    "status": "running",
                    "started_at": "2026-03-01T00:00:00Z",
                    "prompt": "hello",
                }
            )
            + "\n"
        )
        handle.write('{"v":1,"event":"finalize","id":"r1","status":"succeeded"')

    spawns = list_spawns(state_root)
    assert len(spawns) == 1
    assert spawns[0].id == "r1"
    assert spawns[0].status == "running"


def test_list_spawns_survives_mixed_malformed_rows(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    _write_mixed_valid_and_malformed_spawns_jsonl(state_root)

    spawns = list_spawns(state_root)

    assert [spawn.id for spawn in spawns] == ["p1", "p2"]
    assert spawns[0].status == "succeeded"
    assert spawns[1].status == "running"


def test_get_spawn_survives_mixed_malformed_rows(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    _write_mixed_valid_and_malformed_spawns_jsonl(state_root)

    row = get_spawn(state_root, "p2")

    assert row is not None
    assert row.id == "p2"
    assert row.chat_id == "c2"
    assert row.status == "running"


def test_first_terminal_finalize_preserves_error_when_later_succeeds(
    tmp_path: Path,
) -> None:
    """First terminal status wins, even when a later finalize reports success."""
    state_root = _state_root(tmp_path)

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )

    # First finalize: reaper synthesizes a failed status with orphan_run error
    finalize_spawn(state_root, spawn_id, status="failed", exit_code=1, error="orphan_run")
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "orphan_run"

    # Second finalize: later writer reports success.
    finalize_spawn(state_root, spawn_id, status="succeeded", exit_code=0)
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 1
    assert row.error == "orphan_run"


def test_finalize_spawn_returns_ownership_and_always_writes(tmp_path: Path) -> None:
    """finalize_spawn always appends the event.

    It returns True only for the first terminal write.
    """
    state_root = _state_root(tmp_path)
    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )

    assert (
        finalize_spawn(state_root, spawn_id, status="failed", exit_code=1, error="orphan_run")
        is True
    )
    assert (
        finalize_spawn(state_root, spawn_id, status="succeeded", exit_code=0, duration_secs=100.0)
        is False
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 1
    assert row.error == "orphan_run"
    assert row.duration_secs == 100.0


def test_exited_event_is_non_terminal_and_projects_process_exit(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )

    record_spawn_exited(
        state_root,
        spawn_id,
        exit_code=143,
        exited_at="2026-04-12T14:00:00Z",
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "running"
    assert row.exited_at == "2026-04-12T14:00:00Z"
    assert row.process_exit_code == 143
    assert row.exit_code is None


def test_runner_pid_projects_from_start_and_update(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        runner_pid=1111,
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.runner_pid == 1111

    update_spawn(state_root, spawn_id, runner_pid=2222)
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.runner_pid == 2222


def test_succeeded_cannot_be_overwritten_by_later_failed(tmp_path: Path) -> None:
    """Once a spawn is succeeded, a racing failed finalize cannot downgrade it.

    This is the core invariant that prevents the reaper/runner double-finalization
    race: the projection treats 'succeeded' as dominant over 'failed' regardless
    of event ordering, and merges metadata from all finalize events.
    """
    state_root = _state_root(tmp_path)

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )

    # First finalize: reaper correctly writes succeeded (no duration)
    finalize_spawn(state_root, spawn_id, status="succeeded", exit_code=0)
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0

    # Second finalize: runner races in with failed/143 (has duration)
    finalize_spawn(
        state_root,
        spawn_id,
        status="failed",
        exit_code=143,
        duration_secs=312.5,
        error="signal",
    )
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    # Status must remain succeeded — terminal immutability
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.error is None
    # But metadata from the second event IS merged
    assert row.duration_secs == 312.5


def test_failed_cannot_be_overwritten_by_another_failed(tmp_path: Path) -> None:
    """Among non-success terminal states, the first one wins."""
    state_root = _state_root(tmp_path)

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )

    finalize_spawn(state_root, spawn_id, status="failed", exit_code=1, error="timeout")
    finalize_spawn(state_root, spawn_id, status="failed", exit_code=143, error="signal")

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 1  # first failure's exit code
    assert row.error == "timeout"  # first failure's error reason is locked


def test_terminal_status_first_wins_cancelled_then_succeeded_audit_visible(
    tmp_path: Path,
) -> None:
    state_root = _state_root(tmp_path)

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )

    assert (
        finalize_spawn(state_root, spawn_id, status="cancelled", exit_code=130, error="cancelled")
        is True
    )
    assert finalize_spawn(state_root, spawn_id, status="succeeded", exit_code=0) is False

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "cancelled"
    assert row.exit_code == 130
    assert row.error == "cancelled"

    events = [
        json.loads(line)
        for line in (state_root / "spawns.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    finalize_statuses = [
        event.get("status")
        for event in events
        if event.get("event") == "finalize" and event.get("id") == str(spawn_id)
    ]
    assert finalize_statuses == ["cancelled", "succeeded"]


def test_terminal_status_first_wins_succeeded_then_cancelled_audit_visible(
    tmp_path: Path,
) -> None:
    state_root = _state_root(tmp_path)

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )

    assert finalize_spawn(state_root, spawn_id, status="succeeded", exit_code=0) is True
    assert (
        finalize_spawn(state_root, spawn_id, status="cancelled", exit_code=130, error="cancelled")
        is False
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.error is None

    events = [
        json.loads(line)
        for line in (state_root / "spawns.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    finalize_statuses = [
        event.get("status")
        for event in events
        if event.get("event") == "finalize" and event.get("id") == str(spawn_id)
    ]
    assert finalize_statuses == ["succeeded", "cancelled"]


def test_cleanup_terminal_spawn_runtime_artifacts_only_unlinks_terminal_rows(
    tmp_path: Path,
) -> None:
    state_root = _state_root(tmp_path)

    terminal_id = start_spawn(
        state_root,
        spawn_id="p10",
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )
    running_id = start_spawn(
        state_root,
        spawn_id="p11",
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )
    finalize_spawn(state_root, terminal_id, status="failed", exit_code=1, error="failed")

    for spawn_id in (str(terminal_id), str(running_id)):
        spawn_dir = state_root / "spawns" / spawn_id
        spawn_dir.mkdir(parents=True, exist_ok=True)
        for name in ("harness.pid", "heartbeat", "background.pid"):
            (spawn_dir / name).write_text("123\n", encoding="utf-8")

    removed = cleanup_terminal_spawn_runtime_artifacts(state_root, terminal_id)
    assert set(removed) == {"harness.pid", "heartbeat", "background.pid"}

    active_removed = cleanup_terminal_spawn_runtime_artifacts(state_root, running_id)
    assert active_removed == ()
    running_dir = state_root / "spawns" / str(running_id)
    assert (running_dir / "harness.pid").exists()
    assert (running_dir / "heartbeat").exists()
    assert (running_dir / "background.pid").exists()
