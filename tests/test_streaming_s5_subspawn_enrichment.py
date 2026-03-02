"""Slice 5 tests: sub-run lifecycle event enrichment."""

from __future__ import annotations

import json

from meridian.lib.harness._common import categorize_stream_event, parse_json_stream_event
from meridian.lib.ops._spawn_execute import _emit_subrun_event, _spawn_child_env


def test_emit_subrun_event_enriches_protocol(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.setenv("MERIDIAN_SPAWN_ID", "p33")
    monkeypatch.setattr("meridian.lib.ops._spawn_execute.time.time", lambda: 1740000000.123)

    _emit_subrun_event(
        {"t": "meridian.spawn.start", "id": "r34", "model": "claude-haiku-4-5", "d": 1}
    )

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["v"] == 1
    assert payload["t"] == "meridian.spawn.start"
    assert payload["id"] == "r34"
    assert payload["parent"] == "p33"
    assert payload["ts"] == 1740000000.123
    assert payload["model"] == "claude-haiku-4-5"
    assert payload["d"] == 1


def test_run_child_env_sets_parent_spawn_id(monkeypatch) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "2")
    monkeypatch.setenv("MERIDIAN_SPAWN_ID", "p-ancestor")

    env = _spawn_child_env("s9", "p34")

    assert env["MERIDIAN_DEPTH"] == "3"
    assert env["MERIDIAN_SPACE_ID"] == "s9"
    assert env["MERIDIAN_PARENT_SPAWN_ID"] == "p-ancestor"
    assert env["MERIDIAN_SPAWN_ID"] == "p34"


def test_parse_json_stream_event_recognizes_namespaced_subrun() -> None:
    done = parse_json_stream_event(
        '{"t":"meridian.spawn.done","id":"r34","parent":"r33","exit":0,'
        '"secs":2.1,"tok":3200,"v":1,"ts":1740000002.234}'
    )

    assert done is not None
    assert done.event_type == "meridian.spawn.done"
    assert done.category == "sub-run"
    assert done.text == "r34 completed 2.1s exit=0 tok=3200"
    assert categorize_stream_event(done).category == "sub-run"
