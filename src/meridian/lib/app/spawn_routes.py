"""Spawn-related route handlers extracted from server.py."""

from __future__ import annotations

import asyncio
import base64
import json as json_module
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from uuid import uuid4

from pydantic import BaseModel, model_validator

from meridian.lib.app.api_models import CursorEnvelope, SpawnProjection, SpawnStatsProjection
from meridian.lib.config.project_paths import ProjectPaths
from meridian.lib.core.lifecycle import SpawnLifecycleService
from meridian.lib.core.spawn_lifecycle import TERMINAL_SPAWN_STATUSES
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.request import LaunchArgvIntent, LaunchRuntime, SpawnRequest
from meridian.lib.state import spawn_store
from meridian.lib.streaming.signal_canceller import SignalCanceller
from meridian.lib.streaming.spawn_manager import SpawnManager

if TYPE_CHECKING:
    from meridian.lib.app.stream import StreamBroadcaster
    from meridian.lib.state.spawn_store import SpawnRecord

_SPAWN_ID_RE = re.compile(r"^p\d+$")
logger = logging.getLogger(__name__)


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    def post(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...
    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...


class HTTPExceptionCallable(Protocol):
    """Protocol for HTTPException constructor."""

    def __call__(
        self,
        status_code: int,
        detail: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> Exception: ...


class PermissionRequest(BaseModel):
    """REST permission payload for creating one spawn."""

    sandbox: str
    approval: str


class SpawnCreateRequest(BaseModel):
    """REST payload for creating one spawn."""

    harness: str
    prompt: str
    model: str | None = None
    agent: str | None = None
    permissions: PermissionRequest | None = None


class InjectRequest(BaseModel):
    """REST payload for injecting one user message."""

    text: str | None = None
    interrupt: bool = False

    @model_validator(mode="after")
    def _exactly_one(self) -> InjectRequest:
        text_set = self.text is not None and self.text.strip() != ""
        if text_set and self.interrupt:
            raise ValueError("text and interrupt are mutually exclusive")
        if not text_set and not self.interrupt:
            raise ValueError("provide text or interrupt: true")
        return self


def validate_spawn_id(raw: str, http_exception: HTTPExceptionCallable) -> SpawnId:
    """Validate spawn ID format and return typed SpawnId."""
    if not _SPAWN_ID_RE.match(raw):
        raise http_exception(status_code=400, detail=f"invalid spawn ID: {raw}")
    return SpawnId(raw)


def spawn_is_terminal(status: str) -> bool:
    """Check if spawn status is terminal."""
    return status in TERMINAL_SPAWN_STATUSES


def require_spawn(
    state_root: Path,
    spawn_id: SpawnId,
    http_exception: HTTPExceptionCallable,
) -> SpawnRecord:
    """Get spawn record or raise 404."""
    record = spawn_store.get_spawn(state_root, spawn_id)
    if record is None:
        raise http_exception(status_code=404, detail="spawn not found")
    return record


def require_active_manager(
    spawn_manager: SpawnManager,
    spawn_id: SpawnId,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Require spawn has active connection in manager."""
    if spawn_manager.get_connection(spawn_id) is None:
        raise http_exception(status_code=404, detail="spawn not found")


def require_not_terminal(
    record: SpawnRecord,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Require spawn is not in terminal state."""
    if spawn_is_terminal(record.status):
        raise http_exception(status_code=410, detail="spawn already terminal")


def require_not_finalizing(
    record: SpawnRecord,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Require spawn is not finalizing."""
    if record.status == "finalizing":
        raise http_exception(
            status_code=503,
            detail="spawn is finalizing",
            headers={"Retry-After": "2"},
        )


def register_spawn_routes(
    app: object,
    spawn_manager: SpawnManager,
    *,
    state_root: Path,
    project_paths: ProjectPaths,
    lifecycle_service: SpawnLifecycleService,
    spawn_id_lock: asyncio.Lock,
    background_finalize_tasks: set[asyncio.Task[None]],
    event_broadcaster: StreamBroadcaster | None = None,
    allow_unsafe_no_permissions: bool = False,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Register spawn-related routes on the FastAPI app."""

    typed_app = cast("_FastAPIApp", app)

    async def reserve_spawn_id(
        *,
        chat_id: str,
        model: str,
        agent: str,
        harness: str,
        prompt: str,
    ) -> SpawnId:
        async with spawn_id_lock:
            return SpawnId(
                await asyncio.to_thread(
                    lifecycle_service.start,
                    chat_id=chat_id,
                    model=model,
                    agent=agent,
                    harness=harness,
                    kind="streaming",
                    prompt=prompt,
                    launch_mode="app",
                    runner_pid=os.getpid(),
                    status="running",
                )
            )

    def _validate_spawn_id(raw: str) -> SpawnId:
        return validate_spawn_id(raw, http_exception)

    def _require_spawn(spawn_id: SpawnId) -> SpawnRecord:
        return require_spawn(state_root, spawn_id, http_exception)

    def _require_active_manager(spawn_id: SpawnId) -> None:
        require_active_manager(spawn_manager, spawn_id, http_exception)

    def _require_not_terminal(record: SpawnRecord) -> None:
        require_not_terminal(record, http_exception)

    def _require_not_finalizing(record: SpawnRecord) -> None:
        require_not_finalizing(record, http_exception)

    def _broadcast(event_type: str, payload: dict[str, object]) -> None:
        if event_broadcaster is None:
            return
        event: dict[str, object] = {"type": event_type, "timestamp": time.time()}
        event.update(payload)
        event_broadcaster.broadcast(event)

    async def _background_finalize(spawn_id: SpawnId) -> None:
        outcome = await spawn_manager.wait_for_completion(spawn_id)
        if outcome is None:
            return
        lifecycle_service.finalize(
            str(spawn_id),
            outcome.status,
            outcome.exit_code,
            origin="runner",
            duration_secs=outcome.duration_secs,
            error=outcome.error,
        )
        _broadcast(
            "spawn.finalized",
            {
                "spawn_id": str(spawn_id),
                "status": outcome.status,
                "exit_code": outcome.exit_code,
                "duration_secs": outcome.duration_secs,
                "error": outcome.error,
            },
        )

    async def create_spawn(body: SpawnCreateRequest) -> dict[str, object]:
        prompt = body.prompt.strip()
        if not prompt:
            raise http_exception(
                status_code=400,
                detail="prompt is required",
            )

        try:
            harness_id = HarnessId(body.harness.strip().lower())
        except ValueError as exc:
            raise http_exception(
                status_code=400,
                detail=f"unsupported harness '{body.harness}'",
            ) from exc

        permissions = body.permissions
        spawn_sandbox: str | None = None
        spawn_approval: str | None = None
        unsafe_no_permissions = False
        if permissions is None:
            if not allow_unsafe_no_permissions:
                raise http_exception(
                    status_code=400,
                    detail=(
                        "permissions block is required: provide "
                        "permissions.sandbox and permissions.approval"
                    ),
                )
            logger.warning(
                "Handling /api/spawns request without permission metadata because "
                "--allow-unsafe-no-permissions is enabled."
            )
            unsafe_no_permissions = True
        else:
            spawn_sandbox = permissions.sandbox.strip()
            spawn_approval = permissions.approval.strip()
            if not spawn_sandbox:
                raise http_exception(
                    status_code=400,
                    detail="permissions.sandbox is required",
                )
            if not spawn_approval:
                raise http_exception(
                    status_code=400,
                    detail="permissions.approval is required",
                )

        spawn_id = await reserve_spawn_id(
            chat_id=str(uuid4()),
            model=(body.model.strip() if body.model is not None else "") or "unknown",
            agent=(body.agent.strip() if body.agent is not None else "") or "unknown",
            harness=harness_id.value,
            prompt=prompt,
        )
        config = ConnectionConfig(
            spawn_id=spawn_id,
            harness_id=harness_id,
            prompt=prompt,
            repo_root=project_paths.execution_cwd,
            env_overrides={},
        )
        spawn_req = SpawnRequest(
            prompt=prompt,
            model=body.model.strip() if body.model and body.model.strip() else None,
            harness=harness_id.value,
            agent=body.agent.strip() if body.agent else None,
            sandbox=spawn_sandbox,
            approval=spawn_approval,
        )
        launch_runtime = LaunchRuntime(
            argv_intent=LaunchArgvIntent.SPEC_ONLY,
            unsafe_no_permissions=unsafe_no_permissions,
            state_root=state_root.as_posix(),
            project_paths_repo_root=project_paths.repo_root.as_posix(),
            project_paths_execution_cwd=project_paths.execution_cwd.as_posix(),
        )
        launch_ctx = build_launch_context(
            spawn_id=str(spawn_id),
            request=spawn_req,
            runtime=launch_runtime,
            harness_registry=get_default_harness_registry(),
        )

        try:
            connection = await spawn_manager.start_spawn(config, launch_ctx.spec)
            await spawn_manager._start_heartbeat(spawn_id)  # pyright: ignore[reportPrivateUsage]
        except Exception as exc:
            lifecycle_service.finalize(
                str(spawn_id),
                "failed",
                1,
                origin="launch_failure",
                error=str(exc),
            )
            raise http_exception(
                status_code=400,
                detail=str(exc),
            ) from exc
        finalize_task = asyncio.create_task(_background_finalize(spawn_id))
        background_finalize_tasks.add(finalize_task)
        finalize_task.add_done_callback(background_finalize_tasks.discard)

        _broadcast(
            "spawn.created",
            {
                "spawn_id": str(config.spawn_id),
                "harness": connection.harness_id.value,
                "state": connection.state,
            },
        )

        return {
            "spawn_id": str(config.spawn_id),
            "harness": connection.harness_id.value,
            "state": connection.state,
            "capabilities": asdict(connection.capabilities),
        }

    async def list_spawns() -> list[dict[str, str]]:
        spawns = spawn_manager.list_spawns()
        return [{"spawn_id": str(spawn_id)} for spawn_id in spawns]

    async def get_spawn(spawn_id: str) -> dict[str, object]:
        typed_spawn_id = _validate_spawn_id(spawn_id)
        connection = spawn_manager.get_connection(typed_spawn_id)
        if connection is None:
            raise http_exception(
                status_code=404,
                detail="spawn not found",
            )
        return {
            "spawn_id": spawn_id,
            "harness": connection.harness_id.value,
            "state": connection.state,
        }

    async def inject_message(
        spawn_id: str,
        body: InjectRequest,
    ) -> dict[str, object]:
        typed_spawn_id = _validate_spawn_id(spawn_id)
        record = _require_spawn(typed_spawn_id)
        _require_not_terminal(record)
        _require_not_finalizing(record)
        _require_active_manager(typed_spawn_id)

        if body.interrupt:
            result = await spawn_manager.interrupt(typed_spawn_id, source="rest")
            if not result.success:
                raise http_exception(
                    status_code=400,
                    detail=result.error or "interrupt failed",
                )
            response: dict[str, object] = {"ok": True}
            if result.inbound_seq is not None:
                response["inbound_seq"] = result.inbound_seq
            if result.noop:
                response["noop"] = True
            return response

        text = (body.text or "").strip()
        result = await spawn_manager.inject(typed_spawn_id, text, source="rest")
        if not result.success:
            raise http_exception(
                status_code=400,
                detail=result.error or "inject failed",
            )
        response = {"ok": True}
        if result.inbound_seq is not None:
            response["inbound_seq"] = result.inbound_seq
        return response

    async def cancel_spawn(spawn_id: str) -> dict[str, object]:
        typed_spawn_id = _validate_spawn_id(spawn_id)
        record = _require_spawn(typed_spawn_id)
        if spawn_is_terminal(record.status):
            raise http_exception(
                status_code=409,
                detail=f"spawn already terminal: {record.status}",
            )
        canceller = SignalCanceller(state_root=state_root, manager=spawn_manager)
        try:
            outcome = await canceller.cancel(typed_spawn_id)
        except ValueError as exc:
            raise http_exception(status_code=404, detail="spawn not found") from exc
        if outcome.already_terminal:
            raise http_exception(
                status_code=409,
                detail=f"spawn already terminal: {outcome.status}",
            )
        if outcome.finalizing:
            raise http_exception(
                status_code=503,
                detail="spawn is finalizing",
                headers={"Retry-After": "2"},
            )
        return {
            "ok": True,
            "status": outcome.status,
            "origin": outcome.origin,
        }

    typed_app.post("/api/spawns")(create_spawn)
    typed_app.get("/api/spawns")(list_spawns)
    typed_app.get("/api/spawns/{spawn_id}")(get_spawn)
    typed_app.post("/api/spawns/{spawn_id}/inject")(inject_message)
    typed_app.post("/api/spawns/{spawn_id}/cancel")(cancel_spawn)


# ---- Cursor Helpers ----

def _encode_cursor(spawn_id: str, created_at: str) -> str:
    """Encode pagination cursor from spawn ID and timestamp."""
    data = {"id": spawn_id, "ts": created_at}
    return base64.urlsafe_b64encode(json_module.dumps(data).encode()).decode()


def _decode_cursor(cursor: str) -> tuple[str, str] | None:
    """Decode pagination cursor to (spawn_id, created_at). Returns None if invalid."""
    try:
        data = json_module.loads(base64.urlsafe_b64decode(cursor.encode()))
        return (data["id"], data["ts"])
    except (ValueError, KeyError, json_module.JSONDecodeError):
        return None


def _spawn_to_projection(record: SpawnRecord) -> SpawnProjection:
    """Convert spawn record to API projection."""
    sort_ts = record.started_at or ""
    return SpawnProjection(
        spawn_id=record.id,
        status=record.status,
        harness=record.harness or "",
        model=record.model or "",
        agent=record.agent or "",
        work_id=record.work_id if record.work_id else None,
        desc=record.desc or "",
        created_at=sort_ts,
        started_at=record.started_at,
        finished_at=record.finished_at,
    )


def register_spawn_query_routes(
    app: object,
    *,
    state_root: Path,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Register expanded spawn query routes (filters, pagination, stats)."""
    from importlib import import_module

    try:
        fastapi_module = import_module("fastapi")
        Query = fastapi_module.Query
    except ModuleNotFoundError as exc:
        msg = "FastAPI is required"
        raise RuntimeError(msg) from exc

    typed_app = cast("_FastAPIApp", app)

    async def list_spawns_paginated(
        work_id: str | None = Query(default=None, description="Filter by work item"),
        status: str | None = Query(default=None, description="Filter by status"),
        agent: str | None = Query(default=None, description="Filter by agent"),
        harness: str | None = Query(default=None, description="Filter by harness"),
        limit: int = Query(default=20, ge=1, le=100, description="Page size"),
        cursor: str | None = Query(default=None, description="Pagination cursor"),
    ) -> CursorEnvelope[SpawnProjection]:
        """List spawns with filtering and cursor-based pagination."""
        from meridian.lib.state.reaper import reconcile_spawns

        # Build filters dict for spawn_store
        filters: dict[str, str] = {}
        if work_id:
            filters["work_id"] = work_id.strip()
        if status:
            filters["status"] = status.strip()
        if agent:
            filters["agent"] = agent.strip()
        if harness:
            filters["harness"] = harness.strip()

        # Get all matching spawns
        spawns = reconcile_spawns(
            state_root,
            spawn_store.list_spawns(state_root, filters=filters if filters else None),
        )

        # Sort by started_at desc, id desc for stable pagination
        def sort_key(s: SpawnRecord) -> tuple[str, str]:
            return (s.started_at or "", s.id)

        spawns.sort(key=sort_key, reverse=True)

        # Apply cursor filter
        if cursor:
            decoded = _decode_cursor(cursor)
            if decoded is None:
                raise http_exception(status_code=400, detail="invalid cursor")
            cursor_id, cursor_ts = decoded
            # Find position after cursor
            cursor_key = (cursor_ts, cursor_id)
            spawns = [s for s in spawns if (s.started_at or "", s.id) < cursor_key]

        # Take one extra to check if there are more
        page = spawns[: limit + 1]
        has_more = len(page) > limit
        page = page[:limit]

        # Build next cursor
        next_cursor = None
        if has_more and page:
            last = page[-1]
            next_cursor = _encode_cursor(last.id, last.started_at or "")

        return CursorEnvelope(
            items=[_spawn_to_projection(s) for s in page],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def get_spawn_stats(
        work_id: str | None = Query(default=None, description="Filter by work item"),
    ) -> SpawnStatsProjection:
        """Get aggregated spawn statistics."""
        from meridian.lib.state.reaper import reconcile_spawns

        filters = {"work_id": work_id.strip()} if work_id else None
        spawns = reconcile_spawns(
            state_root,
            spawn_store.list_spawns(state_root, filters=filters),
        )

        running = 0
        queued = 0
        succeeded = 0
        failed = 0
        cancelled = 0
        finalizing = 0

        for spawn in spawns:
            if spawn.status == "running":
                running += 1
            elif spawn.status == "queued":
                queued += 1
            elif spawn.status == "succeeded":
                succeeded += 1
            elif spawn.status == "failed":
                failed += 1
            elif spawn.status == "cancelled":
                cancelled += 1
            elif spawn.status == "finalizing":
                finalizing += 1

        total = running + queued + succeeded + failed + cancelled + finalizing

        return SpawnStatsProjection(
            running=running,
            queued=queued,
            succeeded=succeeded,
            failed=failed,
            cancelled=cancelled,
            finalizing=finalizing,
            total=total,
        )

    async def get_spawn_events(
        spawn_id: str,
        since: int | None = Query(default=None, description="Start from line number"),
        tail: int | None = Query(default=None, ge=1, le=1000, description="Last N events"),
    ) -> list[dict[str, object]]:
        """Get events from a spawn's output.jsonl."""
        typed_spawn_id = validate_spawn_id(spawn_id, http_exception)
        
        # Check spawn exists
        record = spawn_store.get_spawn(state_root, typed_spawn_id)
        if record is None:
            raise http_exception(status_code=404, detail="spawn not found")

        output_path = state_root / "spawns" / str(typed_spawn_id) / "output.jsonl"
        if not output_path.exists():
            return []

        events: list[dict[str, object]] = []
        with output_path.open() as f:
            for i, line in enumerate(f):
                if since is not None and i < since:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json_module.loads(line)
                    event["_line"] = i
                    events.append(event)
                except json_module.JSONDecodeError:
                    continue

        if tail is not None:
            events = events[-tail:]

        return events

    # Register routes with query params
    # Note: The paginated list replaces the simple list from register_spawn_routes
    # We register with a different internal name but same path
    typed_app.get("/api/spawns/list")(list_spawns_paginated)
    typed_app.get("/api/spawns/stats")(get_spawn_stats)
    typed_app.get("/api/spawns/{spawn_id}/events")(get_spawn_events)


__all__ = [
    "HTTPExceptionCallable",
    "InjectRequest",
    "PermissionRequest",
    "SpawnCreateRequest",
    "register_spawn_query_routes",
    "register_spawn_routes",
    "require_active_manager",
    "require_not_finalizing",
    "require_not_terminal",
    "require_spawn",
    "spawn_is_terminal",
    "validate_spawn_id",
]
