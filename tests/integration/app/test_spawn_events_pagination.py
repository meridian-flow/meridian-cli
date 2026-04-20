"""Integration tests for GET /api/spawns/{spawn_id}/events pagination.

Tests verify:
  - Empty spawn (no output.jsonl) returns []
  - since=N skips the first N lines
  - tail=N returns the last N events
  - since + tail compose correctly
  - Many events (>100) paginated with since
  - Invalid JSON lines are silently skipped
  - Blank lines in output.jsonl are silently skipped
  - since out of range returns empty list
  - Spawn not found returns 404
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from meridian.lib.app.server import create_app
from meridian.lib.core.types import SpawnId
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths


class FakeManager:
    def __init__(self, *, repo_root: Path) -> None:
        self.repo_root = repo_root
        self.state_root = resolve_state_paths(repo_root).root_dir

    async def shutdown(self) -> None:
        return None

    def list_spawns(self) -> list[SpawnId]:
        return []

    def get_connection(self, spawn_id: SpawnId) -> object | None:
        _ = spawn_id
        return None


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    repo_root = tmp_path
    manager = FakeManager(repo_root=repo_root)
    app = create_app(cast("Any", manager), allow_unsafe_no_permissions=True)
    with TestClient(app) as client:
        yield client, repo_root


def _state_root(repo_root: Path) -> Path:
    return resolve_state_paths(repo_root).root_dir


def _register_spawn(repo_root: Path, spawn_id: str, status: str = "succeeded") -> None:
    """Register a spawn record so the events endpoint recognises it."""
    state_root = _state_root(repo_root)
    spawn_store.start_spawn(
        state_root,
        spawn_id=spawn_id,
        chat_id=f"chat-{spawn_id}",
        model="test-model",
        agent="test-agent",
        harness="codex",
        kind="streaming",
        prompt="test prompt",
        started_at="2026-04-20T00:00:01Z",
        runner_pid=os.getpid(),
    )
    if status != "running":
        spawn_store.finalize_spawn(
            state_root,
            spawn_id,
            status,
            exit_code=0 if status == "succeeded" else 1,
            origin="runner",
            finished_at="2026-04-20T00:01:00Z",
        )


def _write_output(repo_root: Path, spawn_id: str, lines: list[str]) -> None:
    """Write arbitrary text lines to output.jsonl."""
    output_path = _state_root(repo_root) / "spawns" / spawn_id / "output.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_events(
    repo_root: Path, spawn_id: str, events: list[dict[str, object]]
) -> None:
    """Write valid JSON events to output.jsonl."""
    _write_output(repo_root, spawn_id, [json.dumps(e) for e in events])


# ---------------------------------------------------------------------------
# Basic cases
# ---------------------------------------------------------------------------


def test_events_empty_spawn_no_output_file(
    app_client: tuple[TestClient, Path],
) -> None:
    """Spawn with no output.jsonl file returns an empty list, not an error."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    # Deliberately do NOT write any output.jsonl

    resp = client.get("/api/spawns/p1/events")

    assert resp.status_code == 200
    assert resp.json() == []


def test_events_all_events_returned_by_default(
    app_client: tuple[TestClient, Path],
) -> None:
    """Without since/tail, all events are returned with _line metadata."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    events = [{"type": "stdout", "text": f"line {i}"} for i in range(5)]
    _write_events(repo_root, "p1", events)

    resp = client.get("/api/spawns/p1/events")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    for i, item in enumerate(data):
        assert item["_line"] == i
        assert item["type"] == "stdout"


def test_events_unknown_spawn_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """Events endpoint returns 404 for an unknown spawn ID."""
    client, _repo_root = app_client

    resp = client.get("/api/spawns/p999/events")

    assert resp.status_code == 404


def test_events_invalid_spawn_id_format_returns_400(
    app_client: tuple[TestClient, Path],
) -> None:
    """Malformed spawn ID (not pN) returns 400."""
    client, _repo_root = app_client

    resp = client.get("/api/spawns/bad-id/events")

    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# since parameter
# ---------------------------------------------------------------------------


def test_events_since_skips_first_n_lines(
    app_client: tuple[TestClient, Path],
) -> None:
    """since=2 must skip lines 0 and 1 and return lines 2, 3, 4."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    events = [{"type": "stdout", "text": f"line {i}"} for i in range(5)]
    _write_events(repo_root, "p1", events)

    resp = client.get("/api/spawns/p1/events", params={"since": 2})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert [item["_line"] for item in data] == [2, 3, 4]
    assert [item["text"] for item in data] == ["line 2", "line 3", "line 4"]


def test_events_since_zero_returns_all_events(
    app_client: tuple[TestClient, Path],
) -> None:
    """since=0 is equivalent to no since parameter."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    events = [{"type": "stdout", "text": f"msg {i}"} for i in range(3)]
    _write_events(repo_root, "p1", events)

    resp = client.get("/api/spawns/p1/events", params={"since": 0})

    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_events_since_beyond_end_returns_empty(
    app_client: tuple[TestClient, Path],
) -> None:
    """since greater than the number of lines must return an empty list."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    _write_events(repo_root, "p1", [{"type": "stdout", "text": "only"}])

    resp = client.get("/api/spawns/p1/events", params={"since": 100})

    assert resp.status_code == 200
    assert resp.json() == []


def test_events_since_exactly_last_line_returns_one_event(
    app_client: tuple[TestClient, Path],
) -> None:
    """since=N-1 on N-event output returns just the last event."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    events = [{"type": "stdout", "text": f"e{i}"} for i in range(4)]
    _write_events(repo_root, "p1", events)

    resp = client.get("/api/spawns/p1/events", params={"since": 3})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["_line"] == 3
    assert data[0]["text"] == "e3"


# ---------------------------------------------------------------------------
# tail parameter
# ---------------------------------------------------------------------------


def test_events_tail_returns_last_n_events(
    app_client: tuple[TestClient, Path],
) -> None:
    """tail=2 must return only the last 2 events."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    events = [{"type": "stdout", "text": f"t{i}"} for i in range(5)]
    _write_events(repo_root, "p1", events)

    resp = client.get("/api/spawns/p1/events", params={"tail": 2})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert [item["_line"] for item in data] == [3, 4]


def test_events_tail_larger_than_output_returns_all(
    app_client: tuple[TestClient, Path],
) -> None:
    """tail=100 on a 3-event output returns all 3 events."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    events = [{"type": "stdout", "text": f"x{i}"} for i in range(3)]
    _write_events(repo_root, "p1", events)

    resp = client.get("/api/spawns/p1/events", params={"tail": 100})

    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ---------------------------------------------------------------------------
# since + tail composition
# ---------------------------------------------------------------------------


def test_events_since_and_tail_compose(
    app_client: tuple[TestClient, Path],
) -> None:
    """since=2 + tail=2: first skip 2, then keep last 2 of remaining."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    events = [{"type": "stdout", "text": f"v{i}"} for i in range(7)]
    _write_events(repo_root, "p1", events)
    # After since=2: lines 2,3,4,5,6
    # After tail=2: lines 5,6

    resp = client.get("/api/spawns/p1/events", params={"since": 2, "tail": 2})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert [item["_line"] for item in data] == [5, 6]


# ---------------------------------------------------------------------------
# Robustness: invalid/empty lines in output.jsonl
# ---------------------------------------------------------------------------


def test_events_invalid_json_lines_are_skipped(
    app_client: tuple[TestClient, Path],
) -> None:
    """Lines that fail JSON parsing must be silently skipped."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    _write_output(
        repo_root,
        "p1",
        [
            json.dumps({"type": "stdout", "text": "good0"}),
            "this is not json {{{",
            json.dumps({"type": "stdout", "text": "good2"}),
        ],
    )

    resp = client.get("/api/spawns/p1/events")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["text"] == "good0"
    assert data[0]["_line"] == 0
    assert data[1]["text"] == "good2"
    assert data[1]["_line"] == 2


def test_events_blank_lines_are_skipped(
    app_client: tuple[TestClient, Path],
) -> None:
    """Blank/whitespace-only lines in output.jsonl must be silently skipped."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    output_path = _state_root(repo_root) / "spawns" / "p1" / "output.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Manually write with blank lines interspersed
    output_path.write_text(
        json.dumps({"type": "first"}) + "\n"
        "\n"
        "   \n"
        + json.dumps({"type": "third"}) + "\n",
        encoding="utf-8",
    )

    resp = client.get("/api/spawns/p1/events")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["type"] == "first"
    assert data[1]["type"] == "third"


# ---------------------------------------------------------------------------
# Large output (stress test)
# ---------------------------------------------------------------------------


def test_events_large_output_all_returned(
    app_client: tuple[TestClient, Path],
) -> None:
    """200 events are all returned without truncation when no tail/since."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    events = [{"type": "stdout", "text": f"msg{i}", "seq": i} for i in range(200)]
    _write_events(repo_root, "p1", events)

    resp = client.get("/api/spawns/p1/events")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 200
    assert data[0]["seq"] == 0
    assert data[199]["seq"] == 199


def test_events_large_output_with_since(
    app_client: tuple[TestClient, Path],
) -> None:
    """since=190 on 200 events returns exactly 10 events."""
    client, repo_root = app_client
    _register_spawn(repo_root, "p1")
    events = [{"type": "stdout", "seq": i} for i in range(200)]
    _write_events(repo_root, "p1", events)

    resp = client.get("/api/spawns/p1/events", params={"since": 190})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 10
    assert data[0]["seq"] == 190
    assert data[-1]["seq"] == 199
