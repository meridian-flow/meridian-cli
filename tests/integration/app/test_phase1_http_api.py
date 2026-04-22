from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from meridian.lib.app.server import create_app
from meridian.lib.core.types import SpawnId
from meridian.lib.state import spawn_store, work_store
from meridian.lib.state.paths import resolve_project_paths, resolve_runtime_paths


class FakeManager:
    def __init__(self, *, project_root: Path) -> None:
        self.project_root = project_root
        self.state_root = resolve_runtime_paths(project_root).root_dir

    async def shutdown(self) -> None:
        return None

    def list_spawns(self) -> list[SpawnId]:
        return []

    def get_connection(self, spawn_id: SpawnId) -> object | None:
        _ = spawn_id
        return None


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path, object]]:
    project_root = tmp_path
    manager = FakeManager(project_root=project_root)
    app = create_app(cast("Any", manager), allow_unsafe_no_permissions=True)
    with TestClient(app) as client:
        yield client, project_root, app


def _state_root(project_root: Path) -> Path:
    return resolve_runtime_paths(project_root).root_dir


def _repo_state_root(project_root: Path) -> Path:
    return resolve_project_paths(project_root).root_dir


def _write_spawn(
    project_root: Path,
    *,
    spawn_id: str,
    status: str,
    started_at: str,
    work_id: str | None = None,
    agent: str = "api-agent",
    harness: str = "codex",
) -> None:
    state_root = _state_root(project_root)
    spawn_store.start_spawn(
        state_root,
        spawn_id=spawn_id,
        chat_id=f"chat-{spawn_id}",
        model="gpt-5.4",
        agent=agent,
        harness=harness,
        kind="streaming",
        prompt=f"prompt for {spawn_id}",
        work_id=work_id,
        started_at=started_at,
        runner_pid=os.getpid() if status == "running" else None,
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
        return

    heartbeat_path = state_root / "spawns" / spawn_id / "heartbeat"
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.write_text("alive\n", encoding="utf-8")


def _write_spawn_output(project_root: Path, spawn_id: str, events: list[dict[str, object]]) -> None:
    output_path = _state_root(project_root) / "spawns" / spawn_id / "output.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


def _read_active_work_json(project_root: Path) -> dict[str, object]:
    active_path = _repo_state_root(project_root) / "app" / "active_work.json"
    return cast("dict[str, object]", json.loads(active_path.read_text(encoding="utf-8")))


def test_spawns_list_static_route_wins_and_applies_query_filters(
    app_client: tuple[TestClient, Path, object],
) -> None:
    client, project_root, _app = app_client
    _write_spawn(
        project_root,
        spawn_id="p1",
        status="running",
        started_at="2026-04-20T00:00:01Z",
        work_id="feature-a",
    )
    _write_spawn(
        project_root,
        spawn_id="p2",
        status="succeeded",
        started_at="2026-04-20T00:00:02Z",
        work_id="feature-b",
    )

    response = client.get("/api/spawns/list", params={"status": "succeeded", "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    assert payload["has_more"] is False
    assert payload["next_cursor"] is None
    assert [item["spawn_id"] for item in payload["items"]] == ["p2"]
    assert payload["items"][0]["status"] == "succeeded"


def test_spawns_stats_and_events_parse_query_params(
    app_client: tuple[TestClient, Path, object],
) -> None:
    client, project_root, _app = app_client
    _write_spawn(
        project_root,
        spawn_id="p1",
        status="running",
        started_at="2026-04-20T00:00:01Z",
        work_id="alpha",
    )
    _write_spawn(
        project_root,
        spawn_id="p2",
        status="succeeded",
        started_at="2026-04-20T00:00:02Z",
        work_id="alpha",
    )
    _write_spawn(
        project_root,
        spawn_id="p3",
        status="failed",
        started_at="2026-04-20T00:00:03Z",
        work_id="beta",
    )
    _write_spawn_output(
        project_root,
        "p2",
        [
            {"type": "stdout", "text": "one"},
            {"type": "stdout", "text": "two"},
            {"type": "stdout", "text": "three"},
        ],
    )

    stats_response = client.get("/api/spawns/stats", params={"work_id": "alpha"})

    assert stats_response.status_code == 200
    assert stats_response.json() == {
        "running": 1,
        "queued": 0,
        "succeeded": 1,
        "failed": 0,
        "cancelled": 0,
        "finalizing": 0,
        "total": 2,
    }

    events_response = client.get("/api/spawns/p2/events", params={"tail": 2})

    assert events_response.status_code == 200
    assert events_response.json() == [
        {"type": "stdout", "text": "two", "_line": 1},
        {"type": "stdout", "text": "three", "_line": 2},
    ]


def test_work_routes_resolve_static_active_path_and_filter_listing(
    app_client: tuple[TestClient, Path, object],
) -> None:
    client, project_root, _app = app_client
    state_root = _state_root(project_root)
    work_store.create_work_item(state_root, "feature-a", "A")
    work_store.create_work_item(state_root, "feature-b", "B")
    work_store.archive_work_item(state_root, "feature-b")

    response = client.get("/api/work", params={"status": "open", "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert [item["work_id"] for item in payload["items"]] == ["feature-a"]

    active_response = client.get("/api/work/active")

    assert active_response.status_code == 200
    assert active_response.json() == {"work_id": "feature-a"}


def test_active_work_roundtrip_persists_and_falls_back_after_archive(
    app_client: tuple[TestClient, Path, object],
) -> None:
    client, project_root, _app = app_client
    state_root = _state_root(project_root)
    work_store.create_work_item(state_root, "older-task", "older")
    work_store.create_work_item(state_root, "newer-task", "newer")

    set_response = client.put("/api/work/active", json={"work_id": "older-task"})

    assert set_response.status_code == 200
    assert set_response.json() == {"work_id": "older-task"}
    assert _read_active_work_json(project_root) == {"work_id": "older-task"}
    assert client.get("/api/work/active").json() == {"work_id": "older-task"}

    work_store.archive_work_item(state_root, "older-task")

    fallback_response = client.get("/api/work/active")

    assert fallback_response.status_code == 200
    assert fallback_response.json() == {"work_id": "newer-task"}
    assert _read_active_work_json(project_root) == {"work_id": "newer-task"}


def test_stream_endpoint_connects_and_emits_work_events(
    app_client: tuple[TestClient, Path, object],
) -> None:
    _client, _project_root, app = app_client
    broadcaster = app.state.stream_broadcaster
    stream_route = next((route for route in app.routes if route.path == "/api/stream"), None)
    assert stream_route is not None

    subscriber_id, event_queue = asyncio.run(broadcaster.subscribe())

    with TestClient(app) as publisher:
        create_response = publisher.post(
            "/api/work",
            json={"name": "stream-work", "description": "created from stream test"},
        )
        assert create_response.status_code == 200

        active_response = publisher.put("/api/work/active", json={"work_id": "stream-work"})
        assert active_response.status_code == 200

    created_event = asyncio.run(event_queue.get())
    active_changed_event = asyncio.run(event_queue.get())
    asyncio.run(broadcaster.unsubscribe(subscriber_id))

    assert created_event == {
        "type": "work.created",
        "work_id": "stream-work",
        "status": "open",
    }
    assert active_changed_event == {
        "type": "work.active_changed",
        "work_id": "stream-work",
    }
