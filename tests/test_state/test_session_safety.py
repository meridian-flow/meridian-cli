from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
from typing import Any, BinaryIO

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


def _start_and_stop_session_worker(
    state_root_str: str, idx: int, queue: multiprocessing.Queue[str]
) -> None:
    state_root = Path(state_root_str)
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id=f"session-{idx}",
        model="gpt-5.4",
    )
    queue.put(chat_id)
    session_store.stop_session(state_root, chat_id)


def _reserve_chat_id_worker(state_root_str: str, queue: multiprocessing.Queue[str]) -> None:
    state_root = Path(state_root_str)
    queue.put(session_store.reserve_chat_id(state_root))


def _can_acquire_lock_nonblocking_worker(
    lock_path_str: str, queue: multiprocessing.Queue[bool]
) -> None:
    lock_path = Path(lock_path_str)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        try:
            session_store.fcntl.flock(
                handle.fileno(),
                session_store.fcntl.LOCK_EX | session_store.fcntl.LOCK_NB,
            )
        except BlockingIOError:
            queue.put(False)
            return
        session_store.fcntl.flock(handle.fileno(), session_store.fcntl.LOCK_UN)
        queue.put(True)


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
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _state_root(tmp_path)

    def _raise_lock_error(_: Path) -> BinaryIO:
        raise RuntimeError("lock failed")

    monkeypatch.setattr(session_store, "_acquire_session_lock", _raise_lock_error)

    with pytest.raises(RuntimeError, match="lock failed"):
        session_store.start_session(
            state_root,
            harness="codex",
            harness_session_id="thread-1",
            model="gpt-5.4",
        )

    assert not (state_root / "sessions.jsonl").exists()


def test_acquire_session_lock_retries_when_lock_file_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _state_root(tmp_path)
    lock_path = state_root / "sessions" / "c123.lock"
    real_flock = session_store.fcntl.flock
    observed = {"lock_ex_calls": 0, "replaced": False}

    def _flock_with_unlink(fd: int, operation: int) -> None:
        if operation == session_store.fcntl.LOCK_EX:
            observed["lock_ex_calls"] += 1
            if not observed["replaced"]:
                observed["replaced"] = True
                lock_path.unlink(missing_ok=True)
                lock_path.touch()
        real_flock(fd, operation)

    monkeypatch.setattr(session_store.fcntl, "flock", _flock_with_unlink)

    handle = session_store._acquire_session_lock(lock_path)
    try:
        handle_stat = session_store.os.fstat(handle.fileno())
        path_stat = lock_path.stat()
        assert observed["replaced"] is True
        assert observed["lock_ex_calls"] >= 2
        assert handle_stat.st_ino == path_stat.st_ino
        assert handle_stat.st_dev == path_stat.st_dev
    finally:
        session_store.fcntl.flock(handle.fileno(), session_store.fcntl.LOCK_UN)
        handle.close()


def test_start_session_acquires_lifetime_lock_before_appending_start_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _state_root(tmp_path)
    original_append_event = session_store.append_event
    observed = {"checked": False}

    def _append_event_with_lock_check(*args: object, **kwargs: object) -> None:
        event = kwargs.get("event")
        if event is None and len(args) >= 3:
            event = args[2]
        if isinstance(event, session_store.SessionStartEvent):
            ctx, queue = _spawn_queue_or_skip()
            lock_path = state_root / "sessions" / f"{event.chat_id}.lock"
            proc = ctx.Process(
                target=_can_acquire_lock_nonblocking_worker,
                args=(lock_path.as_posix(), queue),
            )
            _start_process_or_skip(proc)
            proc.join(timeout=20)
            assert proc.exitcode == 0
            assert queue.get(timeout=5) is False
            observed["checked"] = True
        original_append_event(*args, **kwargs)

    monkeypatch.setattr(session_store, "append_event", _append_event_with_lock_check)

    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="thread-ordered",
        model="gpt-5.4",
    )
    assert observed["checked"] is True

    session_store.stop_session(state_root, chat_id)


def test_start_session_rolls_back_lock_and_event_on_append_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _state_root(tmp_path)
    chat_id = "c99"

    def _raise_append_error(*_: object, **__: object) -> None:
        raise RuntimeError("append failed")

    monkeypatch.setattr(session_store, "append_event", _raise_append_error)

    with pytest.raises(RuntimeError, match="append failed"):
        session_store.start_session(
            state_root,
            harness="codex",
            harness_session_id="thread-fail",
            model="gpt-5.4",
            chat_id=chat_id,
        )

    assert not (state_root / "sessions.jsonl").exists()
    assert not (state_root / "sessions" / f"{chat_id}.lease.json").exists()
    assert (
        session_store._session_lock_key(state_root, chat_id)
        not in session_store._SESSION_LOCK_HANDLES
    )

    ctx, queue = _spawn_queue_or_skip()
    lock_path = state_root / "sessions" / f"{chat_id}.lock"
    proc = ctx.Process(
        target=_can_acquire_lock_nonblocking_worker,
        args=(lock_path.as_posix(), queue),
    )
    _start_process_or_skip(proc)
    proc.join(timeout=20)
    assert proc.exitcode == 0
    assert queue.get(timeout=5) is True


def test_start_session_includes_null_forked_from_chat_id_by_default(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="thread-fork-default",
        model="gpt-5.4",
    )
    session_store.stop_session(state_root, chat_id)

    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    start_rows = [
        row for row in rows if row.get("event") == "start" and row.get("chat_id") == chat_id
    ]
    assert len(start_rows) == 1
    assert "forked_from_chat_id" in start_rows[0]
    assert start_rows[0]["forked_from_chat_id"] is None


def test_cleanup_stale_sessions_skips_generation_mismatch(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    chat_id = "c7"
    _write_session_start(
        state_root=state_root,
        chat_id=chat_id,
        session_instance_id="new-generation",
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
                "session_instance_id": "old-generation",
            }
        ),
        encoding="utf-8",
    )

    cleanup = session_store.cleanup_stale_sessions(state_root)

    assert cleanup.cleaned_ids == ()
    assert lock_path.exists()
    assert lease_path.exists()
    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [
        row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id
    ]
    assert stop_rows == []


def test_cleanup_stale_sessions_stops_and_cleans_when_generation_matches(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    chat_id = "c8"
    session_instance_id = "matching-generation"
    _write_session_start(
        state_root=state_root,
        chat_id=chat_id,
        session_instance_id=session_instance_id,
        harness="claude",
    )

    lock_path = state_root / "sessions" / f"{chat_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    lease_path = state_root / "sessions" / f"{chat_id}.lease.json"
    lease_path.write_text(
        json.dumps(
            {
                "chat_id": chat_id,
                "owner_pid": 456,
                "session_instance_id": session_instance_id,
            }
        ),
        encoding="utf-8",
    )

    cleanup = session_store.cleanup_stale_sessions(state_root)

    assert cleanup.cleaned_ids == (chat_id,)
    assert cleanup.materialized_scopes == ("claude",)
    assert not lock_path.exists()
    assert not lease_path.exists()
    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [
        row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id
    ]
    assert len(stop_rows) == 1
    assert stop_rows[0]["session_instance_id"] == session_instance_id


def test_cleanup_stale_sessions_skips_primary_sessions(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    chat_id = "c9"
    session_instance_id = "primary-generation"
    _write_session_start(
        state_root=state_root,
        chat_id=chat_id,
        session_instance_id=session_instance_id,
        harness="claude",
        kind="primary",
    )

    lock_path = state_root / "sessions" / f"{chat_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    lease_path = state_root / "sessions" / f"{chat_id}.lease.json"
    lease_path.write_text(
        json.dumps(
            {
                "chat_id": chat_id,
                "owner_pid": 789,
                "session_instance_id": session_instance_id,
            }
        ),
        encoding="utf-8",
    )

    cleanup = session_store.cleanup_stale_sessions(state_root)

    assert cleanup.cleaned_ids == ()
    assert cleanup.materialized_scopes == ()
    assert lock_path.exists()
    assert lease_path.exists()
    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [
        row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id
    ]
    assert stop_rows == []


def test_records_by_session_ignores_mismatched_generation_stop_and_update(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    with (state_root / "sessions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "start",
                    "chat_id": "c10",
                    "harness": "codex",
                    "harness_session_id": "thread-1",
                    "model": "gpt-5.4",
                    "session_instance_id": "gen-a",
                    "started_at": "2026-03-01T00:00:00Z",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "update",
                    "chat_id": "c10",
                    "harness_session_id": "thread-2",
                    "session_instance_id": "gen-a",
                    "active_work_id": "work-1",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "update",
                    "chat_id": "c10",
                    "harness_session_id": "thread-ignored",
                    "session_instance_id": "gen-b",
                    "active_work_id": "work-ignored",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "stop",
                    "chat_id": "c10",
                    "session_instance_id": "gen-b",
                    "stopped_at": "2026-03-01T00:01:00Z",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )

    record = session_store._records_by_session(state_root)["c10"]
    assert record.harness_session_id == "thread-2"
    assert record.harness_session_ids == ("thread-1", "thread-2")
    assert record.active_work_id == "work-1"
    assert record.forked_from_chat_id is None
    assert record.stopped_at is None


def test_concurrent_start_session_allocates_unique_chat_ids(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    process_count = 8
    ctx, queue = _spawn_queue_or_skip()
    procs = [
        ctx.Process(
            target=_start_and_stop_session_worker,
            args=(state_root.as_posix(), idx, queue),
        )
        for idx in range(process_count)
    ]
    for proc in procs:
        _start_process_or_skip(proc)
    for proc in procs:
        proc.join(timeout=20)
        assert proc.exitcode == 0

    allocated = sorted(queue.get(timeout=5) for _ in range(process_count))
    assert len(allocated) == process_count
    assert len(set(allocated)) == process_count
