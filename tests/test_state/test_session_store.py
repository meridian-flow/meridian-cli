import json

from meridian.lib.state.session_store import (
    cleanup_stale_sessions,
    get_session_harness_ids,
    resolve_session_ref,
    start_session,
    stop_session,
    update_session_harness_id,
    update_session_work_id,
)


def _state_root(tmp_path):
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def test_cleanup_stale_sessions_removes_dead_locks_and_writes_stop_events(tmp_path):
    state_root = _state_root(tmp_path)
    live = start_session(
        state_root,
        harness="codex",
        harness_session_id="live-thread",
        model="gpt-5.3-codex",
    )

    stale_lock = state_root / "sessions" / "c2.lock"
    stale_lock.parent.mkdir(parents=True, exist_ok=True)
    stale_lock.touch()

    with (state_root / "sessions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "v": 1,
                    "event": "start",
                    "chat_id": "c2",
                    "harness": "claude",
                    "harness_session_id": "stale-thread",
                    "model": "claude-opus-4-6",
                    "params": [],
                    "started_at": "2026-03-01T00:00:00Z",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        )

    cleanup = cleanup_stale_sessions(state_root)
    assert cleanup.cleaned_ids == ("c2",)
    assert cleanup.materialized_scopes == ("claude",)
    assert not stale_lock.exists()
    assert (state_root / "sessions" / f"{live}.lock").exists()

    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [row for row in rows if row.get("event") == "stop" and row.get("chat_id") == "c2"]
    assert len(stop_rows) == 1
    assert stop_rows[0]["v"] == 1
    assert isinstance(stop_rows[0]["stopped_at"], str)

    stop_session(state_root, live)


def test_session_record_preserves_harness_session_history(tmp_path):
    state_root = _state_root(tmp_path)
    chat_id = start_session(
        state_root,
        harness="claude",
        harness_session_id="session-1",
        model="claude-opus-4-6",
    )

    update_session_harness_id(state_root, chat_id, "session-2")
    update_session_harness_id(state_root, chat_id, "session-3")
    update_session_harness_id(state_root, chat_id, "session-2")

    record = resolve_session_ref(state_root, "session-1")
    assert record is not None
    assert record.chat_id == chat_id
    assert record.harness_session_id == "session-2"
    assert record.harness_session_ids == ("session-1", "session-2", "session-3")
    assert get_session_harness_ids(state_root, chat_id) == ("session-1", "session-2", "session-3")

    latest_record = resolve_session_ref(state_root, "session-3")
    assert latest_record is not None
    assert latest_record.chat_id == chat_id

    stop_session(state_root, chat_id)


def test_session_record_tracks_active_work_id(tmp_path):
    state_root = _state_root(tmp_path)
    chat_id = start_session(
        state_root,
        harness="codex",
        harness_session_id="session-1",
        model="gpt-5.4",
    )

    update_session_work_id(state_root, chat_id, "work-1")
    record = resolve_session_ref(state_root, "session-1")
    assert record is not None
    assert record.active_work_id == "work-1"

    update_session_work_id(state_root, chat_id, None)
    cleared = resolve_session_ref(state_root, "session-1")
    assert cleared is not None
    assert cleared.active_work_id is None
    assert cleared.harness_session_id == "session-1"
    assert cleared.harness_session_ids == ("session-1",)

    stop_session(state_root, chat_id)
