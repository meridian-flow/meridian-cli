"""Session log parser regressions."""

import json
from pathlib import Path

import pytest

from meridian.lib.ops.session_log import (
    SessionLogInput,
    _extract_from_event,
    parse_session_file,
    resolve_target,
    session_log_sync,
)
from meridian.lib.state import session_store, spawn_store
from meridian.lib.state.paths import resolve_runtime_state_root


def test_parse_session_file_splits_segments_on_compaction_boundary(tmp_path) -> None:
    session_file = tmp_path / "session.jsonl"
    lines = [
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "before boundary"}]},
            }
        ),
        json.dumps({"type": "system", "subtype": "compact_boundary"}),
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "after boundary"}]},
            }
        ),
    ]
    session_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    segments, total_compactions = parse_session_file(session_file)

    assert total_compactions == 1
    assert len(segments) == 2
    assert [(message.role, message.content) for message in segments[0]] == [
        ("assistant", "before boundary")
    ]
    assert [(message.role, message.content) for message in segments[1]] == [
        ("assistant", "after boundary")
    ]


def test_extract_from_event_claude_assistant_and_user_messages() -> None:
    assistant_messages, assistant_boundary = _extract_from_event(
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "assistant text"}]},
        }
    )
    user_messages, user_boundary = _extract_from_event(
        {
            "type": "user",
            "message": {"content": [{"type": "text", "text": "user text"}]},
        }
    )

    assert assistant_boundary is False
    assert user_boundary is False
    assert [(message.role, message.content) for message in assistant_messages] == [
        ("assistant", "assistant text")
    ]
    assert [(message.role, message.content) for message in user_messages] == [("user", "user text")]


def test_extract_from_event_codex_response_and_exec_events() -> None:
    response_messages, response_boundary = _extract_from_event(
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "codex response"}],
            },
        }
    )
    exec_messages, exec_boundary = _extract_from_event(
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "codex exec"},
        }
    )

    assert response_boundary is False
    assert exec_boundary is False
    assert [(message.role, message.content) for message in response_messages] == [
        ("assistant", "codex response")
    ]
    assert [(message.role, message.content) for message in exec_messages] == [
        ("assistant", "codex exec")
    ]


def test_session_log_resolves_opencode_storage_session_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = resolve_runtime_state_root(repo_root)
    state_root.mkdir(parents=True, exist_ok=True)

    xdg_data_home = tmp_path / "xdg-data"
    session_id = "ses_fixture_session_12345"
    session_file = (
        xdg_data_home / "opencode" / "storage" / "session_diff" / f"{session_id}.json"
    )
    session_file.parent.mkdir(parents=True)
    session_file.write_text("[]\n", encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_HOME", xdg_data_home.as_posix())

    spawn_store.start_spawn(
        state_root,
        chat_id="c1",
        model="opencode-gpt-5.3-codex",
        agent="coder",
        harness="opencode",
        prompt="hello",
        spawn_id="p1",
        harness_session_id=session_id,
        started_at="2026-04-11T00:00:00Z",
    )

    output = session_log_sync(
        SessionLogInput(
            ref="p1",
            repo_root=repo_root.as_posix(),
            compaction=0,
            last_n=5,
            offset=0,
        )
    )

    assert output.session_id == session_id
    assert output.segment_messages == 0
    assert output.messages == ()


def test_resolve_target_chat_missing_harness_session_id_reports_unavailable_transcript(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = resolve_runtime_state_root(repo_root)
    state_root.mkdir(parents=True, exist_ok=True)

    chat_id = session_store.start_session(
        state_root,
        harness="codex",
        harness_session_id="",
        model="gpt-5.4",
        chat_id="c1",
    )

    try:
        with pytest.raises(ValueError) as exc:
            resolve_target(
                SessionLogInput(ref=chat_id),
                repo_root=repo_root,
                state_root=state_root,
            )
        assert str(exc.value) == (
            "Session 'c1' exists but no transcript is available yet "
            "(no harness session id recorded)"
        )
    finally:
        session_store.stop_session(state_root, chat_id)


def test_resolve_target_chat_not_found_preserves_missing_chat_error(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = resolve_runtime_state_root(repo_root)
    state_root.mkdir(parents=True, exist_ok=True)

    with pytest.raises(ValueError) as exc:
        resolve_target(
            SessionLogInput(ref="c999"),
            repo_root=repo_root,
            state_root=state_root,
        )
    assert str(exc.value) == "Chat 'c999' not found"
