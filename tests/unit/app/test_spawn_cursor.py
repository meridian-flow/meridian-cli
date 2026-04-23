from __future__ import annotations

import base64
import json

from meridian.lib.app.spawn_routes import _decode_cursor, _encode_cursor


def test_cursor_round_trips_spawn_id_and_timestamp() -> None:
    cursor = _encode_cursor("p42", "2026-04-20T12:34:56Z")

    assert _decode_cursor(cursor) == ("p42", "2026-04-20T12:34:56Z")


def test_decode_cursor_rejects_non_json_payload() -> None:
    cursor = base64.urlsafe_b64encode(b"not-json").decode()

    assert _decode_cursor(cursor) is None


def test_decode_cursor_rejects_payload_missing_required_keys() -> None:
    cursor = base64.urlsafe_b64encode(json.dumps({"id": "p42"}).encode()).decode()

    assert _decode_cursor(cursor) is None


def test_decode_cursor_rejects_empty_string() -> None:
    """Empty cursor string is invalid base64 content → None."""
    assert _decode_cursor("") is None


def test_decode_cursor_rejects_json_array_payload() -> None:
    """A valid base64 encoding of a JSON list (not dict) must return None."""
    cursor = base64.urlsafe_b64encode(json.dumps(["p1", "ts"]).encode()).decode()

    assert _decode_cursor(cursor) is None
