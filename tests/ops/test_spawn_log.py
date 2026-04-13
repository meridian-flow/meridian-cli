"""Spawn log assistant extraction regression tests."""

import json

from meridian.lib.ops.spawn.log import _extract_assistant_messages


def _jsonl(*events: dict[str, object]) -> str:
    return "\n".join(json.dumps(event) for event in events)


def test_extract_assistant_messages_parses_structured_harness_events() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "nested message"}]},
            },
            {
                "type": "assistant",
                "content": [{"type": "text", "text": "assistant fallback"}],
            },
            {"type": "assistant", "message": "assistant fallback"},
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "codex message"},
            },
            {
                "type": "progress",
                "data": {
                    "message": {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "wrapped"}]},
                    }
                },
            },
            {"type": "rate_limit_event", "message": "ignored"},
        )
    )

    assert output == ["nested message", "assistant fallback", "codex message", "wrapped"]


def test_extract_assistant_messages_parses_streaming_codex_event_shapes() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {
                "event_type": "item/completed",
                "payload": {"item": {"type": "agentMessage", "text": "streamed codex message"}},
            }
        )
    )

    assert output == ["streamed codex message"]


def test_extract_assistant_messages_parses_unstructured_assistant_fallbacks() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {"role": "assistant", "content": "generic fallback"},
            {"type": "assistant", "text": "json assistant message"},
        )
    )

    assert output == ["generic fallback", "json assistant message"]


def test_extract_assistant_messages_returns_empty_for_empty_or_whitespace_input() -> None:
    assert _extract_assistant_messages("") == []
    assert _extract_assistant_messages("\n \n\t\n") == []


def test_extract_assistant_messages_skips_malformed_or_non_assistant_payloads() -> None:
    raw = "\n".join(
        [
            "{not-json}",
            json.dumps({"type": "item.completed", "item": {"type": "tool_call", "text": "x"}}),
            json.dumps({"type": "progress", "message": "ignored"}),
            json.dumps({"type": "assistant", "message": "kept"}),
        ]
    )

    assert _extract_assistant_messages(raw) == ["kept"]
