"""Unit tests for inspector event-ID helpers.

Covers make_event_id / parse_event_id edge cases that are not already tested
in test_thread_api.py, including:
  - Spawn IDs that themselves contain colons (rfind picks the last separator)
  - Zero and very large line indices
  - Separator at position 0 (sep_pos < 1 guard)
  - Negative line index in the encoded string
  - Whitespace-only line index
"""

from __future__ import annotations

import pytest

from meridian.lib.app.inspector import make_event_id, parse_event_id


# ---------------------------------------------------------------------------
# make_event_id
# ---------------------------------------------------------------------------


class TestMakeEventId:
    def test_produces_spawn_colon_linenum(self) -> None:
        assert make_event_id("p1", 5) == "p1:5"

    def test_zero_line_index(self) -> None:
        assert make_event_id("p42", 0) == "p42:0"

    def test_large_line_index(self) -> None:
        assert make_event_id("p99", 999_999) == "p99:999999"

    def test_arbitrary_spawn_id_preserved(self) -> None:
        """Spawn IDs with unusual but valid characters are preserved verbatim."""
        result = make_event_id("spawn-abc", 3)
        assert result == "spawn-abc:3"


# ---------------------------------------------------------------------------
# parse_event_id — valid inputs
# ---------------------------------------------------------------------------


class TestParseEventIdValid:
    def test_round_trip_simple(self) -> None:
        event_id = make_event_id("p1", 7)
        assert parse_event_id(event_id) == ("p1", 7)

    def test_zero_line_index_round_trips(self) -> None:
        assert parse_event_id("p5:0") == ("p5", 0)

    def test_large_line_index_round_trips(self) -> None:
        assert parse_event_id("p1:100000") == ("p1", 100_000)

    def test_spawn_id_containing_colon_uses_rfind(self) -> None:
        """When spawn_id itself contains colons, rfind must pick the rightmost one.

        Format: {spawn_id}:{line_index}
        If spawn_id = "ns:p1" and line_index = 3, the encoded form is "ns:p1:3".
        parse_event_id must use rfind so it returns ("ns:p1", 3) rather than ("ns", ???).
        """
        encoded = "ns:p1:3"
        result = parse_event_id(encoded)
        # rfind picks last ':' → spawn_id="ns:p1", line_index=3
        assert result == ("ns:p1", 3)

    def test_spawn_id_with_multiple_colons(self) -> None:
        """Deeper namespaced spawn IDs with multiple colons still parse correctly."""
        encoded = "a:b:c:42"
        result = parse_event_id(encoded)
        assert result == ("a:b:c", 42)


# ---------------------------------------------------------------------------
# parse_event_id — invalid inputs → None
# ---------------------------------------------------------------------------


class TestParseEventIdInvalid:
    def test_no_colon_returns_none(self) -> None:
        assert parse_event_id("p1nocoron") is None

    def test_empty_string_returns_none(self) -> None:
        assert parse_event_id("") is None

    def test_colon_at_position_zero_returns_none(self) -> None:
        # sep_pos = 0 → sep_pos < 1 guard fires
        assert parse_event_id(":5") is None

    def test_non_numeric_line_index_returns_none(self) -> None:
        assert parse_event_id("p1:abc") is None

    def test_negative_line_index_returns_none(self) -> None:
        # The integer parses fine but the sign check rejects it
        assert parse_event_id("p1:-1") is None

    def test_float_line_index_returns_none(self) -> None:
        # int("3.5") raises ValueError → None
        assert parse_event_id("p1:3.5") is None

    def test_whitespace_line_index_returns_none(self) -> None:
        assert parse_event_id("p1: ") is None

    def test_only_colon_returns_none(self) -> None:
        # sep_pos=0, spawn_id part is empty
        assert parse_event_id(":") is None
