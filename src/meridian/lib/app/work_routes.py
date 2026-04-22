"""Work-related route handlers for the app server."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.app.api_models import CursorEnvelope, WorkProjection
from meridian.lib.app.spawn_routes import HTTPExceptionCallable
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.event_store import lock_file

if TYPE_CHECKING:
    from meridian.lib.app.stream import StreamBroadcaster


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...
    def post(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...
    def put(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...


class WorkCreateRequest(BaseModel):
    """Request body for creating a work item."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str = ""


class ActiveWorkRequest(BaseModel):
    """Request body for setting active work item."""

    model_config = ConfigDict(frozen=True)

    work_id: str | None = None


class SyncResponse(BaseModel):
    """Response for sync trigger."""

    model_config = ConfigDict(frozen=True)

    status: str = "not_implemented"
    message: str = "Work sync is not yet implemented"


class _ActiveWorkState(BaseModel):
    """Persisted active work selection for app mode."""

    model_config = ConfigDict(frozen=True)

    work_id: str | None = None


def _active_work_state_path(project_state_dir: Path) -> Path:
    """Path for persisted app active-work selection."""
    return project_state_dir / "app" / "active_work.json"


def _active_work_lock_path(project_state_dir: Path) -> Path:
    """Lock path for active-work state updates."""
    return project_state_dir / "app" / "active_work.flock"


def _read_active_work_state(project_state_dir: Path) -> str | None:
    """Read persisted active work selection."""
    state_path = _active_work_state_path(project_state_dir)
    lock_path = _active_work_lock_path(project_state_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_file(lock_path):
        try:
            state = _ActiveWorkState.model_validate_json(state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        return state.work_id


def _write_active_work_state(project_state_dir: Path, work_id: str | None) -> None:
    """Persist active work selection atomically."""
    state_path = _active_work_state_path(project_state_dir)
    lock_path = _active_work_lock_path(project_state_dir)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_file(lock_path):
        atomic_write_text(
            state_path,
            _ActiveWorkState(work_id=work_id).model_dump_json(indent=2) + "\n",
        )


def _work_item_to_projection(
    item: object,
    *,
    project_root: Path,
    project_state_dir: Path,
    spawn_count: int = 0,
    session_count: int = 0,
    last_activity_at: str | None = None,
) -> WorkProjection:
    """Convert a work item to API projection."""
    from meridian.lib.ops.work_dashboard import work_dir_display

    # item is a WorkItem with name, status, description, created_at attributes
    name = getattr(item, "name", "")
    status = getattr(item, "status", "")
    description = getattr(item, "description", "")
    created_at = getattr(item, "created_at", "")

    return WorkProjection(
        work_id=name,
        name=name,
        status=status,
        description=description,
        work_dir=work_dir_display(project_root, project_state_dir, name),
        created_at=created_at,
        last_activity_at=last_activity_at,
        spawn_count=spawn_count,
        session_count=session_count,
    )


def register_work_routes(
    app: object,
    *,
    state_root: Path,
    project_state_dir: Path,
    project_root: Path,
    event_broadcaster: StreamBroadcaster | None = None,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Register work-related routes on the FastAPI app."""
    from importlib import import_module

    from meridian.lib.state import session_store, spawn_store, work_store

    try:
        fastapi_module = import_module("fastapi")
        Query = fastapi_module.Query
    except ModuleNotFoundError as exc:
        msg = "FastAPI is required"
        raise RuntimeError(msg) from exc

    typed_app = cast("_FastAPIApp", app)

    def _broadcast(event_type: str, payload: dict[str, object]) -> None:
        if event_broadcaster is None:
            return
        event_broadcaster.broadcast({"type": event_type, **payload})

    def _get_work_stats(work_id: str) -> tuple[int, int, str | None]:
        """Get spawn count, session count, and last activity for a work item."""
        spawns = spawn_store.list_spawns(state_root, filters={"work_id": work_id})
        spawn_count = len(spawns)

        sessions = session_store.list_active_sessions_for_work_id(state_root, work_id)
        session_count = len(sessions)

        # Get last activity from spawns
        last_activity: str | None = None
        for spawn in spawns:
            finished = getattr(spawn, "finished_at", None)
            started = getattr(spawn, "started_at", None)
            created = getattr(spawn, "created_at", None)
            ts = finished or started or created
            if ts and (last_activity is None or ts > last_activity):
                last_activity = ts

        return spawn_count, session_count, last_activity

    async def list_work_items(
        status: str | None = Query(default=None, description="Filter by status"),
        limit: int = Query(default=20, ge=1, le=100, description="Page size"),
    ) -> CursorEnvelope[WorkProjection]:
        """List work items with optional status filter."""
        status_filter = (status or "").strip()
        if status_filter == "done":
            items = work_store.list_archived_work_items(
                project_state_dir,
                limit=limit,
                all_archived=False,
            )
        else:
            items = work_store.list_work_items(project_state_dir)
            if status_filter:
                items = [item for item in items if item.status == status_filter]
            # Active listing uses newest-created first.
            items.sort(key=lambda x: x.created_at, reverse=True)

        # For now, simple pagination without cursor (can enhance later)
        page = items[:limit]

        projections: list[WorkProjection] = []
        for item in page:
            spawn_count, session_count, last_activity = _get_work_stats(item.name)
            projections.append(
                _work_item_to_projection(
                    item,
                    project_root=project_root,
                    project_state_dir=project_state_dir,
                    spawn_count=spawn_count,
                    session_count=session_count,
                    last_activity_at=last_activity,
                )
            )

        # No cursor is produced, so advertising has_more=True would cause
        # clients to loop forever on a null cursor. Report truthfully.
        return CursorEnvelope(
            items=projections,
            next_cursor=None,
            has_more=False,
        )

    async def get_work_item(work_id: str) -> WorkProjection:
        """Get work item details."""
        item = work_store.get_work_item(project_state_dir, work_id)
        if item is None:
            raise http_exception(status_code=404, detail=f"Work item '{work_id}' not found")

        spawn_count, session_count, last_activity = _get_work_stats(item.name)
        return _work_item_to_projection(
            item,
            project_root=project_root,
            project_state_dir=project_state_dir,
            spawn_count=spawn_count,
            session_count=session_count,
            last_activity_at=last_activity,
        )

    async def create_work_item(body: WorkCreateRequest) -> WorkProjection:
        """Create a new work item."""
        name = body.name.strip()
        if not name:
            raise http_exception(status_code=400, detail="name is required")

        # Check if work item already exists
        existing = work_store.get_work_item(project_state_dir, name)
        if existing is not None:
            if existing.status == "done":
                raise http_exception(
                    status_code=409,
                    detail=f"Work item '{name}' exists but is done. Reopen it first.",
                )
            raise http_exception(
                status_code=409,
                detail=f"Work item '{name}' already exists",
            )

        item = work_store.create_work_item(project_state_dir, name, body.description)
        _broadcast("work.created", {"work_id": item.name, "status": item.status})
        return _work_item_to_projection(
            item,
            project_root=project_root,
            project_state_dir=project_state_dir,
        )

    async def archive_work_item(work_id: str) -> WorkProjection:
        """Archive (mark as done) a work item."""
        item = work_store.get_work_item(project_state_dir, work_id)
        if item is None:
            raise http_exception(status_code=404, detail=f"Work item '{work_id}' not found")

        if item.status == "done":
            raise http_exception(
                status_code=409,
                detail=f"Work item '{work_id}' is already archived",
            )

        archived_item = work_store.archive_work_item(project_state_dir, work_id)
        _broadcast("work.archived", {"work_id": archived_item.name, "status": archived_item.status})
        return _work_item_to_projection(
            archived_item,
            project_root=project_root,
            project_state_dir=project_state_dir,
        )

    async def get_active_work() -> dict[str, str | None]:
        """Get the currently active work item for this session."""
        persisted_work_id = _read_active_work_state(project_state_dir)
        if persisted_work_id:
            persisted = work_store.get_work_item(project_state_dir, persisted_work_id)
            if persisted is not None and persisted.status != "done":
                return {"work_id": persisted.name}

        # Fallback: most recently created non-done work item.
        items = work_store.list_work_items(project_state_dir)
        if not items:
            return {"work_id": None}

        # Sort by created_at desc and return most recent
        items.sort(key=lambda x: x.created_at, reverse=True)
        fallback_work_id = items[0].name
        _write_active_work_state(project_state_dir, fallback_work_id)
        return {"work_id": fallback_work_id}

    async def set_active_work(body: ActiveWorkRequest) -> dict[str, str | None]:
        """Set the active work item."""
        work_id = body.work_id

        if work_id is None:
            # Clear active work
            _write_active_work_state(project_state_dir, None)
            _broadcast("work.active_changed", {"work_id": None})
            return {"work_id": None}

        item = work_store.get_work_item(project_state_dir, work_id)
        if item is None:
            raise http_exception(status_code=404, detail=f"Work item '{work_id}' not found")

        if item.status == "done":
            raise http_exception(
                status_code=409,
                detail=f"Work item '{work_id}' is archived. Reopen it first.",
            )

        _write_active_work_state(project_state_dir, item.name)
        _broadcast("work.active_changed", {"work_id": item.name})
        return {"work_id": item.name}

    async def trigger_sync(work_id: str) -> SyncResponse:
        """Trigger sync for a work item. Returns 501 - not yet implemented."""
        # Check work item exists
        item = work_store.get_work_item(project_state_dir, work_id)
        if item is None:
            raise http_exception(status_code=404, detail=f"Work item '{work_id}' not found")

        # Return 501 Not Implemented
        raise http_exception(
            status_code=501,
            detail="Work sync is not yet implemented. Depends on hook infrastructure.",
        )

    async def get_sync_status(work_id: str, op_id: str) -> SyncResponse:
        """Get sync operation status. Returns 501 - not yet implemented."""
        _ = op_id  # Unused for now

        # Check work item exists
        item = work_store.get_work_item(project_state_dir, work_id)
        if item is None:
            raise http_exception(status_code=404, detail=f"Work item '{work_id}' not found")

        # Return 501 Not Implemented
        raise http_exception(
            status_code=501,
            detail="Work sync is not yet implemented. Depends on hook infrastructure.",
        )

    # Register routes
    typed_app.get("/api/work")(list_work_items)
    typed_app.get("/api/work/active")(get_active_work)
    typed_app.put("/api/work/active")(set_active_work)
    typed_app.post("/api/work")(create_work_item)
    typed_app.get("/api/work/{work_id}")(get_work_item)
    typed_app.post("/api/work/{work_id}/archive")(archive_work_item)
    typed_app.post("/api/work/{work_id}/sync")(trigger_sync)
    typed_app.get("/api/work/{work_id}/sync/{op_id}")(get_sync_status)


__all__ = [
    "ActiveWorkRequest",
    "SyncResponse",
    "WorkCreateRequest",
    "register_work_routes",
]
