"""State-layer tests for file-authoritative stores."""


import json
import multiprocessing
from pathlib import Path

import pytest

from meridian.lib.state.spawn_store import finalize_spawn, list_spawns, start_spawn
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.core.types import SpawnId

def _write_start_and_finalize(repo_root: str, idx: int) -> None:
    root = Path(repo_root)
    state_root = resolve_state_paths(root).root_dir
    spawn_id = SpawnId(f"rlock{idx}")
    start_spawn(
        state_root,
        spawn_id=spawn_id,
        chat_id=f"c{idx}",
        model="gpt-5.3-codex",
        agent="coder",
        harness="codex",
        prompt=f"job-{idx}",
        started_at="2026-02-25T00:00:00Z",
    )
    finalize_spawn(
        state_root,
        spawn_id,
        "succeeded",
        0,
        duration_secs=0.1,
        finished_at="2026-02-25T00:00:01Z",
    )

def test_locking_contention_writes_clean_jsonl(tmp_path: Path) -> None:
    state_root = tmp_path / ".meridian"
    state_root.mkdir(parents=True, exist_ok=True)
    process_count = 8

    ctx = multiprocessing.get_context("spawn")
    procs = [
        ctx.Process(target=_write_start_and_finalize, args=(tmp_path.as_posix(), idx))
        for idx in range(process_count)
    ]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=20)
        assert proc.exitcode == 0

    rows = list_spawns(state_root)
    assert len(rows) == process_count
    assert all(row.status == "succeeded" for row in rows)

    # Every line must remain parseable JSON under concurrent append pressure.
    with (state_root / "spawns.jsonl").open("r", encoding="utf-8") as handle:
        for line in handle:
            json.loads(line)
