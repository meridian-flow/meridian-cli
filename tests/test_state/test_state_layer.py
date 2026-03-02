"""State-layer tests for file-authoritative stores."""

from __future__ import annotations

import dataclasses
import json
import multiprocessing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from meridian.lib.domain import PinnedFile, Spawn, Space, Span, WorkflowEvent
from meridian.lib.space.session_store import get_last_session, start_session, stop_session
from meridian.lib.space.space_file import create_space, get_space, update_space_status
from meridian.lib.state.artifact_store import InMemoryStore, LocalStore, make_artifact_key
from meridian.lib.state.id_gen import next_spawn_id, next_chat_id, next_space_id
from meridian.lib.state.spawn_store import finalize_spawn, get_spawn, list_spawns, spawn_stats, start_spawn
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.types import SpawnId, SpanId, TraceId


def _write_start_and_finalize(repo_root: str, space_id: str, idx: int) -> None:
    root = Path(repo_root)
    space_dir = resolve_space_dir(root, space_id)
    spawn_id = SpawnId(f"rlock{idx}")
    start_spawn(
        space_dir,
        spawn_id=spawn_id,
        chat_id=f"c{idx}",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt=f"job-{idx}",
        started_at="2026-02-25T00:00:00Z",
    )
    finalize_spawn(
        space_dir,
        spawn_id,
        "succeeded",
        0,
        duration_secs=0.1,
        finished_at="2026-02-25T00:00:01Z",
    )


def test_space_and_run_crud_with_file_backed_stores(tmp_path: Path) -> None:
    space = create_space(tmp_path, name="writer-room")
    space_dir = resolve_space_dir(tmp_path, space.id)

    assert space.id == "s1"
    assert get_space(tmp_path, space.id) is not None

    run_1 = start_spawn(
        space_dir,
        chat_id="c1",
        model="claude-opus-4-6",
        agent="planner",
        harness="claude",
        prompt="standalone",
    )
    run_2 = start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="space-1",
    )

    finalize_spawn(space_dir, run_1, "failed", 1)
    finalize_spawn(space_dir, run_2, "succeeded", 0, input_tokens=10, output_tokens=20)

    loaded = get_spawn(space_dir, run_2)
    assert loaded is not None
    assert loaded.prompt == "space-1"
    assert loaded.status == "succeeded"
    assert loaded.input_tokens == 10
    assert loaded.output_tokens == 20

    summaries = list_spawns(space_dir, filters={"model": "gpt-5.3-codex"})
    assert [summary.id for summary in summaries] == ["r2"]


def test_space_status_transitions_and_finish_timestamp(tmp_path: Path) -> None:
    space = create_space(tmp_path, name="status")

    closed = update_space_status(tmp_path, space.id, "closed")
    assert closed.status == "closed"
    assert closed.finished_at is not None

    reopened = update_space_status(tmp_path, space.id, "active")
    assert reopened.status == "active"
    assert reopened.finished_at is None


def test_run_stats_aggregate_duration_cost_and_tokens(tmp_path: Path) -> None:
    space = create_space(tmp_path, name="stats")
    space_dir = resolve_space_dir(tmp_path, space.id)

    r1 = start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="a",
    )
    r2 = start_spawn(
        space_dir,
        chat_id="c2",
        model="claude-sonnet-4-6",
        agent="reviewer",
        harness="claude",
        prompt="b",
    )

    finalize_spawn(
        space_dir,
        r1,
        "succeeded",
        0,
        duration_secs=4.0,
        total_cost_usd=0.1,
        input_tokens=100,
        output_tokens=50,
    )
    finalize_spawn(
        space_dir,
        r2,
        "failed",
        1,
        duration_secs=6.0,
        total_cost_usd=0.2,
        input_tokens=20,
        output_tokens=10,
    )

    stats = spawn_stats(space_dir)
    assert stats["total_runs"] == 2
    assert stats["by_status"] == {"failed": 1, "succeeded": 1}
    assert stats["by_model"] == {"claude-sonnet-4-6": 1, "gpt-5.3-codex": 1}
    assert stats["total_duration_secs"] == 10.0
    assert stats["total_cost_usd"] == pytest.approx(0.3)
    assert stats["total_input_tokens"] == 120
    assert stats["total_output_tokens"] == 60


def test_session_store_round_trip(tmp_path: Path) -> None:
    space = create_space(tmp_path, name="sessions")
    space_dir = resolve_space_dir(tmp_path, space.id)

    chat_id = start_session(
        space_dir,
        harness="codex",
        harness_session_id="sess-1",
        model="gpt-5.3-codex",
        params=("--foo", "bar"),
    )

    last = get_last_session(space_dir)
    assert last is not None
    assert last.chat_id == chat_id
    assert last.harness_session_id == "sess-1"
    assert last.stopped_at is None

    stop_session(space_dir, chat_id)
    stopped = get_last_session(space_dir)
    assert stopped is not None
    assert stopped.stopped_at is not None


def test_locking_contention_writes_clean_jsonl(tmp_path: Path) -> None:
    space = create_space(tmp_path, name="locks")
    process_count = 8

    ctx = multiprocessing.get_context("spawn")
    procs = [
        ctx.Process(target=_write_start_and_finalize, args=(tmp_path.as_posix(), space.id, idx))
        for idx in range(process_count)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=20)
        assert proc.exitcode == 0

    space_dir = resolve_space_dir(tmp_path, space.id)
    rows = list_spawns(space_dir)
    assert len(rows) == process_count
    assert all(row.status == "succeeded" for row in rows)

    # Every line must remain parseable JSON under concurrent append pressure.
    with (space_dir / "spawns.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            json.loads(line)


def test_id_generation_uses_s_r_c_prefixes(tmp_path: Path) -> None:
    assert str(next_space_id(tmp_path)) == "s1"

    space = create_space(tmp_path, name="idgen")
    space_dir = resolve_space_dir(tmp_path, space.id)

    assert str(next_spawn_id(space_dir)) == "r1"
    assert next_chat_id(space_dir) == "c1"

    start_spawn(
        space_dir,
        chat_id="c1",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt="first",
    )
    assert str(next_spawn_id(space_dir)) == "r2"


def test_artifact_store_local_and_memory(tmp_path: Path) -> None:
    key = make_artifact_key(SpawnId("r1"), "output.jsonl")

    local = LocalStore(root_dir=tmp_path / "artifacts")
    local.put(key, b"hello")
    assert local.exists(key)
    assert local.get(key) == b"hello"
    assert local.list_artifacts("r1") == [key]
    local.delete(key)
    assert not local.exists(key)

    memory = InMemoryStore()
    memory.put(key, b"world")
    assert memory.exists(key)
    assert memory.get(key) == b"world"
    assert memory.list_artifacts("r1") == [key]
    memory.delete(key)
    assert not memory.exists(key)


def test_domain_dataclasses_are_frozen() -> None:
    for cls in (Spawn, Space, PinnedFile, WorkflowEvent, Span):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen

    span = Span(
        span_id=SpanId("span-1"),
        trace_id=TraceId("trace-1"),
        name="spawn",
        kind="workflow",
        started_at=datetime.now(UTC),
    )
    assert span.status == "ok"
