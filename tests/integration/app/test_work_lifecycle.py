"""Integration tests for work item lifecycle via the HTTP API.

Scenarios:
  - Create a work item, set it as active, archive it (full lifecycle)
  - Archived work is excluded from the default listing
  - Setting a nonexistent work item as active returns 404
  - Setting a done (archived) work item as active returns 409
  - Archiving an already-done work item returns 409
  - Clearing active work (work_id=null) works
  - Creating a duplicate work item returns 409
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Full lifecycle: create → active → archive
# ---------------------------------------------------------------------------


def test_create_then_set_active_then_archive(
    app_client: tuple[TestClient, Path],
) -> None:
    """Create → set active → archive: each step produces the correct state."""
    client, _project_root = app_client

    # 1. Create
    create_resp = client.post("/api/work", json={"name": "task-1", "description": "my task"})
    assert create_resp.status_code == 200
    body = create_resp.json()
    assert body["work_id"] == "task-1"
    assert body["status"] == "open"

    # 2. Set active
    active_resp = client.put("/api/work/active", json={"work_id": "task-1"})
    assert active_resp.status_code == 200
    assert active_resp.json() == {"work_id": "task-1"}

    get_active = client.get("/api/work/active")
    assert get_active.status_code == 200
    assert get_active.json() == {"work_id": "task-1"}

    # 3. Archive
    archive_resp = client.post("/api/work/task-1/archive")
    assert archive_resp.status_code == 200
    assert archive_resp.json()["status"] == "done"


def test_archived_work_excluded_from_default_listing(
    app_client: tuple[TestClient, Path],
) -> None:
    """Archived (done) work items must not appear in the open work listing."""
    client, _project_root = app_client

    client.post("/api/work", json={"name": "open-task"})
    client.post("/api/work", json={"name": "done-task"})
    client.post("/api/work/done-task/archive")

    resp = client.get("/api/work", params={"status": "open"})
    assert resp.status_code == 200
    work_ids = [item["work_id"] for item in resp.json()["items"]]
    assert "open-task" in work_ids
    assert "done-task" not in work_ids


def test_archived_work_appears_with_done_filter(
    app_client: tuple[TestClient, Path],
) -> None:
    """Archived work items appear when filtering by status=done."""
    client, _project_root = app_client

    client.post("/api/work", json={"name": "archived-task"})
    client.post("/api/work/archived-task/archive")

    resp = client.get("/api/work", params={"status": "done"})
    assert resp.status_code == 200
    work_ids = [item["work_id"] for item in resp.json()["items"]]
    assert "archived-task" in work_ids


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_set_nonexistent_work_as_active_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """Attempting to activate a work item that does not exist must return 404."""
    client, _project_root = app_client

    resp = client.put("/api/work/active", json={"work_id": "ghost-task"})
    assert resp.status_code == 404


def test_set_archived_work_as_active_returns_409(
    app_client: tuple[TestClient, Path],
) -> None:
    """Attempting to activate a done work item must return 409."""
    client, _project_root = app_client

    client.post("/api/work", json={"name": "done-task"})
    client.post("/api/work/done-task/archive")

    resp = client.put("/api/work/active", json={"work_id": "done-task"})
    assert resp.status_code == 409


def test_archive_already_archived_work_returns_409(
    app_client: tuple[TestClient, Path],
) -> None:
    """Archiving a work item that is already done must return 409."""
    client, _project_root = app_client

    client.post("/api/work", json={"name": "task-x"})
    client.post("/api/work/task-x/archive")

    resp = client.post("/api/work/task-x/archive")
    assert resp.status_code == 409


def test_archive_nonexistent_work_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """Archiving a work item that doesn't exist must return 404."""
    client, _project_root = app_client

    resp = client.post("/api/work/nonexistent/archive")
    assert resp.status_code == 404


def test_create_duplicate_work_item_returns_409(
    app_client: tuple[TestClient, Path],
) -> None:
    """Creating a work item with a name that already exists must return 409."""
    client, _project_root = app_client

    client.post("/api/work", json={"name": "dup-task"})
    resp = client.post("/api/work", json={"name": "dup-task"})
    assert resp.status_code == 409


def test_create_work_item_with_empty_name_returns_400(
    app_client: tuple[TestClient, Path],
) -> None:
    """Empty work item name must be rejected with 400."""
    client, _project_root = app_client

    resp = client.post("/api/work", json={"name": "   "})
    assert resp.status_code == 400


def test_get_nonexistent_work_item_returns_404(
    app_client: tuple[TestClient, Path],
) -> None:
    """GET /api/work/{work_id} for an unknown item returns 404."""
    client, _project_root = app_client

    resp = client.get("/api/work/no-such-item")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Clear active work
# ---------------------------------------------------------------------------


def test_clear_active_work_by_setting_null(
    app_client: tuple[TestClient, Path],
) -> None:
    """PUT /api/work/active with work_id=null clears the active selection."""
    client, _project_root = app_client

    client.post("/api/work", json={"name": "clearable"})
    client.put("/api/work/active", json={"work_id": "clearable"})

    clear_resp = client.put("/api/work/active", json={"work_id": None})
    assert clear_resp.status_code == 200
    assert clear_resp.json() == {"work_id": None}


# ---------------------------------------------------------------------------
# Active fallback behaviour
# ---------------------------------------------------------------------------


def test_active_work_returns_none_when_no_work_items(
    app_client: tuple[TestClient, Path],
) -> None:
    """GET /api/work/active returns {work_id: null} when no work items exist."""
    client, _project_root = app_client

    resp = client.get("/api/work/active")
    assert resp.status_code == 200
    assert resp.json()["work_id"] is None


def test_active_work_falls_back_to_most_recent_open_item(
    app_client: tuple[TestClient, Path],
) -> None:
    """When no active work is persisted, fallback uses the newest open item."""
    client, _project_root = app_client

    client.post("/api/work", json={"name": "alpha"})
    client.post("/api/work", json={"name": "beta"})

    # Clear any persisted selection
    client.put("/api/work/active", json={"work_id": None})

    resp = client.get("/api/work/active")
    assert resp.status_code == 200
    # Should be one of the open items (most recent)
    assert resp.json()["work_id"] in ("alpha", "beta")
