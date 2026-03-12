import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from meridian.lib.state.event_store import append_event, lock_file, read_events, utc_now_iso


class _ReadEvent(BaseModel):
    id: int
    kind: str


class _AppendEvent(BaseModel):
    z_key: str
    a_key: str
    optional: str | None = None


def _parse_read_event(payload: dict[str, Any]) -> _ReadEvent:
    return _ReadEvent.model_validate(payload)


def _write_lines(path: Path, lines: list[str]) -> None:
    path.write_text("".join(lines), encoding="utf-8")


def test_utc_now_iso_returns_z_and_no_microseconds() -> None:
    iso = utc_now_iso()

    assert iso.endswith("Z")
    parsed = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    assert parsed.microsecond == 0


def test_read_events_skips_truncated_trailing_line(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    _write_lines(
        data_path,
        [
            '{"id":1,"kind":"start"}\n',
            '{"id":2,"kind":"update"}\n',
            '{"id":3,"kind":"broken"',
        ],
    )

    rows = read_events(data_path, _parse_read_event)

    assert [row.id for row in rows] == [1, 2]


def test_read_events_skips_malformed_json_in_middle(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    _write_lines(
        data_path,
        [
            '{"id":1,"kind":"start"}\n',
            "{not-valid-json}\n",
            '{"id":2,"kind":"done"}\n',
        ],
    )

    rows = read_events(data_path, _parse_read_event)

    assert [row.id for row in rows] == [1, 2]


def test_read_events_skips_validation_errors_from_parser(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    _write_lines(
        data_path,
        [
            '{"id":1,"kind":"start"}\n',
            '{"id":"bad","kind":"update"}\n',
            '{"id":2,"kind":"done"}\n',
        ],
    )

    rows = read_events(data_path, _parse_read_event)

    assert [row.id for row in rows] == [1, 2]


def test_read_events_returns_empty_for_empty_file(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    data_path.write_text("", encoding="utf-8")

    assert read_events(data_path, _parse_read_event) == []


def test_read_events_returns_empty_for_blank_lines_only(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    data_path.write_text("\n  \n\t\n", encoding="utf-8")

    assert read_events(data_path, _parse_read_event) == []


def test_read_events_returns_empty_when_file_missing(tmp_path: Path) -> None:
    data_path = tmp_path / "missing.jsonl"

    assert read_events(data_path, _parse_read_event) == []


def test_read_events_handles_many_lines(tmp_path: Path) -> None:
    data_path = tmp_path / "many.jsonl"
    lines = [json.dumps({"id": i, "kind": "tick"}, separators=(",", ":")) + "\n" for i in range(150)]
    _write_lines(data_path, lines)

    rows = read_events(data_path, _parse_read_event)

    assert len(rows) == 150
    assert rows[0].id == 0
    assert rows[-1].id == 149


def test_append_event_writes_single_compact_sorted_jsonl_line(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    lock_path = tmp_path / "events.lock"
    event = _AppendEvent(z_key="z", a_key="a", optional=None)

    append_event(data_path, lock_path, event, store_name="test", exclude_none=False)

    assert data_path.read_text(encoding="utf-8") == '{"a_key":"a","optional":null,"z_key":"z"}\n'


def test_append_event_exclude_none_true_omits_none_fields(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    lock_path = tmp_path / "events.lock"
    event = _AppendEvent(z_key="z", a_key="a", optional=None)

    append_event(data_path, lock_path, event, store_name="test", exclude_none=True)

    assert data_path.read_text(encoding="utf-8") == '{"a_key":"a","z_key":"z"}\n'


def test_append_event_exclude_none_false_includes_none_fields(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    lock_path = tmp_path / "events.lock"
    event = _AppendEvent(z_key="z", a_key="a", optional=None)

    append_event(data_path, lock_path, event, store_name="test", exclude_none=False)

    assert '"optional":null' in data_path.read_text(encoding="utf-8")


def test_append_event_multiple_appends_create_multiple_lines(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    lock_path = tmp_path / "events.lock"

    append_event(
        data_path,
        lock_path,
        _AppendEvent(z_key="z1", a_key="a1", optional=None),
        store_name="test",
        exclude_none=True,
    )
    append_event(
        data_path,
        lock_path,
        _AppendEvent(z_key="z2", a_key="a2", optional=None),
        store_name="test",
        exclude_none=True,
    )

    lines = data_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert lines[0] == '{"a_key":"a1","z_key":"z1"}'
    assert lines[1] == '{"a_key":"a2","z_key":"z2"}'


def test_lock_file_can_acquire_release_and_reacquire(tmp_path: Path) -> None:
    lock_path = tmp_path / "events.lock"

    with lock_file(lock_path) as handle:
        assert not handle.closed

    assert handle.closed

    with lock_file(lock_path) as reacquired:
        assert not reacquired.closed


def test_lock_file_is_reentrant_in_same_thread(tmp_path: Path) -> None:
    lock_path = tmp_path / "events.lock"

    with lock_file(lock_path) as outer:
        with lock_file(lock_path) as inner:
            assert inner is outer
            assert not inner.closed
        assert not outer.closed

    assert outer.closed
    with lock_file(lock_path):
        pass
