from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
from typing import Any

import pytest

from meridian.lib.state import session_store


def _spawn_queue_or_skip() -> tuple[Any, multiprocessing.Queue[Any]]:
    ctx = multiprocessing.get_context("spawn")
    try:
        queue: multiprocessing.Queue[Any] = ctx.Queue()
    except PermissionError as exc:
        pytest.skip(f"multiprocessing semaphore unavailable in this environment: {exc}")
    return ctx, queue


def _start_process_or_skip(proc: Any) -> None:
    try:
        proc.start()
    except PermissionError as exc:
        pytest.skip(f"multiprocessing semaphore unavailable in this environment: {exc}")


def _state_root(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _reserve_chat_id_worker(state_root_str: str, queue: multiprocessing.Queue[str]) -> None:
    state_root = Path(state_root_str)
    queue.put(session_store.reserve_chat_id(state_root))

def _write_session_start(
    *,
    state_root: Path,
    chat_id: str,
    session_instance_id: str,
    harness: str = "codex",
    kind: str = "spawn",
) -> None:
    with (state_root / "sessions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "start",
                    "chat_id": chat_id,
                    "kind": kind,
                    "harness": harness,
                    "harness_session_id": f"{chat_id}-thread",
                    "model": "gpt-5.4",
                    "session_instance_id": session_instance_id,
                    "started_at": "2026-03-01T00:00:00Z",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )


def test_reserve_chat_id_is_safe_under_concurrency(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    process_count = 8
    ctx, queue = _spawn_queue_or_skip()
    procs = [
        ctx.Process(
            target=_reserve_chat_id_worker,
            args=(state_root.as_posix(), queue),
        )
        for _ in range(process_count)
    ]
    for proc in procs:
        _start_process_or_skip(proc)
    for proc in procs:
        proc.join(timeout=20)
        assert proc.exitcode == 0

    allocated = sorted(queue.get(timeout=5) for _ in range(process_count))
    assert allocated == [f"c{idx}" for idx in range(1, process_count + 1)]
    assert (state_root / "session-id-counter").read_text(encoding="utf-8") == f"{process_count}\n"


def test_start_session_does_not_append_start_event_when_lock_acquire_fails(
    tmp_path: Path,
) -> None:
    state_root = _state_root(tmp_path)
    sessions_dir_as_file = state_root / "sessions"
    sessions_dir_as_file.write_text("not-a-directory\n", encoding="utf-8")

    with pytest.raises(OSError):
        session_store.start_session(
            state_root,
            harness="codex",
            harness_session_id="thread-1",
            model="gpt-5.4",
        )

    assert not (state_root / "sessions.jsonl").exists()


@pytest.mark.parametrize(
    (
        "chat_id",
        "kind",
        "harness",
        "start_generation",
        "lease_generation",
        "expected_cleaned",
        "expected_materialized",
        "expect_lock_exists",
        "expect_lease_exists",
        "expected_stop_count",
    ),
    [
        pytest.param(
            "c7",
            "spawn",
            "codex",
            "new-generation",
            "old-generation",
            (),
            (),
            True,
            True,
            0,
            id="skips-generation-mismatch",
        ),
        pytest.param(
            "c8",
            "spawn",
            "claude",
            "matching-generation",
            "matching-generation",
            ("c8",),
            ("claude",),
            False,
            False,
            1,
            id="stops-and-cleans-when-generation-matches",
        ),
        pytest.param(
            "c9",
            "primary",
            "claude",
            "primary-generation",
            "primary-generation",
            (),
            (),
            True,
            True,
            0,
            id="skips-primary-sessions",
        ),
    ],
)
def test_cleanup_stale_sessions_handles_generation_and_kind_rules(
    tmp_path: Path,
    chat_id: str,
    kind: str,
    harness: str,
    start_generation: str,
    lease_generation: str,
    expected_cleaned: tuple[str, ...],
    expected_materialized: tuple[str, ...],
    expect_lock_exists: bool,
    expect_lease_exists: bool,
    expected_stop_count: int,
) -> None:
    state_root = _state_root(tmp_path)
    _write_session_start(
        state_root=state_root,
        chat_id=chat_id,
        session_instance_id=start_generation,
        harness=harness,
        kind=kind,
    )

    lock_path = state_root / "sessions" / f"{chat_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    lease_path = state_root / "sessions" / f"{chat_id}.lease.json"
    lease_path.write_text(
        json.dumps(
            {
                "chat_id": chat_id,
                "owner_pid": 123,
                "session_instance_id": lease_generation,
            }
        ),
        encoding="utf-8",
    )

    cleanup = session_store.cleanup_stale_sessions(state_root)

    assert cleanup.cleaned_ids == expected_cleaned
    assert cleanup.materialized_scopes == expected_materialized
    assert lock_path.exists() is expect_lock_exists
    assert lease_path.exists() is expect_lease_exists

    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [
        row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id
    ]
    assert len(stop_rows) == expected_stop_count
    if expected_stop_count == 1:
        assert stop_rows[0]["session_instance_id"] == start_generation
