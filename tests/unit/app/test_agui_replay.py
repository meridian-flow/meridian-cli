from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, cast

import pytest

from meridian.lib.app.agui_replay import (
    PaginationCursor,
    decode_pagination_cursor,
    encode_pagination_cursor,
    replay_events_paginated,
    replay_events_to_agui,
)
from meridian.lib.core.types import HarnessId
from meridian.lib.streaming.drain_policy import TURN_BOUNDARY_EVENT_TYPE


def _event_types(events: list[Any]) -> list[str]:
    return [cast("str", event.type) for event in events]


def _write_history(path: Path, raw_events: list[dict[str, Any]]) -> None:
    lines: list[str] = []
    byte_offset = 0
    for seq, raw_event in enumerate(raw_events):
        envelope = {
            "seq": seq,
            "byte_offset": byte_offset,
            **raw_event,
        }
        line = json.dumps(envelope, separators=(",", ":"), sort_keys=True) + "\n"
        lines.append(line)
        byte_offset += len(line.encode("utf-8"))
    path.write_text("".join(lines), encoding="utf-8")


def test_replay_from_seq_zero_emits_run_boundaries_and_translated_events() -> None:
    raw_events = [
        {
            "seq": 0,
            "byte_offset": 0,
            "event_type": "item/agentMessage",
            "harness_id": "codex",
            "payload": {"text": "hello"},
        }
    ]

    events = list(replay_events_to_agui(raw_events, HarnessId.CODEX, "p1"))

    assert _event_types(events) == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "RUN_FINISHED",
    ]


def test_replay_turn_boundary_emits_new_run_started_and_finished_pairs() -> None:
    raw_events: list[dict[str, Any]] = [
        {"event_type": "item/agentMessage", "harness_id": "codex", "payload": {"text": "one"}},
        {"event_type": TURN_BOUNDARY_EVENT_TYPE, "harness_id": "codex", "payload": {}},
        {"event_type": "item/agentMessage", "harness_id": "codex", "payload": {"text": "two"}},
    ]

    events = list(replay_events_to_agui(raw_events, HarnessId.CODEX, "p1"))

    assert _event_types(events) == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "RUN_FINISHED",
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "RUN_FINISHED",
    ]


def test_replay_run_error_suppresses_terminal_run_finished() -> None:
    raw_events = [
        {
            "event_type": "error/connectionClosed",
            "harness_id": "codex",
            "payload": {"message": "boom"},
        }
    ]

    events = list(replay_events_to_agui(raw_events, HarnessId.CODEX, "p1"))

    assert _event_types(events) == ["RUN_STARTED", "RUN_ERROR"]


def test_replay_skips_invalid_raw_events() -> None:
    raw_events: list[dict[str, Any]] = [
        {"payload": {"text": "missing-required-fields"}},
        {
            "event": {
                "event_type": "item/agentMessage",
                "harness_id": "codex",
                "payload": {"text": "wrapped"},
            }
        },
        {"event_type": "item/agentMessage", "harness_id": "codex", "payload": "not-a-dict"},
    ]

    events = list(replay_events_to_agui(raw_events, HarnessId.CODEX, "p1"))

    assert _event_types(events) == [
        "RUN_STARTED",
        "TEXT_MESSAGE_START",
        "TEXT_MESSAGE_CONTENT",
        "RUN_FINISHED",
    ]


@pytest.mark.parametrize(
    ("harness_id", "raw_event"),
    [
        (
            HarnessId.CLAUDE,
            {
                "event_type": "assistant",
                "harness_id": "claude",
                "payload": {
                    "content": [{"type": "text", "text": "hello from claude"}],
                },
            },
        ),
        (
            HarnessId.CODEX,
            {
                "event_type": "item/agentMessage",
                "harness_id": "codex",
                "payload": {"item": {"type": "agentMessage", "text": "hello from codex"}},
            },
        ),
        (
            HarnessId.OPENCODE,
            {
                "event_type": "message.updated",
                "harness_id": "opencode",
                "payload": {
                    "properties": {
                        "info": {
                            "id": "msg-1",
                            "role": "assistant",
                            "content": "hello from opencode",
                        }
                    }
                },
            },
        ),
    ],
)
def test_replay_with_harness_fixture_shapes(
    harness_id: HarnessId,
    raw_event: dict[str, Any],
) -> None:
    events = list(replay_events_to_agui([raw_event], harness_id, "p-fixture"))

    event_types = _event_types(events)
    assert event_types[0] == "RUN_STARTED"
    assert event_types[-1] == "RUN_FINISHED"
    assert len(event_types) >= 3


def test_pagination_cursor_round_trips_as_url_safe_opaque_string() -> None:
    encoded = encode_pagination_cursor(
        PaginationCursor(raw_seq=42, agui_skip=2, checkpoint=7, spawn_idx=3)
    )

    assert "+" not in encoded
    assert "/" not in encoded
    assert "=" not in encoded
    assert decode_pagination_cursor(encoded) == PaginationCursor(
        raw_seq=42,
        agui_skip=2,
        checkpoint=7,
        spawn_idx=3,
    )


def test_pagination_cursor_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        decode_pagination_cursor("not-json")

    encoded = encode_pagination_cursor(PaginationCursor(raw_seq=1, agui_skip=0, checkpoint=0))
    payload = json.loads(base64.urlsafe_b64decode((encoded + "==").encode("ascii")).decode("utf-8"))
    payload["v"] = 999
    invalid = (
        base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )

    with pytest.raises(ValueError):
        decode_pagination_cursor(invalid)


def test_paginated_replay_matches_full_replay_without_gaps_or_duplicates(tmp_path: Path) -> None:
    raw_events: list[dict[str, Any]] = [
        {"event_type": "item/agentMessage", "harness_id": "codex", "payload": {"text": "one"}},
        {"event_type": TURN_BOUNDARY_EVENT_TYPE, "harness_id": "codex", "payload": {}},
        {
            "event_type": "item/started",
            "harness_id": "codex",
            "payload": {"item": {"type": "commandExecution", "id": "tool-1", "command": "ls"}},
        },
        {
            "event_type": "item/commandExecution/outputDelta",
            "harness_id": "codex",
            "payload": {"itemId": "tool-1", "delta": "out"},
        },
        {
            "event_type": "item/completed",
            "harness_id": "codex",
            "payload": {
                "item": {
                    "type": "commandExecution",
                    "id": "tool-1",
                    "aggregatedOutput": "out",
                }
            },
        },
    ]
    history_path = tmp_path / "history.jsonl"
    _write_history(history_path, raw_events)

    expected = _event_types(list(replay_events_to_agui(raw_events, HarnessId.CODEX, "p1")))
    actual: list[str] = []
    cursor: str | None = None

    while True:
        page = replay_events_paginated(
            history_path,
            HarnessId.CODEX,
            "p1",
            limit=2,
            cursor=cursor,
        )
        actual.extend(_event_types(page.events))
        if not page.has_more:
            assert page.next_cursor is None
            break
        assert page.next_cursor is not None
        cursor = page.next_cursor

    assert actual == expected


def test_paginated_replay_handles_mid_expansion_cursor(tmp_path: Path) -> None:
    raw_events = [
        {
            "event_type": "item/completed",
            "harness_id": "codex",
            "payload": {"item": {"type": "reasoning", "id": "r1", "content": "thinking"}},
        },
    ]
    history_path = tmp_path / "history.jsonl"
    _write_history(history_path, raw_events)

    first = replay_events_paginated(history_path, HarnessId.CODEX, "p1", limit=2)
    assert first.has_more
    assert first.next_cursor is not None

    second = replay_events_paginated(
        history_path,
        HarnessId.CODEX,
        "p1",
        limit=10,
        cursor=first.next_cursor,
    )

    expected = _event_types(list(replay_events_to_agui(raw_events, HarnessId.CODEX, "p1")))
    assert _event_types(first.events + second.events) == expected


def test_paginated_replay_empty_history_returns_empty_page(tmp_path: Path) -> None:
    history_path = tmp_path / "history.jsonl"

    page = replay_events_paginated(history_path, HarnessId.CODEX, "p1", limit=10)

    assert page.events == []
    assert page.next_cursor is None
    assert not page.has_more
