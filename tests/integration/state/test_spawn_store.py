import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.state.spawn_store import (
    finalize_spawn,
    get_spawn,
    list_spawns,
    mark_finalizing,
    record_spawn_exited,
    start_spawn,
    update_spawn,
)


def _state_root(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _start_test_spawn(runtime_root: Path) -> str:
    return str(
        start_spawn(
            runtime_root,
            chat_id="c1",
            model="gpt-5.4",
            agent="coder",
            harness="codex",
            prompt="hello",
        )
    )


def _write_mixed_valid_and_malformed_spawns_jsonl(runtime_root: Path) -> None:
    spawns_jsonl = runtime_root / "spawns.jsonl"
    with spawns_jsonl.open("w", encoding="utf-8") as handle:
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
        handle.write("{ this is not json }\n")
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
        handle.write('{"v":1,"event":"update","id":"p1","status":"running"\n')
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "finalize",
                    "id": "p1",
                    "status": "succeeded",
                    "exit_code": 0,
                    "finished_at": "2026-03-01T00:01:00Z",
                    "origin": "runner",
                }
            )
            + "\n"
        )
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


def test_start_and_update_project_fields_round_trip(tmp_path: Path) -> None:
    runtime_root = _state_root(tmp_path)
    spawn_id = str(
        start_spawn(
            runtime_root,
            chat_id="c1",
            model="gpt-5.4",
            agent="coder",
            harness="codex",
            prompt="hello",
            launch_mode="app",
            runner_pid=1111,
        )
    )

    row = get_spawn(runtime_root, spawn_id)
    assert row is not None
    assert row.launch_mode == "app"
    assert row.runner_pid == 1111

    update_spawn(runtime_root, spawn_id, launch_mode="foreground", runner_pid=2222)
    row = get_spawn(runtime_root, spawn_id)
    assert row is not None
    assert row.launch_mode == "foreground"
    assert row.runner_pid == 2222


def test_list_runs_skips_truncated_trailing_json(tmp_path: Path) -> None:
    runtime_root = _state_root(tmp_path)
    spawns_jsonl = runtime_root / "spawns.jsonl"
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

    spawns = list_spawns(runtime_root)
    assert len(spawns) == 1
    assert spawns[0].id == "r1"
    assert spawns[0].status == "running"


def test_spawn_queries_survive_mixed_malformed_rows(tmp_path: Path) -> None:
    runtime_root = _state_root(tmp_path)
    _write_mixed_valid_and_malformed_spawns_jsonl(runtime_root)

    spawns = list_spawns(runtime_root)
    assert [spawn.id for spawn in spawns] == ["p1", "p2"]
    assert spawns[0].status == "succeeded"
    assert spawns[1].status == "running"

    row = get_spawn(runtime_root, "p2")
    assert row is not None
    assert row.id == "p2"
    assert row.chat_id == "c2"
    assert row.status == "running"


def test_mark_finalizing_state_machine_enforces_running_only(tmp_path: Path) -> None:
    runtime_root = _state_root(tmp_path)
    running_spawn_id = _start_test_spawn(runtime_root)

    assert mark_finalizing(runtime_root, running_spawn_id) is True
    row = get_spawn(runtime_root, running_spawn_id)
    assert row is not None
    assert row.status == "finalizing"
    assert mark_finalizing(runtime_root, "p-missing") is False

    non_running_statuses: tuple[SpawnStatus, ...] = (
        "queued",
        "finalizing",
        "succeeded",
        "failed",
        "cancelled",
    )
    for start_status in non_running_statuses:
        spawn_id = str(
            start_spawn(
                runtime_root,
                chat_id=f"c-{start_status}",
                model="gpt-5.4",
                agent="coder",
                harness="codex",
                prompt="hello",
                status=start_status,
            )
        )
        assert mark_finalizing(runtime_root, spawn_id) is False
        row = get_spawn(runtime_root, spawn_id)
        assert row is not None
        assert row.status == start_status


def test_mark_finalizing_concurrent_race_only_one_writer_wins(tmp_path: Path) -> None:
    runtime_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(runtime_root)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _unused: mark_finalizing(runtime_root, spawn_id),
                (0, 1),
            )
        )

    assert sorted(results) == [False, True]
    row = get_spawn(runtime_root, spawn_id)
    assert row is not None
    assert row.status == "finalizing"


def test_projection_authority_reconciler_then_runner_replaces_terminal_tuple(
    tmp_path: Path,
) -> None:
    runtime_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(runtime_root)

    assert (
        finalize_spawn(
            runtime_root,
            spawn_id,
            status="failed",
            exit_code=1,
            origin="reconciler",
            error="orphan_run",
        )
        is True
    )
    assert (
        finalize_spawn(
            runtime_root,
            spawn_id,
            status="succeeded",
            exit_code=0,
            origin="runner",
            duration_secs=12.5,
        )
        is False
    )

    row = get_spawn(runtime_root, spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.error is None
    assert row.terminal_origin == "runner"
    assert row.duration_secs == 12.5


def test_finalize_spawn_reconciler_writes_through_finalizing_row(tmp_path: Path) -> None:
    runtime_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(runtime_root)
    assert mark_finalizing(runtime_root, spawn_id) is True

    wrote = finalize_spawn(
        runtime_root,
        spawn_id,
        status="failed",
        exit_code=1,
        origin="reconciler",
        error="orphan_finalization",
    )

    assert wrote is True
    row = get_spawn(runtime_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "orphan_finalization"


def test_finalize_spawn_reconciler_drops_when_row_already_terminal(tmp_path: Path) -> None:
    runtime_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(runtime_root)

    finalize_spawn(
        runtime_root,
        spawn_id,
        status="failed",
        exit_code=1,
        origin="runner",
        error="timeout",
    )
    wrote = finalize_spawn(
        runtime_root,
        spawn_id,
        status="succeeded",
        exit_code=0,
        origin="reconciler",
        duration_secs=999.0,
    )

    assert wrote is False
    row = get_spawn(runtime_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "timeout"
    assert row.duration_secs is None


def test_exited_event_is_non_terminal_and_projects_process_exit(tmp_path: Path) -> None:
    runtime_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(runtime_root)

    record_spawn_exited(
        runtime_root,
        spawn_id,
        exit_code=143,
        exited_at="2026-04-12T14:00:00Z",
    )

    row = get_spawn(runtime_root, spawn_id)
    assert row is not None
    assert row.status == "running"
    assert row.exited_at == "2026-04-12T14:00:00Z"
    assert row.process_exit_code == 143
    assert row.exit_code is None
