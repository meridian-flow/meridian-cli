from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_runtime_paths

from .conftest import make_test_app


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path, object]]:
    app, _ = make_test_app(tmp_path)
    with TestClient(app) as client:
        yield client, tmp_path, app


def _state_root(project_root: Path) -> Path:
    return resolve_runtime_paths(project_root).root_dir


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
    runtime_root = _state_root(project_root)
    spawn_store.start_spawn(
        runtime_root,
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
            runtime_root,
            spawn_id,
            status,
            exit_code=0 if status == "succeeded" else 1,
            origin="runner",
            finished_at="2026-04-20T00:01:00Z",
        )
        return

    heartbeat_path = runtime_root / "spawns" / spawn_id / "heartbeat"
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    heartbeat_path.write_text("alive\n", encoding="utf-8")


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
