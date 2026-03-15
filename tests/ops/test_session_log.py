"""Session log parser regressions."""


import json

from meridian.lib.ops.session_log import _extract_from_event, _parse_session_file


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

    segments, total_compactions = _parse_session_file(session_file)

    assert total_compactions == 1
    assert len(segments) == 2
    assert [(message.role, message.content) for message in segments[0]] == [("assistant", "before boundary")]
    assert [(message.role, message.content) for message in segments[1]] == [("assistant", "after boundary")]


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
    assert [(message.role, message.content) for message in assistant_messages] == [("assistant", "assistant text")]
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
    assert [(message.role, message.content) for message in response_messages] == [("assistant", "codex response")]
    assert [(message.role, message.content) for message in exec_messages] == [("assistant", "codex exec")]
