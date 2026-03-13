
import json
from pathlib import Path

from meridian.lib.state.spawn_store import finalize_spawn, get_spawn, list_spawns, start_spawn, update_spawn


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


def test_spawn_record_preserves_desc_and_work_id(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        desc="investigate bug",
        work_id="work-7",
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.desc == "investigate bug"
    assert row.work_id == "work-7"


def test_spawn_record_tracks_launch_mode_and_process_pids(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        launch_mode="background",
        status="queued",
    )
    update_spawn(state_root, spawn_id, status="running", wrapper_pid=4321, worker_pid=8765)

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.launch_mode == "background"
    assert row.wrapper_pid == 4321
    assert row.worker_pid == 8765
    assert row.status == "running"


def test_succeeded_finalize_clears_stale_error(tmp_path: Path) -> None:
    """A succeeded finalize event must clear any stale error from a prior failed finalize."""
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

    # Second finalize: runner writes the real succeeded status (error=None, dropped by exclude_none)
    finalize_spawn(state_root, spawn_id, status="succeeded", exit_code=0)
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.error is None, f"Expected error=None after succeeded finalize, got {row.error!r}"


def test_finalize_spawn_returns_ownership_and_always_writes(tmp_path: Path) -> None:
    """finalize_spawn always appends the event but returns True only for the first terminal write."""
    state_root = _state_root(tmp_path)
    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
    )

    assert finalize_spawn(
        state_root, spawn_id, status="failed", exit_code=1, error="orphan_run"
    ) is True
    assert finalize_spawn(
        state_root, spawn_id, status="succeeded", exit_code=0, duration_secs=100.0
    ) is False

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.error is None
    assert row.duration_secs == 100.0


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
        state_root, spawn_id, status="failed", exit_code=143,
        duration_secs=312.5, error="signal",
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


def test_update_spawn_backfills_work_id_and_desc(tmp_path: Path) -> None:
    """Update events can backfill work_id and desc onto an existing spawn."""
    state_root = _state_root(tmp_path)

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        kind="primary",
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.work_id is None
    assert row.desc is None

    update_spawn(state_root, spawn_id, work_id="my-feature", desc="orchestrator")

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.work_id == "my-feature"
    assert row.desc == "orchestrator"
