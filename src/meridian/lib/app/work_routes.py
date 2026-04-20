"""Work-related route handlers for the app server."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.app.api_models import CursorEnvelope, WorkProjection
from meridian.lib.app.spawn_routes import HTTPExceptionCallable


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


def _work_item_to_projection(
    item: object,
    *,
    repo_root: Path,
    repo_state_root: Path,
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
        work_dir=work_dir_display(repo_root, repo_state_root, name),
        created_at=created_at,
        last_activity_at=last_activity_at,
        spawn_count=spawn_count,
        session_count=session_count,
    )


def register_work_routes(
    app: object,
    *,
    state_root: Path,
    repo_state_root: Path,
    repo_root: Path,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Register work-related routes on the FastAPI app."""
    from importlib import import_module
    from typing import Annotated

    from meridian.lib.state import session_store, spawn_store, work_store

    try:
        fastapi_module = import_module("fastapi")
        Query = fastapi_module.Query
    except ModuleNotFoundError as exc:
        msg = "FastAPI is required"
        raise RuntimeError(msg) from exc

    typed_app = cast("_FastAPIApp", app)

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
        status: Annotated[str | None, Query(description="Filter by status")] = None,
        limit: Annotated[int, Query(ge=1, le=100, description="Page size")] = 20,
    ) -> CursorEnvelope[WorkProjection]:
        """List work items with optional status filter."""
        items = work_store.list_work_items(repo_state_root)

        # Apply status filter
        if status:
            items = [item for item in items if item.status == status.strip()]

        # Sort by created_at desc
        items.sort(key=lambda x: x.created_at, reverse=True)

        # For now, simple pagination without cursor (can enhance later)
        page = items[:limit]

        projections: list[WorkProjection] = []
        for item in page:
            spawn_count, session_count, last_activity = _get_work_stats(item.name)
            projections.append(
                _work_item_to_projection(
                    item,
                    repo_root=repo_root,
                    repo_state_root=repo_state_root,
                    spawn_count=spawn_count,
                    session_count=session_count,
                    last_activity_at=last_activity,
                )
            )

        return CursorEnvelope(
            items=projections,
            next_cursor=None,  # Simplified for now
            has_more=len(items) > limit,
        )

    async def get_work_item(work_id: str) -> WorkProjection:
        """Get work item details."""
        item = work_store.get_work_item(repo_state_root, work_id)
        if item is None:
            raise http_exception(status_code=404, detail=f"Work item '{work_id}' not found")

        spawn_count, session_count, last_activity = _get_work_stats(item.name)
        return _work_item_to_projection(
            item,
            repo_root=repo_root,
            repo_state_root=repo_state_root,
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
        existing = work_store.get_work_item(repo_state_root, name)
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

        item = work_store.create_work_item(repo_state_root, name, body.description)
        return _work_item_to_projection(
            item,
            repo_root=repo_root,
            repo_state_root=repo_state_root,
        )

    async def archive_work_item(work_id: str) -> WorkProjection:
        """Archive (mark as done) a work item."""
        item = work_store.get_work_item(repo_state_root, work_id)
        if item is None:
            raise http_exception(status_code=404, detail=f"Work item '{work_id}' not found")

        if item.status == "done":
            raise http_exception(
                status_code=409,
                detail=f"Work item '{work_id}' is already archived",
            )

        archived_item = work_store.archive_work_item(repo_state_root, work_id)
        return _work_item_to_projection(
            archived_item,
            repo_root=repo_root,
            repo_state_root=repo_state_root,
        )

    async def get_active_work() -> dict[str, str | None]:
        """Get the currently active work item for this session."""
        # For app mode, we look at the most recently active work item
        # This is a simplified implementation - in full implementation,
        # this would be session-scoped
        items = work_store.list_work_items(repo_state_root)
        active_items = [item for item in items if item.status != "done"]

        if not active_items:
            return {"work_id": None}

        # Sort by created_at desc and return most recent
        active_items.sort(key=lambda x: x.created_at, reverse=True)
        return {"work_id": active_items[0].name}

    async def set_active_work(body: ActiveWorkRequest) -> dict[str, str | None]:
        """Set the active work item."""
        work_id = body.work_id

        if work_id is None:
            # Clear active work
            return {"work_id": None}

        item = work_store.get_work_item(repo_state_root, work_id)
        if item is None:
            raise http_exception(status_code=404, detail=f"Work item '{work_id}' not found")

        if item.status == "done":
            raise http_exception(
                status_code=409,
                detail=f"Work item '{work_id}' is archived. Reopen it first.",
            )

        return {"work_id": item.name}

    async def trigger_sync(work_id: str) -> SyncResponse:
        """Trigger sync for a work item. Returns 501 - not yet implemented."""
        # Check work item exists
        item = work_store.get_work_item(repo_state_root, work_id)
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
        item = work_store.get_work_item(repo_state_root, work_id)
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
