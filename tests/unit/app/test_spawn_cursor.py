from __future__ import annotations

import base64
import json

import pytest

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


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


def test_decode_cursor_rejects_payload_missing_id_key() -> None:
    """Payload with 'ts' but no 'id' must return None."""
    cursor = base64.urlsafe_b64encode(
        json.dumps({"ts": "2026-04-20T00:00:00Z"}).encode()
    ).decode()

    assert _decode_cursor(cursor) is None


def test_decode_cursor_rejects_empty_string() -> None:
    """Empty cursor string is invalid base64 content → None."""
    assert _decode_cursor("") is None


def test_decode_cursor_rejects_tampered_base64_characters() -> None:
    """A string with characters outside urlsafe-base64 alphabet must return None."""
    # '!' is not valid urlsafe-base64; decode will either raise or produce garbage JSON
    assert _decode_cursor("!!!invalid!!!") is None


def test_decode_cursor_rejects_json_array_payload() -> None:
    """A valid base64 encoding of a JSON list (not dict) must return None."""
    cursor = base64.urlsafe_b64encode(json.dumps(["p1", "ts"]).encode()).decode()

    assert _decode_cursor(cursor) is None


def test_cursor_extra_keys_do_not_break_round_trip() -> None:
    """Cursor payloads with extra keys are tolerated — 'id' and 'ts' still returned."""
    # Manually encode a cursor with an extra key
    data = {"id": "p7", "ts": "2026-01-01T00:00:00Z", "extra": "ignored"}
    cursor = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

    result = _decode_cursor(cursor)
    assert result == ("p7", "2026-01-01T00:00:00Z")


def test_encode_cursor_produces_valid_urlsafe_base64() -> None:
    """Encoded cursor must be decodable without padding errors."""
    cursor = _encode_cursor("p100", "2026-12-31T23:59:59Z")
    # Must not raise
    raw = base64.urlsafe_b64decode(cursor.encode())
    data = json.loads(raw)
    assert data["id"] == "p100"
    assert data["ts"] == "2026-12-31T23:59:59Z"


@pytest.mark.parametrize(
    "spawn_id,ts",
    [
        ("p0", ""),           # empty timestamp (valid — treated as empty string)
        ("p999", "2099-01-01T00:00:00Z"),  # far-future timestamp
        ("p1", "a" * 100),   # long timestamp string
    ],
)
def test_cursor_round_trips_various_values(spawn_id: str, ts: str) -> None:
    cursor = _encode_cursor(spawn_id, ts)
    assert _decode_cursor(cursor) == (spawn_id, ts)
