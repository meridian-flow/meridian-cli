import inspect
import json
from pathlib import Path
from typing import Any, get_args

import pytest

from meridian.lib.state.spawn_store import (
    AUTHORITATIVE_ORIGINS,
    LEGACY_RECONCILER_ERRORS,
    SpawnFinalizeEvent,
    SpawnOrigin,
    finalize_spawn,
    get_spawn,
    list_spawns,
    record_spawn_exited,
    resolve_finalize_origin,
    start_spawn,
    update_spawn,
)


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
    assert {
        "orphan_run",
        "orphan_finalization",
        "missing_worker_pid",
        "harness_completed",
    } == LEGACY_RECONCILER_ERRORS


def test_finalize_spawn_requires_keyword_origin(tmp_path: Path) -> None:
    signature = inspect.signature(finalize_spawn)
    origin_param = signature.parameters["origin"]
    assert origin_param.kind is inspect.Parameter.KEYWORD_ONLY
    assert origin_param.default is inspect.Parameter.empty

    state_root = _state_root(tmp_path)
    spawn_id = _start_test_spawn(state_root)
    with pytest.raises(TypeError):
        finalize_spawn(state_root, spawn_id, status="succeeded", exit_code=0)


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
    finalize_spawn(
        state_root,
        spawn_id,
        status="succeeded",
        exit_code=0,
        origin="reconciler",
        duration_secs=9.0,
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 1
    assert row.error == "timeout"
    assert row.terminal_origin == "runner"
    assert row.duration_secs == 9.0


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
    finalize_spawn(
        state_root,
        spawn_id,
        status="succeeded",
        exit_code=0,
        origin="reconciler",
        duration_secs=4.0,
    )

    row = get_spawn(state_root, spawn_id)
    assert row is not None
    assert row.status == "failed"
    assert row.exit_code == 1
    assert row.error == "orphan_run"
    assert row.terminal_origin == "reconciler"
    assert row.duration_secs == 4.0


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


def test_resolve_finalize_origin_prefers_explicit_origin() -> None:
    event = SpawnFinalizeEvent(
        id="p1",
        status="failed",
        exit_code=1,
        error="orphan_run",
        origin="cancel",
    )
    assert resolve_finalize_origin(event) == "cancel"


def test_resolve_finalize_origin_maps_legacy_reconciler_errors() -> None:
    event = SpawnFinalizeEvent(
        id="p1",
        status="failed",
        exit_code=1,
        error="orphan_run",
    )
    assert resolve_finalize_origin(event) == "reconciler"


def test_resolve_finalize_origin_defaults_legacy_rows_to_runner() -> None:
    event = SpawnFinalizeEvent(
        id="p1",
        status="failed",
        exit_code=1,
        error="timeout",
    )
    assert resolve_finalize_origin(event) == "runner"


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


def _paired_orphan_run_then_succeeded_finalize_ids(events: list[dict[str, Any]]) -> list[str]:
    per_spawn: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        if event.get("event") != "finalize":
            continue
        spawn_id = str(event.get("id", "")).strip()
        if not spawn_id:
            continue
        per_spawn.setdefault(spawn_id, []).append(event)

    paired: list[str] = []
    for spawn_id, finalize_events in per_spawn.items():
        saw_orphan_run = False
        for event in finalize_events:
            if event.get("error") == "orphan_run":
                saw_orphan_run = True
            if saw_orphan_run and event.get("status") == "succeeded":
                paired.append(spawn_id)
                break
    return sorted(paired)


def test_backfill_regression_live_state_rows_project_to_succeeded(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    source_jsonl = repo_root / ".meridian" / "spawns.jsonl"
    if not source_jsonl.is_file():
        pytest.skip("Live .meridian/spawns.jsonl not present in this workspace.")

    state_root = _state_root(tmp_path)
    target_jsonl = state_root / "spawns.jsonl"
    target_jsonl.write_text(source_jsonl.read_text(encoding="utf-8"), encoding="utf-8")

    projected = {row.id: row for row in list_spawns(state_root)}
    required_ids = ("p1711", "p1712", "p1731", "p1732")
    for spawn_id in required_ids:
        assert spawn_id in projected, f"expected {spawn_id} to exist in live spawns.jsonl"
        assert projected[spawn_id].status == "succeeded"

    parsed_events: list[dict[str, Any]] = []
    for line in source_jsonl.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            parsed_events.append(event)

    paired_ids = _paired_orphan_run_then_succeeded_finalize_ids(parsed_events)
    for spawn_id in paired_ids:
        row = projected.get(spawn_id)
        assert row is not None, f"missing projected row for paired finalize spawn {spawn_id}"
        assert row.status == "succeeded"
