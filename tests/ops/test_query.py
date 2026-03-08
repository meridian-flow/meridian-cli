"""Running-spawn query parser regressions."""

from __future__ import annotations

import json

from meridian.lib.ops.spawn.query import _extract_last_assistant_message


def test_extract_last_assistant_message_ignores_codex_substrings() -> None:
    stderr_text = "\n".join(
        [
            "OpenAI Codex v0.107.0",
            "model=gpt-5.3-codex",
            "harness=codex",
            "provider=openai",
        ]
    )
    assert _extract_last_assistant_message(stderr_text) is None


def test_extract_last_assistant_message_reads_lines_after_codex_marker() -> None:
    stderr_text = "\n".join(
        [
            "OpenAI Codex v0.107.0",
            "model: gpt-5.3-codex",
            "codex",
            "First response line.",
            "Second response line.",
            "exec",
            "/bin/bash -lc 'echo ok'",
            "codex",
            "Final assistant reply.",
        ]
    )
    assert _extract_last_assistant_message(stderr_text) == "Final assistant reply."


def test_extract_last_assistant_message_keeps_json_assistant_events() -> None:
    stderr_text = "\n".join(
        [
            json.dumps({"type": "assistant", "text": "json assistant message"}),
            "exec",
        ]
    )
    assert _extract_last_assistant_message(stderr_text) == "json assistant message"
