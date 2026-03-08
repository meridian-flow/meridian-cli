"""State-layer tests for file-authoritative stores."""


import dataclasses
import json
import multiprocessing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from meridian.lib.state.session_store import get_last_session, start_session, stop_session
from meridian.lib.state.space_store import create_space, get_space
from meridian.lib.state.artifact_store import InMemoryStore, LocalStore, make_artifact_key
from meridian.lib.state.spawn_store import next_spawn_id, next_chat_id, next_space_id
from meridian.lib.state.spawn_store import finalize_spawn, get_spawn, list_spawns, spawn_stats, start_spawn
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.core.types import SpawnId

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
