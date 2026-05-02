"""Integration tests for telemetry reader/query/status helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from meridian.lib.telemetry.query import query_events
from meridian.lib.telemetry.reader import read_events
from meridian.lib.telemetry.status import compute_status, status_to_dict


def _event(
    ts: datetime,
    event: str,
    *,
    domain: str = "chat",
    ids: dict[str, str] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "v": 1,
        "ts": ts.isoformat().replace("+00:00", "Z"),
        "domain": domain,
        "event": event,
        "scope": "test",
    }
    if ids is not None:
        payload["ids"] = ids
    return payload


def _write_segment(
    telemetry_dir: Path,
    name: str,
    events: list[dict[str, object]],
    extra: str = "",
) -> Path:
    telemetry_dir.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(event, separators=(",", ":")) for event in events]
    if extra:
        lines.append(extra)
    path = telemetry_dir / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_query_with_no_filters_returns_events_from_segments(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    now = datetime.now(UTC)
    events = [_event(now, "chat.ws.connected"), _event(now, "spawn.succeeded", domain="spawn")]
    _write_segment(telemetry_dir, "123-0001.jsonl", events)

    assert list(query_events(telemetry_dir)) == events


def test_query_domain_filter(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    now = datetime.now(UTC)
    chat_event = _event(now, "chat.ws.connected", domain="chat")
    spawn_event = _event(now, "spawn.succeeded", domain="spawn")
    _write_segment(telemetry_dir, "123-0001.jsonl", [chat_event, spawn_event])

    assert list(query_events(telemetry_dir, domain="chat")) == [chat_event]


def test_query_since_filter(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    recent = _event(datetime.now(UTC), "chat.ws.connected")
    old = _event(datetime.now(UTC) - timedelta(hours=2), "chat.ws.disconnected")
    _write_segment(telemetry_dir, "123-0001.jsonl", [old, recent])

    assert list(query_events(telemetry_dir, since="1h")) == [recent]


def test_query_spawn_correlation_filter(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    now = datetime.now(UTC)
    matching = _event(now, "spawn.succeeded", domain="spawn", ids={"spawn_id": "p123"})
    other = _event(now, "spawn.failed", domain="spawn", ids={"spawn_id": "p456"})
    _write_segment(telemetry_dir, "123-0001.jsonl", [matching, other])

    assert list(query_events(telemetry_dir, ids_filter={"spawn_id": "p123"})) == [matching]


def test_status_returns_segment_count_and_size(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    event = _event(datetime.now(UTC), "chat.ws.connected")
    path = _write_segment(telemetry_dir, "123-0001.jsonl", [event])

    status = compute_status(tmp_path)

    assert status.telemetry_dir == telemetry_dir
    assert status.segment_count == 1
    assert status.total_bytes == path.stat().st_size
    assert status.total_size_human.endswith("B")


def test_truncated_lines_are_skipped_gracefully(tmp_path: Path) -> None:
    telemetry_dir = tmp_path / "telemetry"
    event = _event(datetime.now(UTC), "chat.ws.connected")
    path = _write_segment(telemetry_dir, "123-0001.jsonl", [event], extra='{"truncated"')

    assert list(read_events(path)) == [event]


def test_status_text_includes_rootless_limitation(tmp_path: Path) -> None:
    status = compute_status(tmp_path)

    rendered = status.format_text()

    assert "Rootless processes" in rendered
    assert "stderr only" in rendered
    assert "outside the scope of local segment readers" in rendered


def test_status_dict_is_json_serializable(tmp_path: Path) -> None:
    status = compute_status(tmp_path)

    result = status_to_dict(status)

    json.dumps(result)
    assert result["telemetry_dir"] == str(tmp_path / "telemetry")
    assert result["total_size_human"] == status.total_size_human
