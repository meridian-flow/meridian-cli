import inspect
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast, get_args

import pytest

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.state.event_store import append_event
from meridian.lib.state.paths import StateRootPaths
from meridian.lib.state.spawn_store import (
    APP_LAUNCH_MODE,
    AUTHORITATIVE_ORIGINS,
    LaunchMode,
    SpawnExitedEvent,
    SpawnFinalizeEvent,
    SpawnStartEvent,
    SpawnOrigin,
    SpawnUpdateEvent,
    finalize_spawn,
    get_spawn,
    list_spawns,
    mark_finalizing,
    record_spawn_exited,
    start_spawn,
    update_spawn,
)
from tests.support.fakes import FakeClock, FakeSpawnRepository


def _state_root(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _start_test_spawn(state_root: Path) -> str:
    return str(
        start_spawn(
            state_root,
            chat_id="c1",
            model="gpt-5.4",
            agent="coder",
            harness="codex",
            prompt="hello",
        )
    )


def _write_mixed_valid_and_malformed_spawns_jsonl(state_root: Path) -> None:
    spawns_jsonl = state_root / "spawns.jsonl"
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


def test_spawn_origin_enum_is_complete() -> None:
    assert set(get_args(SpawnOrigin)) == {
        "runner",
        "launcher",
        "launch_failure",
        "cancel",
        "reconciler",
    }
    assert {
        "runner",
        "launcher",
        "launch_failure",
        "cancel",
    } == AUTHORITATIVE_ORIGINS


def test_launch_mode_enum_includes_app() -> None:
    assert set(get_args(LaunchMode)) == {
        "background",
        "foreground",
        "app",
    }


def test_start_spawn_accepts_app_launch_mode_and_projects_it(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = str(
        start_spawn(
            state_root,
            chat_id="c1",
            model="gpt-5.4",
            agent="coder",
            harness="codex",
            prompt="hello",
            launch_mode="app",
        )
    )

    row = get_spawn(state_root, spawn_id)

    assert row is not None
    assert row.launch_mode == "app"


def test_get_spawn_coerces_legacy_launch_mode_strings(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawns_jsonl = StateRootPaths.from_root_dir(state_root).spawns_jsonl
    spawns_jsonl.write_text(
        json.dumps(
            {
                "v": 1,
                "event": "start",
                "id": "p1",
                "chat_id": "c1",
                "model": "gpt-5.4",
                "agent": "coder",
                "harness": "codex",
                "status": "running",
                "started_at": "2026-03-01T00:00:00Z",
                "prompt": "hello",
                "launch_mode": " APP ",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    row = get_spawn(state_root, "p1")

    assert row is not None
    assert row.launch_mode == APP_LAUNCH_MODE


def test_finalize_spawn_requires_keyword_origin(tmp_path: Path) -> None:
    signature = inspect.signature(finalize_spawn)
    origin_param = signature.parameters["origin"]
    assert origin_param.kind is inspect.Parameter.KEYWORD_ONLY
    assert origin_param.default is inspect.Parameter.empty

    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)
    with pytest.raises(TypeError):
        finalize_spawn(state_root, spawn_id, status="succeeded", exit_code=0)


def test_update_spawn_is_metadata_only_and_rejects_status(tmp_path: Path) -> None:
    signature = inspect.signature(update_spawn)
    assert "status" not in signature.parameters

    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)
    with pytest.raises(TypeError):
        cast("Any", update_spawn)(state_root, spawn_id, status="running")


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


def test_start_spawn_accepts_injected_clock_and_repository(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    fake_clock = FakeClock(start=1_700_000_000.0)
    fake_repository = FakeSpawnRepository()

    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        clock=fake_clock,
        repository=fake_repository,
    )

    events = fake_repository.read_events()
    assert str(spawn_id) == "p1"
    assert len(events) == 1
    start_event = cast("SpawnStartEvent", events[0])
    assert start_event.started_at == fake_clock.utc_now_iso()
    assert start_event.id == "p1"


def test_record_spawn_exited_accepts_injected_clock_and_repository(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    fake_repository = FakeSpawnRepository()
    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        repository=fake_repository,
    )
    fake_clock = FakeClock(start=1_700_000_123.0)

    record_spawn_exited(
        state_root,
        spawn_id,
        exit_code=143,
        clock=fake_clock,
        repository=fake_repository,
    )

    events = fake_repository.read_events()
    assert len(events) == 2
    exited_event = cast("SpawnExitedEvent", events[-1])
    assert exited_event.exited_at == fake_clock.utc_now_iso()
    assert exited_event.exit_code == 143


def test_finalize_spawn_accepts_injected_clock_and_repository(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    fake_repository = FakeSpawnRepository()
    spawn_id = start_spawn(
        state_root,
        chat_id="c1",
        model="gpt-5.4",
        agent="coder",
        harness="codex",
        prompt="hello",
        repository=fake_repository,
    )
    fake_clock = FakeClock(start=1_700_000_222.0)

    wrote = finalize_spawn(
        state_root,
        spawn_id,
        status="succeeded",
        exit_code=0,
        origin="runner",
        clock=fake_clock,
        repository=fake_repository,
    )

    assert wrote is True
    events = fake_repository.read_events()
    assert len(events) == 2
    finalize_event = cast("SpawnFinalizeEvent", events[-1])
    assert finalize_event.finished_at == fake_clock.utc_now_iso()
    row = get_spawn(state_root, spawn_id, repository=fake_repository)
    assert row is not None
    assert row.status == "succeeded"


def test_mark_finalizing_returns_true_from_running(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

    assert mark_finalizing(state_root, spawn_id) is True

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "finalizing"


@pytest.mark.parametrize(
    "start_status",
    ["queued", "finalizing", "succeeded", "failed", "cancelled"],
)
def test_mark_finalizing_returns_false_for_non_running_states(
    tmp_path: Path,
    start_status: SpawnStatus,
) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = str(
        start_spawn(
            state_root,
            chat_id="c1",
            model="gpt-5.4",
            agent="coder",
            harness="codex",
            prompt="hello",
            status=start_status,
        )
    )

    assert mark_finalizing(state_root, spawn_id) is False
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == start_status


def test_mark_finalizing_returns_false_for_missing_row(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    assert mark_finalizing(state_root, "p-missing") is False


def test_mark_finalizing_concurrent_race_only_one_writer_wins(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _unused: mark_finalizing(state_root, spawn_id),
                (0, 1),
            )
        )

    assert sorted(results) == [False, True]
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "finalizing"


def test_projection_authority_reconciler_then_runner_replaces_terminal_tuple(
    tmp_path: Path,
) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

    assert (
        finalize_spawn(
            state_root,
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
            state_root,
            spawn_id,
            status="succeeded",
            exit_code=0,
            origin="runner",
            duration_secs=12.5,
        )
        is False
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.exit_code == 0
    assert row.error is None
    assert row.terminal_origin == "runner"
    assert row.duration_secs == 12.5


def test_projection_authority_runner_then_reconciler_does_not_override(
    tmp_path: Path,
) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

    finalize_spawn(
        state_root,
        spawn_id,
        status="failed",
        exit_code=1,
        origin="runner",
        error="timeout",
    )
    assert (
        finalize_spawn(
            state_root,
            spawn_id,
            status="succeeded",
            exit_code=0,
            origin="reconciler",
            duration_secs=9.0,
        )
        is False
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 1
    assert row.error == "timeout"
    assert row.terminal_origin == "runner"
    assert row.duration_secs is None


def test_projection_authority_reconciler_then_reconciler_first_wins(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

    finalize_spawn(
        state_root,
        spawn_id,
        status="failed",
        exit_code=1,
        origin="reconciler",
        error="orphan_run",
    )
    assert (
        finalize_spawn(
            state_root,
            spawn_id,
            status="succeeded",
            exit_code=0,
            origin="reconciler",
            duration_secs=4.0,
        )
        is False
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 1
    assert row.error == "orphan_run"
    assert row.terminal_origin == "reconciler"
    assert row.duration_secs is None


def test_projection_authority_runner_then_runner_first_wins(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

    finalize_spawn(
        state_root,
        spawn_id,
        status="cancelled",
        exit_code=130,
        origin="runner",
        error="cancelled",
    )
    finalize_spawn(
        state_root,
        spawn_id,
        status="succeeded",
        exit_code=0,
        origin="runner",
        duration_secs=3.2,
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "cancelled"
    assert row.exit_code == 130
    assert row.error == "cancelled"
    assert row.terminal_origin == "runner"
    assert row.duration_secs == 3.2


def test_late_update_status_never_downgrades_terminal_projection(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

    finalize_spawn(
        state_root,
        spawn_id,
        status="succeeded",
        exit_code=0,
        origin="runner",
    )
    paths = StateRootPaths.from_root_dir(state_root)
    append_event(
        paths.spawns_jsonl,
        paths.spawns_flock,
        SpawnUpdateEvent(
            id=spawn_id,
            status="finalizing",
            desc="post-finish metadata update",
        ),
        exclude_none=True,
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "succeeded"
    assert row.desc == "post-finish metadata update"


def test_projection_authority_override_clears_error_when_authoritative_error_missing(
    tmp_path: Path,
) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

    finalize_spawn(
        state_root,
        spawn_id,
        status="failed",
        exit_code=1,
        origin="reconciler",
        error="orphan_run",
    )
    finalize_spawn(
        state_root,
        spawn_id,
        status="failed",
        exit_code=9,
        origin="runner",
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 9
    assert row.error is None
    assert row.terminal_origin == "runner"


def test_finalize_spawn_reconciler_writes_through_finalizing_row(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)
    assert mark_finalizing(state_root, spawn_id) is True

    wrote = finalize_spawn(
        state_root,
        spawn_id,
        status="failed",
        exit_code=1,
        origin="reconciler",
        error="orphan_finalization",
    )

    assert wrote is True
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "orphan_finalization"


def test_finalize_spawn_reconciler_drops_when_row_already_terminal(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

    finalize_spawn(
        state_root,
        spawn_id,
        status="failed",
        exit_code=1,
        origin="runner",
        error="timeout",
    )
    wrote = finalize_spawn(
        state_root,
        spawn_id,
        status="succeeded",
        exit_code=0,
        origin="reconciler",
        duration_secs=999.0,
    )

    assert wrote is False
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.error == "timeout"
    assert row.duration_secs is None


def test_exited_event_is_non_terminal_and_projects_process_exit(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)

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
    spawn_id = str(
        start_spawn(
            state_root,
            chat_id="c1",
            model="gpt-5.4",
            agent="coder",
            harness="codex",
            prompt="hello",
            runner_pid=1111,
        )
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.runner_pid == 1111

    update_spawn(state_root, spawn_id, runner_pid=2222)
    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.runner_pid == 2222
