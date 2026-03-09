import json
from pathlib import Path

from meridian.lib.state.paths import StateRootPaths
from meridian.lib.state.session_store import (
    cleanup_stale_sessions,
    collect_active_chat_ids,
    get_last_session,
    get_session_harness_id,
    list_active_sessions,
    resolve_session_ref,
    start_session,
    stop_session,
    update_session_harness_id,
)


def _state_root(tmp_path):
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_start_session_creates_start_event_and_lock_file(tmp_path):
    state_root = _state_root(tmp_path)
    chat_id = start_session(
        state_root,
        harness="codex",
        harness_session_id="hs-1",
        model="gpt-5.3-codex",
        agent="coder",
        agent_path="/tmp/agents/coder.md",
        skills=("meridian-spawn-agent", "orchestrate"),
        skill_paths=(
            "/tmp/skills/meridian-spawn-agent/SKILL.md",
            "/tmp/skills/orchestrate/SKILL.md",
        ),
        params=("--system-prompt", "Be concise."),
    )

    assert chat_id == "c1"
    paths = StateRootPaths.from_root_dir(state_root)
    assert (paths.sessions_dir / "c1.lock").exists()

    first = paths.sessions_jsonl.read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(first)
    assert payload["v"] == 1
    assert payload["event"] == "start"
    assert payload["chat_id"] == "c1"
    assert payload["harness"] == "codex"
    assert payload["harness_session_id"] == "hs-1"
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["agent"] == "coder"
    assert payload["agent_path"] == "/tmp/agents/coder.md"
    assert payload["skills"] == ["meridian-spawn-agent", "orchestrate"]
    assert payload["skill_paths"] == [
        "/tmp/skills/meridian-spawn-agent/SKILL.md",
        "/tmp/skills/orchestrate/SKILL.md",
    ]
    assert payload["params"] == ["--system-prompt", "Be concise."]

    stop_session(state_root, chat_id)


def test_stop_session_appends_stop_event(tmp_path):
    state_root = _state_root(tmp_path)
    chat_id = start_session(
        state_root,
        harness="claude",
        harness_session_id="claude-123",
        model="claude-opus-4-6",
    )

    stop_session(state_root, chat_id)

    lines = (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    stop_payload = json.loads(lines[1])
    assert stop_payload["v"] == 1
    assert stop_payload["event"] == "stop"
    assert stop_payload["chat_id"] == "c1"
    assert isinstance(stop_payload["stopped_at"], str)


def test_get_last_session_returns_most_recent_start(tmp_path):
    state_root = _state_root(tmp_path)
    c1 = start_session(
        state_root,
        harness="claude",
        harness_session_id="hs-a",
        model="claude-opus-4-6",
    )
    c2 = start_session(
        state_root,
        harness="codex",
        harness_session_id="hs-b",
        model="gpt-5.3-codex",
        params=("--append-system-prompt", "Focus on tests"),
    )

    last = get_last_session(state_root)
    assert last is not None
    assert last.chat_id == c2
    assert last.harness == "codex"
    assert last.harness_session_id == "hs-b"
    assert last.model == "gpt-5.3-codex"
    assert last.agent == ""
    assert last.agent_path == ""
    assert last.skills == ()
    assert last.skill_paths == ()
    assert last.params == ("--append-system-prompt", "Focus on tests")

    stop_session(state_root, c1)
    stop_session(state_root, c2)


def test_resolve_session_ref_by_harness_session_id(tmp_path):
    state_root = _state_root(tmp_path)
    c1 = start_session(
        state_root,
        harness="claude",
        harness_session_id="claude-thread-1",
        model="claude-opus-4-6",
    )
    c2 = start_session(
        state_root,
        harness="codex",
        harness_session_id="codex-thread-2",
        model="gpt-5.3-codex",
    )

    by_alias = resolve_session_ref(state_root, c1)
    by_harness = resolve_session_ref(state_root, "codex-thread-2")
    missing = resolve_session_ref(state_root, "unknown")

    assert by_alias is None
    assert by_harness is not None
    assert by_harness.chat_id == c2
    assert by_harness.harness == "codex"
    assert get_session_harness_id(state_root, c2) == "codex-thread-2"
    assert get_session_harness_id(state_root, "c404") is None
    assert missing is None

    stop_session(state_root, c1)
    stop_session(state_root, c2)


def test_update_session_harness_id_writes_update_event_and_replays(tmp_path):
    state_root = _state_root(tmp_path)
    chat_id = start_session(
        state_root,
        harness="codex",
        harness_session_id="",
        model="gpt-5.3-codex",
    )

    update_session_harness_id(state_root, chat_id, "hs-updated")
    resolved = resolve_session_ref(state_root, "hs-updated")

    assert resolved is not None
    assert resolved.harness_session_id == "hs-updated"
    assert get_session_harness_id(state_root, chat_id) == "hs-updated"

    rows = [
        json.loads(line)
        for line in (state_root / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    update_rows = [row for row in rows if row.get("event") == "update"]
    assert len(update_rows) == 1
    assert update_rows[0]["chat_id"] == chat_id
    assert update_rows[0]["harness_session_id"] == "hs-updated"

    stop_session(state_root, chat_id)


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
    assert cleanup.materialized_scopes == (("claude", "c2"),)
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


def test_cleanup_stale_sessions_removes_materialized_scope_for_stale_chat(tmp_path):
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

    _write(tmp_path / ".claude" / "agents" / "__primary-c2.md", "x")
    _write(tmp_path / ".claude" / "agents" / "__primary-c3.md", "x")
    _write(tmp_path / ".claude" / "skills" / "__alpha-c2" / "SKILL.md", "x")
    _write(tmp_path / ".claude" / "skills" / "__alpha-c3" / "SKILL.md", "x")

    cleanup = cleanup_stale_sessions(state_root)

    assert cleanup.cleaned_ids == ("c2",)
    assert cleanup.materialized_scopes == (("claude", "c2"),)
    assert (tmp_path / ".claude" / "agents" / "__primary-c2.md").is_file()
    assert (tmp_path / ".claude" / "agents" / "__primary-c3.md").is_file()
    assert (tmp_path / ".claude" / "skills" / "__alpha-c2").is_dir()
    assert (tmp_path / ".claude" / "skills" / "__alpha-c3").is_dir()

    stop_session(state_root, live)


def test_collect_active_chat_ids_single_root(tmp_path):
    state_root = _state_root(tmp_path)

    c1 = start_session(
        state_root,
        harness="claude",
        harness_session_id="hs-1",
        model="claude-opus-4-6",
    )
    c2 = start_session(
        state_root,
        harness="codex",
        harness_session_id="hs-2",
        model="gpt-5.3-codex",
    )
    stop_session(state_root, c2)

    assert collect_active_chat_ids(tmp_path) == frozenset({c1})

    stop_session(state_root, c1)
