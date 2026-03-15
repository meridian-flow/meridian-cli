"""Spawn log assistant extraction regression tests."""

import json

from meridian.lib.ops.spawn.log import _extract_assistant_messages


def _jsonl(*events: dict[str, object]) -> str:
    return "\n".join(json.dumps(event) for event in events)


def test_extract_assistant_messages_claude_nested_message() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": "nested message"}]},
            }
        )
    )
    assert output == ["nested message"]


def test_extract_assistant_messages_claude_top_level_content() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {
                "type": "assistant",
                "content": [{"type": "text", "text": "assistant fallback"}],
            }
        )
    )
    assert output == ["assistant fallback"]


def test_extract_assistant_messages_opencode_string_message() -> None:
    output = _extract_assistant_messages(_jsonl({"type": "assistant", "message": "first message"}))
    assert output == ["first message"]


def test_extract_assistant_messages_codex_exec_item() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "first"},
            }
        )
    )
    assert output == ["first"]


def test_extract_assistant_messages_generic_fallback_shapes() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {"role": "assistant", "content": "generic fallback"},
            {"type": "assistant", "text": "json assistant message"},
        )
    )
    assert output == ["generic fallback", "json assistant message"]


def test_extract_assistant_messages_deduplicates_adjacent_messages() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {"type": "assistant", "message": "same"},
            {"type": "assistant", "message": "same"},
            {"type": "assistant", "message": "different"},
        )
    )
    assert output == ["same", "different"]


def test_extract_assistant_messages_skips_progress_and_rate_limit_events() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {"type": "progress", "message": "ignored progress"},
            {"type": "rate_limit_event", "message": "ignored rate limit"},
            {"type": "assistant", "message": "kept"},
        )
    )
    assert output == ["kept"]


def test_extract_assistant_messages_unwraps_progress_nested_message() -> None:
    output = _extract_assistant_messages(
        _jsonl(
            {
                "type": "progress",
                "data": {
                    "message": {
                        "type": "assistant",
                        "message": {"content": [{"type": "text", "text": "wrapped assistant"}]},
                    }
                },
            }
        )
    )
    assert output == ["wrapped assistant"]
