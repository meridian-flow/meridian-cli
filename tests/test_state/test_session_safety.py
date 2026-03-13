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


def _start_and_stop_session_worker(state_root_str: str, idx: int, queue: multiprocessing.Queue[str]) -> None:
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


def _can_acquire_lock_nonblocking_worker(lock_path_str: str, queue: multiprocessing.Queue[bool]) -> None:
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
) -> None:
    with (state_root / "sessions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "start",
                    "chat_id": chat_id,
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


def test_reserve_chat_id_uses_counter_file(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    assert session_store.reserve_chat_id(state_root) == "c1"
    assert session_store.reserve_chat_id(state_root) == "c2"
    assert (state_root / "session-id-counter").read_text(encoding="utf-8") == "2\n"


def test_reserve_chat_id_creates_counter_and_lock_files(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    counter_path = state_root / "session-id-counter"
    counter_lock_path = state_root / "session-id-counter.lock"
    assert not counter_path.exists()
    assert not counter_lock_path.exists()

    assert session_store.reserve_chat_id(state_root) == "c1"
    assert counter_path.read_text(encoding="utf-8") == "1\n"
    assert counter_lock_path.exists()


def test_reserve_chat_id_recovers_from_corrupted_counter_file(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    (state_root / "session-id-counter").write_text("not-a-number\n", encoding="utf-8")

    assert session_store.reserve_chat_id(state_root) == "c1"
    assert session_store.reserve_chat_id(state_root) == "c2"
    assert (state_root / "session-id-counter").read_text(encoding="utf-8") == "2\n"


def test_reserve_chat_id_seeds_counter_from_existing_start_events_on_first_use(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    _write_session_start(state_root=state_root, chat_id="c2", session_instance_id="gen-2")
    _write_session_start(state_root=state_root, chat_id="legacy", session_instance_id="gen-legacy")
    _write_session_start(state_root=state_root, chat_id="c10", session_instance_id="gen-10")
    with (state_root / "sessions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "stop",
                    "chat_id": "c99",
                    "session_instance_id": "gen-99",
                    "stopped_at": "2026-03-01T00:01:00Z",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )

    assert not (state_root / "session-id-counter").exists()

    assert session_store.reserve_chat_id(state_root) == "c11"
    assert session_store.reserve_chat_id(state_root) == "c12"
    assert (state_root / "session-id-counter").read_text(encoding="utf-8") == "12\n"


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

    allocated = sorted((queue.get(timeout=5) for _ in range(process_count)))
    assert allocated == [f"c{idx}" for idx in range(1, process_count + 1)]
    assert (state_root / "session-id-counter").read_text(encoding="utf-8") == f"{process_count}\n"


def test_start_stop_session_writes_and_removes_lease(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="thread-1",
        model="gpt-5.4",
    )
    lease_path = state_root / "sessions" / f"{chat_id}.lease.json"
    lease_payload = json.loads(lease_path.read_text(encoding="utf-8"))

    assert lease_payload["chat_id"] == chat_id
    assert isinstance(lease_payload.get("owner_pid"), int)
    session_instance_id = lease_payload.get("session_instance_id")
    assert isinstance(session_instance_id, str)
    assert session_instance_id

    session_store.stop_session(state_root, chat_id)

    assert not lease_path.exists()
    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id]
    assert len(stop_rows) == 1
    assert stop_rows[0]["session_instance_id"] == session_instance_id


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
    assert session_store._session_lock_key(state_root, chat_id) not in session_store._SESSION_LOCK_HANDLES

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


def test_start_update_stop_events_include_session_instance_id(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="thread-1",
        model="gpt-5.4",
    )
    lease_payload = json.loads((state_root / "sessions" / f"{chat_id}.lease.json").read_text(encoding="utf-8"))
    session_instance_id = lease_payload["session_instance_id"]

    session_store.update_session_harness_id(state_root, chat_id, "thread-2")
    session_store.update_session_work_id(state_root, chat_id, "work-9")
    session_store.stop_session(state_root, chat_id)

    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows_for_chat = [row for row in rows if row.get("chat_id") == chat_id]
    assert rows_for_chat
    for row in rows_for_chat:
        assert "session_instance_id" in row
        assert row["session_instance_id"] == session_instance_id


def test_update_events_use_in_memory_session_instance_id(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="thread-1",
        model="gpt-5.4",
    )
    lease_path = state_root / "sessions" / f"{chat_id}.lease.json"
    lease_payload = json.loads(lease_path.read_text(encoding="utf-8"))
    session_instance_id = lease_payload["session_instance_id"]

    lease_payload["session_instance_id"] = "tampered-lease-generation"
    lease_path.write_text(json.dumps(lease_payload) + "\n", encoding="utf-8")

    session_store.update_session_harness_id(state_root, chat_id, "thread-2")
    session_store.update_session_work_id(state_root, chat_id, "work-1")
    session_store.stop_session(state_root, chat_id)

    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    update_rows = [row for row in rows if row.get("event") == "update" and row.get("chat_id") == chat_id]
    assert len(update_rows) == 2
    for row in update_rows:
        assert row["session_instance_id"] == session_instance_id

    stop_rows = [row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id]
    assert len(stop_rows) == 1
    assert stop_rows[0]["session_instance_id"] == session_instance_id


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
    stop_rows = [row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id]
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
    stop_rows = [row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id]
    assert len(stop_rows) == 1
    assert stop_rows[0]["session_instance_id"] == session_instance_id


def test_records_load_without_session_instance_id_for_backward_compat(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    with (state_root / "sessions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "start",
                    "chat_id": "c1",
                    "harness": "codex",
                    "harness_session_id": "legacy-thread",
                    "model": "gpt-5.4",
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
                    "chat_id": "c1",
                    "harness_session_id": "legacy-thread-2",
                    "active_work_id": "work-1",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )

    record = session_store.resolve_session_ref(state_root, "legacy-thread-2")
    assert record is not None
    assert record.chat_id == "c1"
    assert record.session_instance_id == ""
    assert record.active_work_id == "work-1"


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
    assert record.stopped_at is None


def test_cleanup_stale_sessions_cleans_legacy_session_without_lease(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    chat_id = "c11"
    _write_session_start(
        state_root=state_root,
        chat_id=chat_id,
        session_instance_id="legacy-generation",
        harness="codex",
    )
    lock_path = state_root / "sessions" / f"{chat_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()

    cleanup = session_store.cleanup_stale_sessions(state_root)

    assert cleanup.cleaned_ids == (chat_id,)
    assert cleanup.materialized_scopes == ("codex",)
    assert not lock_path.exists()
    assert not (state_root / "sessions" / f"{chat_id}.lease.json").exists()
    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id]
    assert len(stop_rows) == 1
    assert stop_rows[0]["session_instance_id"] == "legacy-generation"


def test_cleanup_stale_sessions_skips_currently_locked_session(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="thread-live",
        model="gpt-5.4",
    )

    cleanup = session_store.cleanup_stale_sessions(state_root)

    assert cleanup.cleaned_ids == ()
    assert cleanup.materialized_scopes == ()
    assert (state_root / "sessions" / f"{chat_id}.lock").exists()
    assert (state_root / "sessions" / f"{chat_id}.lease.json").exists()
    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id]
    assert stop_rows == []

    session_store.stop_session(state_root, chat_id)


def test_stop_session_without_start_uses_empty_generation(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    session_store.stop_session(state_root, "c404")

    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    stop_row = rows[0]
    assert stop_row["event"] == "stop"
    assert stop_row["chat_id"] == "c404"
    assert stop_row["session_instance_id"] == ""
    assert isinstance(stop_row["stopped_at"], str)


def test_double_stop_appends_events_with_same_generation(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="thread-double-stop",
        model="gpt-5.4",
    )
    start_rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    start_row = next(row for row in start_rows if row.get("event") == "start" and row.get("chat_id") == chat_id)
    session_instance_id = start_row["session_instance_id"]

    session_store.stop_session(state_root, chat_id)
    session_store.stop_session(state_root, chat_id)

    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [row for row in rows if row.get("event") == "stop" and row.get("chat_id") == chat_id]
    assert len(stop_rows) == 2
    assert stop_rows[0]["session_instance_id"] == session_instance_id
    assert stop_rows[1]["session_instance_id"] == session_instance_id
    assert not (state_root / "sessions" / f"{chat_id}.lease.json").exists()


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

    allocated = sorted((queue.get(timeout=5) for _ in range(process_count)))
    assert len(allocated) == process_count
    assert len(set(allocated)) == process_count
