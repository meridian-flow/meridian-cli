"""Integration tests for thread inspector endpoints (APP-THREAD-01..03).

Tests verify:
    APP-THREAD-01  GET /api/threads/{chat_id}/events/{event_id}
    APP-THREAD-02  GET /api/threads/{chat_id}/tool-calls/{call_id}
    APP-THREAD-03  GET /api/threads/{chat_id}/token-usage

All endpoints must work on completed sessions by reading persisted artifacts,
without requiring a live connection or in-memory state.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from meridian.lib.app.inspector import make_event_id, parse_event_id
from meridian.lib.app.server import create_app
from meridian.lib.core.types import SpawnId
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_runtime_paths

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


class FakeManager:
    def __init__(self, *, project_root: Path) -> None:
        self.project_root = project_root
        self.runtime_root = resolve_runtime_paths(project_root).root_dir

    async def shutdown(self) -> None:
        return None

    def list_spawns(self) -> list[SpawnId]:
        return []

    def get_connection(self, spawn_id: SpawnId) -> object | None:
        _ = spawn_id
        return None


@pytest.fixture
def app_client(tmp_path: Path) -> Iterator[tuple[TestClient, Path]]:
    project_root = tmp_path
    manager = FakeManager(project_root=project_root)
    app = create_app(cast("Any", manager), allow_unsafe_no_permissions=True)
    with TestClient(app) as client:
        yield client, project_root


def _state_root(project_root: Path) -> Path:
    return resolve_runtime_paths(project_root).root_dir


def _write_spawn(
    project_root: Path,
    *,
    spawn_id: str,
    chat_id: str,
    harness: str = "claude",
    status: str = "succeeded",
) -> None:
    """Register a spawn record in spawns.jsonl."""
    runtime_root = _state_root(project_root)
    spawn_store.start_spawn(
        runtime_root,
        spawn_id=spawn_id,
        chat_id=chat_id,
        model="claude-opus-4-5",
        agent="test-agent",
        harness=harness,
        kind="primary",
        prompt="test prompt",
        started_at="2026-04-20T00:00:01Z",
        runner_pid=os.getpid(),
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


def _write_artifact_output(
    project_root: Path,
    spawn_id: str,
    events: list[dict[str, object]],
) -> None:
    """Write output.jsonl into the artifact store used by the inspector."""
    artifact_dir = _state_root(project_root) / "artifacts" / spawn_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    output_path = artifact_dir / "output.jsonl"
    output_path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )


# Sample events for testing
_ASSISTANT_EVENT = {
    "type": "assistant",
    "message": {
        "role": "assistant",
        "content": [{"type": "text", "text": "Hello from assistant"}],
    },
}

_TOOL_USE_EVENT = {
    "type": "assistant",
    "message": {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_abc123",
                "name": "Read",
                "input": {"file_path": "/tmp/test.py"},
            }
        ],
    },
}

_TOOL_RESULT_EVENT = {
    "type": "user",
    "message": {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_abc123",
                "content": "file contents here",
            }
        ],
    },
}

_RESULT_EVENT = {
    "type": "result",
    "result": "Task completed.",
    "usage": {
        "input_tokens": 1200,
        "output_tokens": 350,
    },
}


# ---------------------------------------------------------------------------
# parse_event_id unit tests (supporting both ID directions)
# ---------------------------------------------------------------------------


def test_parse_event_id_round_trips() -> None:
    event_id = make_event_id("p1", 5)
    assert event_id == "p1:5"
    result = parse_event_id(event_id)
    assert result == ("p1", 5)


def test_parse_event_id_returns_none_for_missing_separator() -> None:
    assert parse_event_id("p1") is None
    assert parse_event_id("") is None


def test_parse_event_id_returns_none_for_bad_index() -> None:
    assert parse_event_id("p1:abc") is None
    assert parse_event_id("p1:-1") is None


# ---------------------------------------------------------------------------
# APP-THREAD-01: GET /api/threads/{chat_id}/events/{event_id}
# ---------------------------------------------------------------------------


def test_get_event_returns_correct_payload(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-01: Valid event_id returns the raw event payload."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    _write_artifact_output(project_root, "p1", [_ASSISTANT_EVENT, _RESULT_EVENT])

    response = client.get("/api/threads/c1/events/p1:0")

    assert response.status_code == 200
    payload = response.json()
    assert payload["event_id"] == "p1:0"
    assert payload["spawn_id"] == "p1"
    assert payload["line_index"] == 0
    assert "payload" in payload


def test_get_event_by_spawn_id_direct(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-01: Using a spawn_id directly in the chat_id field also works."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    _write_artifact_output(project_root, "p1", [_ASSISTANT_EVENT, _TOOL_USE_EVENT])

    response = client.get("/api/threads/p1/events/p1:1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["line_index"] == 1


def test_get_event_invalid_event_id_format(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-01: Malformed event_id returns 400."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")

    response = client.get("/api/threads/c1/events/badformat")

    assert response.status_code == 400


def test_get_event_unknown_chat_id_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-01: Unknown chat_id returns 404."""
    client, _project_root = app_client

    response = client.get("/api/threads/c999/events/p1:0")

    assert response.status_code == 404


def test_get_event_out_of_range_line_index_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-01: Line index beyond artifact length returns 404."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    _write_artifact_output(project_root, "p1", [_ASSISTANT_EVENT])

    response = client.get("/api/threads/c1/events/p1:99")

    assert response.status_code == 404


def test_get_event_spawn_not_in_chat_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-01: Event spawn_id not associated with chat_id returns 404."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    _write_spawn(project_root, spawn_id="p2", chat_id="c2")
    _write_artifact_output(project_root, "p2", [_ASSISTANT_EVENT])

    # p2 belongs to c2, not c1
    response = client.get("/api/threads/c1/events/p2:0")

    assert response.status_code == 404


def test_get_event_stable_id_survives_restart(
    tmp_path: Path,
) -> None:
    """APP-THREAD-01: Event ID stays the same across app restarts (artifact-derived)."""
    project_root = tmp_path

    # First app instance
    manager = FakeManager(project_root=project_root)
    app1 = create_app(cast("Any", manager), allow_unsafe_no_permissions=True)
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    _write_artifact_output(project_root, "p1", [_ASSISTANT_EVENT, _RESULT_EVENT])
    with TestClient(app1) as client1:
        r1 = client1.get("/api/threads/c1/events/p1:0")
        assert r1.status_code == 200
        event_id_first = r1.json()["event_id"]

    # Second app instance (simulating restart)
    manager2 = FakeManager(project_root=project_root)
    app2 = create_app(cast("Any", manager2), allow_unsafe_no_permissions=True)
    with TestClient(app2) as client2:
        r2 = client2.get("/api/threads/c1/events/p1:0")
        assert r2.status_code == 200
        event_id_second = r2.json()["event_id"]

    assert event_id_first == event_id_second


# ---------------------------------------------------------------------------
# APP-THREAD-02: GET /api/threads/{chat_id}/tool-calls/{call_id}
# ---------------------------------------------------------------------------


def test_get_tool_call_returns_tool_use_payload(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-02: Valid call_id for a tool_use event returns the payload."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    # line 0: assistant text; line 1: tool_use; line 2: tool_result
    _write_artifact_output(
        project_root, "p1", [_ASSISTANT_EVENT, _TOOL_USE_EVENT, _TOOL_RESULT_EVENT]
    )

    response = client.get("/api/threads/c1/tool-calls/p1:1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["call_id"] == "p1:1"
    assert payload["spawn_id"] == "p1"
    assert payload["line_index"] == 1
    assert "payload" in payload


def test_get_tool_call_non_tool_line_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-02: Requesting a call_id that points to a non-tool event returns 404."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    _write_artifact_output(project_root, "p1", [_ASSISTANT_EVENT])

    response = client.get("/api/threads/c1/tool-calls/p1:0")

    assert response.status_code == 404


def test_list_tool_calls_returns_all_tool_events(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-02: List endpoint returns all tool_use events for a thread."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    _write_artifact_output(
        project_root,
        "p1",
        [_ASSISTANT_EVENT, _TOOL_USE_EVENT, _TOOL_RESULT_EVENT, _RESULT_EVENT],
    )

    response = client.get("/api/threads/c1/tool-calls")

    assert response.status_code == 200
    payload = response.json()
    assert "tool_calls" in payload
    # Only _TOOL_USE_EVENT qualifies
    assert len(payload["tool_calls"]) == 1
    assert payload["tool_calls"][0]["call_id"] == "p1:1"


def test_list_tool_calls_empty_when_no_tool_events(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-02: No tool_use events → empty tool_calls list."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    _write_artifact_output(project_root, "p1", [_ASSISTANT_EVENT, _RESULT_EVENT])

    response = client.get("/api/threads/c1/tool-calls")

    assert response.status_code == 200
    assert response.json()["tool_calls"] == []


def test_get_tool_call_unknown_thread_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-02: Unknown thread ID returns 404 for tool-call lookup."""
    client, _project_root = app_client

    response = client.get("/api/threads/c999/tool-calls/p1:0")

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# APP-THREAD-03: GET /api/threads/{chat_id}/token-usage
# ---------------------------------------------------------------------------


def test_token_usage_from_result_event(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-03: Token usage is extracted from persisted artifacts."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    _write_artifact_output(project_root, "p1", [_ASSISTANT_EVENT, _RESULT_EVENT])

    response = client.get("/api/threads/c1/token-usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["spawn_id"] == "p1"
    assert payload["input_tokens"] == 1200
    assert payload["output_tokens"] == 350


def test_token_usage_zero_when_no_artifacts(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-03: No artifact → token fields are None (not an error)."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    # No artifact output written — empty state.

    response = client.get("/api/threads/c1/token-usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["spawn_id"] == "p1"
    assert payload["input_tokens"] is None
    assert payload["output_tokens"] is None
    assert payload["total_cost_usd"] is None


def test_token_usage_unknown_thread_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-03: Unknown thread returns 404."""
    client, _project_root = app_client

    response = client.get("/api/threads/c999/token-usage")

    assert response.status_code == 404


def test_token_usage_works_with_tokens_json(
    app_client: tuple[TestClient, Path],
) -> None:
    """APP-THREAD-03: Token usage from tokens.json artifact is also supported."""
    client, project_root = app_client
    _write_spawn(project_root, spawn_id="p1", chat_id="c1")
    # Write tokens.json artifact instead of embedding in output.jsonl
    artifact_dir = _state_root(project_root) / "artifacts" / "p1"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "tokens.json").write_text(
        json.dumps({"input_tokens": 500, "output_tokens": 100}),
        encoding="utf-8",
    )
    _write_artifact_output(project_root, "p1", [_ASSISTANT_EVENT])

    response = client.get("/api/threads/c1/token-usage")

    assert response.status_code == 200
    payload = response.json()
    assert payload["input_tokens"] == 500
    assert payload["output_tokens"] == 100


def test_thread_routes_do_not_require_live_connection(
    tmp_path: Path,
) -> None:
    """APP-THREAD-01..03: All inspector endpoints work on a completed, static session."""
    project_root = tmp_path
    manager = FakeManager(project_root=project_root)
    app = create_app(cast("Any", manager), allow_unsafe_no_permissions=True)

    _write_spawn(project_root, spawn_id="p1", chat_id="c1", status="succeeded")
    _write_artifact_output(
        project_root,
        "p1",
        [_ASSISTANT_EVENT, _TOOL_USE_EVENT, _RESULT_EVENT],
    )

    with TestClient(app) as client:
        events_resp = client.get("/api/threads/c1/events/p1:0")
        assert events_resp.status_code == 200

        tool_resp = client.get("/api/threads/c1/tool-calls/p1:1")
        assert tool_resp.status_code == 200

        usage_resp = client.get("/api/threads/c1/token-usage")
        assert usage_resp.status_code == 200
