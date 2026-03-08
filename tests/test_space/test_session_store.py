
import json
from pathlib import Path

from meridian.lib.state.session_store import (
    collect_active_chat_ids,
    cleanup_stale_sessions,
    get_last_session,
    get_session_harness_id,
    list_active_sessions,
    resolve_session_ref,
    start_session,
    stop_session,
    update_session_harness_id,
)
from meridian.lib.state.paths import SpacePaths

def _space_dir(tmp_path):
    space_dir = tmp_path / ".meridian" / ".spaces" / "s1"
    space_dir.mkdir(parents=True, exist_ok=True)
    return space_dir

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def test_start_session_creates_start_event_and_lock_file(tmp_path):
    space_dir = _space_dir(tmp_path)
    chat_id = start_session(
        space_dir,
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
    paths = SpacePaths.from_space_dir(space_dir)
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

    stop_session(space_dir, chat_id)

def test_stop_session_appends_stop_event(tmp_path):
    space_dir = _space_dir(tmp_path)
    chat_id = start_session(
        space_dir,
        harness="claude",
        harness_session_id="claude-123",
        model="claude-opus-4-6",
    )

    stop_session(space_dir, chat_id)

    lines = (space_dir / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    stop_payload = json.loads(lines[1])
    assert stop_payload["v"] == 1
    assert stop_payload["event"] == "stop"
    assert stop_payload["chat_id"] == "c1"
    assert isinstance(stop_payload["stopped_at"], str)

def test_get_last_session_returns_most_recent_start(tmp_path):
    space_dir = _space_dir(tmp_path)
    c1 = start_session(
        space_dir,
        harness="claude",
        harness_session_id="hs-a",
        model="claude-opus-4-6",
    )
    c2 = start_session(
        space_dir,
        harness="codex",
        harness_session_id="hs-b",
        model="gpt-5.3-codex",
        params=("--append-system-prompt", "Focus on tests"),
    )

    last = get_last_session(space_dir)
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

    stop_session(space_dir, c1)
    stop_session(space_dir, c2)

def test_resolve_session_ref_by_harness_session_id(tmp_path):
    space_dir = _space_dir(tmp_path)
    c1 = start_session(
        space_dir,
        harness="claude",
        harness_session_id="claude-thread-1",
        model="claude-opus-4-6",
    )
    c2 = start_session(
        space_dir,
        harness="codex",
        harness_session_id="codex-thread-2",
        model="gpt-5.3-codex",
    )

    by_alias = resolve_session_ref(space_dir, c1)
    by_harness = resolve_session_ref(space_dir, "codex-thread-2")
    missing = resolve_session_ref(space_dir, "unknown")

    assert by_alias is None
    assert by_harness is not None
    assert by_harness.chat_id == c2
    assert by_harness.harness == "codex"
    assert get_session_harness_id(space_dir, c2) == "codex-thread-2"
    assert get_session_harness_id(space_dir, "c404") is None
    assert missing is None

    stop_session(space_dir, c1)
    stop_session(space_dir, c2)

def test_update_session_harness_id_writes_update_event_and_replays(tmp_path):
    space_dir = _space_dir(tmp_path)
    chat_id = start_session(
        space_dir,
        harness="codex",
        harness_session_id="",
        model="gpt-5.3-codex",
    )

    update_session_harness_id(space_dir, chat_id, "hs-updated")
    resolved = resolve_session_ref(space_dir, "hs-updated")

    assert resolved is not None
    assert resolved.harness_session_id == "hs-updated"
    assert get_session_harness_id(space_dir, chat_id) == "hs-updated"

    rows = [
        json.loads(line)
        for line in (space_dir / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    update_rows = [row for row in rows if row.get("event") == "update"]
    assert len(update_rows) == 1
    assert update_rows[0]["chat_id"] == chat_id
    assert update_rows[0]["harness_session_id"] == "hs-updated"

    stop_session(space_dir, chat_id)

def test_cleanup_stale_sessions_removes_dead_locks_and_writes_stop_events(tmp_path):
    space_dir = _space_dir(tmp_path)
    live = start_session(
        space_dir,
        harness="codex",
        harness_session_id="live-thread",
        model="gpt-5.3-codex",
    )

    stale_lock = space_dir / "sessions" / "c2.lock"
    stale_lock.parent.mkdir(parents=True, exist_ok=True)
    stale_lock.touch()

    with (space_dir / "sessions.jsonl").open("a", encoding="utf-8") as handle:
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

    cleanup = cleanup_stale_sessions(space_dir)
    assert cleanup.cleaned_ids == ("c2",)
    assert cleanup.materialized_scopes == (("claude", "c2"),)
    assert not stale_lock.exists()
    assert (space_dir / "sessions" / f"{live}.lock").exists()

    rows = [
        json.loads(line)
        for line in (space_dir / "sessions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    stop_rows = [row for row in rows if row.get("event") == "stop" and row.get("chat_id") == "c2"]
    assert len(stop_rows) == 1
    assert stop_rows[0]["v"] == 1
    assert isinstance(stop_rows[0]["stopped_at"], str)

    stop_session(space_dir, live)

def test_cleanup_stale_sessions_removes_materialized_scope_for_stale_chat(tmp_path):
    space_dir = _space_dir(tmp_path)
    live = start_session(
        space_dir,
        harness="codex",
        harness_session_id="live-thread",
        model="gpt-5.3-codex",
    )

    stale_lock = space_dir / "sessions" / "c2.lock"
    stale_lock.parent.mkdir(parents=True, exist_ok=True)
    stale_lock.touch()

    with (space_dir / "sessions.jsonl").open("a", encoding="utf-8") as handle:
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

    cleanup = cleanup_stale_sessions(space_dir)

    assert cleanup.cleaned_ids == ("c2",)
    assert cleanup.materialized_scopes == (("claude", "c2"),)
    assert (tmp_path / ".claude" / "agents" / "__primary-c2.md").is_file()
    assert (tmp_path / ".claude" / "agents" / "__primary-c3.md").is_file()
    assert (tmp_path / ".claude" / "skills" / "__alpha-c2").is_dir()
    assert (tmp_path / ".claude" / "skills" / "__alpha-c3").is_dir()

    stop_session(space_dir, live)


def test_collect_active_chat_ids_across_spaces(tmp_path):
    first_space = _space_dir(tmp_path)
    second_space = tmp_path / ".meridian" / ".spaces" / "s2"
    second_space.mkdir(parents=True, exist_ok=True)

    c1 = start_session(
        first_space,
        harness="claude",
        harness_session_id="hs-1",
        model="claude-opus-4-6",
    )
    c2 = start_session(
        second_space,
        harness="codex",
        harness_session_id="hs-2",
        model="gpt-5.3-codex",
    )
    stop_session(second_space, c2)

    assert collect_active_chat_ids(tmp_path) == frozenset({c1})

    stop_session(first_space, c1)
