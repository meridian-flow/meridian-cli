import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from meridian.lib.state.event_store import append_event, lock_file, read_events


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


def test_read_events_skips_malformed_json_and_validation_errors(tmp_path: Path) -> None:
    data_path = tmp_path / "events.jsonl"
    _write_lines(
        data_path,
        [
            '{"id":1,"kind":"start"}\n',
            "{not-valid-json}\n",
            '{"id":"bad","kind":"update"}\n',
            '{"id":2,"kind":"done"}\n',
        ],
    )

    rows = read_events(data_path, _parse_read_event)

    assert [row.id for row in rows] == [1, 2]


def test_read_events_returns_empty_for_missing_or_blank_files(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.jsonl"
    assert read_events(missing_path, _parse_read_event) == []

    blank_path = tmp_path / "blank.jsonl"
    blank_path.write_text("\n  \n\t\n", encoding="utf-8")
    assert read_events(blank_path, _parse_read_event) == []


def test_read_events_handles_many_lines(tmp_path: Path) -> None:
    data_path = tmp_path / "many.jsonl"
    lines = [
        json.dumps({"id": i, "kind": "tick"}, separators=(",", ":")) + "\n" for i in range(150)
    ]
    _write_lines(data_path, lines)

    rows = read_events(data_path, _parse_read_event)

    assert len(rows) == 150
    assert rows[0].id == 0
    assert rows[-1].id == 149


def test_append_event_serialization_sorts_keys_and_toggles_none_fields(tmp_path: Path) -> None:
    include_path = tmp_path / "include.jsonl"
    include_lock = tmp_path / "include.lock"
    omit_path = tmp_path / "omit.jsonl"
    omit_lock = tmp_path / "omit.lock"
    event = _AppendEvent(z_key="z", a_key="a", optional=None)

    append_event(include_path, include_lock, event, store_name="test", exclude_none=False)
    append_event(omit_path, omit_lock, event, store_name="test", exclude_none=True)

    assert include_path.read_text(encoding="utf-8") == '{"a_key":"a","optional":null,"z_key":"z"}\n'
    assert omit_path.read_text(encoding="utf-8") == '{"a_key":"a","z_key":"z"}\n'


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
