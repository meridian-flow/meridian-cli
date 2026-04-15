"""FastAPI application factory for Meridian app endpoints."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import uuid4

from pydantic import BaseModel, model_validator

from meridian.lib.core.spawn_lifecycle import TERMINAL_SPAWN_STATUSES
from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.harness.adapter import SpawnParams
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch.launch_types import ResolvedLaunchSpec
from meridian.lib.safety.permissions import (
    TieredPermissionResolver,
    UnsafeNoOpPermissionResolver,
    build_permission_config,
)
from meridian.lib.state import spawn_store
from meridian.lib.streaming.signal_canceller import SignalCanceller
from meridian.lib.streaming.spawn_manager import SpawnManager

_SPAWN_ID_RE = re.compile(r"^p\d+$")
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from meridian.lib.state.spawn_store import SpawnRecord

class _AppState(Protocol):
    """App state payload carrying shared runtime singletons."""

    spawn_manager: SpawnManager


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    state: _AppState

    def add_middleware(self, middleware_class: type[object], **kwargs: object) -> None: ...
    def add_exception_handler(
        self,
        exc_class_or_status_code: object,
        handler: Callable[..., object],
    ) -> None: ...
    def post(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...
    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...
    def delete(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...
    def mount(self, path: str, app: object, name: str | None = None) -> None: ...


class _FastAPIFactory(Protocol):
    """Callable FastAPI constructor surface used by create_app()."""

    def __call__(self, *, title: str, lifespan: object) -> object: ...


class _FastAPIModule(Protocol):
    FastAPI: _FastAPIFactory
    HTTPException: type[Exception]


class _FastAPICorsModule(Protocol):
    CORSMiddleware: type[object]


class _StaticFilesModule(Protocol):
    StaticFiles: type[object]


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


def create_app(
    spawn_manager: SpawnManager,
    *,
    allow_unsafe_no_permissions: bool = False,
) -> object:
    """Create the FastAPI application for Meridian app."""

    background_finalize_tasks: set[asyncio.Task[None]] = set()

    @asynccontextmanager
    async def lifespan(_: object) -> AsyncIterator[None]:
        # SpawnManager lifecycle is owned by caller for startup.
        yield
        await spawn_manager.shutdown()
        if background_finalize_tasks:
            await asyncio.gather(*tuple(background_finalize_tasks), return_exceptions=True)

    try:
        fastapi_module = import_module("fastapi")
        cors_module = import_module("fastapi.middleware.cors")
        validation_module = import_module("fastapi.exceptions")
        exception_handlers_module = import_module("fastapi.exception_handlers")
        responses_module = import_module("fastapi.responses")
    except ModuleNotFoundError as exc:
        msg = (
            "FastAPI app dependencies are not installed. "
            "Run `uv sync --extra app --extra dev`."
        )
        raise RuntimeError(msg) from exc

    fastapi = cast("_FastAPIModule", fastapi_module)
    cors = cast("_FastAPICorsModule", cors_module)
    app_obj = fastapi.FastAPI(title="Meridian App", lifespan=lifespan)
    app = cast("_FastAPIApp", app_obj)
    http_exception_cls = cast("Callable[..., Exception]", fastapi.HTTPException)
    request_validation_error_cls = cast(
        "type[Exception]",
        validation_module.RequestValidationError,
    )
    request_validation_exception_handler = cast(
        "Callable[[object, Exception], object]",
        exception_handlers_module.request_validation_exception_handler,
    )
    json_response_cls = cast("Callable[..., object]", responses_module.JSONResponse)

    app.add_middleware(
        cors.CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def _validation_error_handler(request: object, exc: Exception) -> object:
        error_factory = getattr(exc, "errors", None)
        if callable(error_factory):
            error_items = cast("list[object]", error_factory())
            for error_item in error_items:
                if not isinstance(error_item, dict):
                    continue
                error_dict = cast("dict[str, object]", error_item)
                context_obj = error_dict.get("ctx")
                if not isinstance(context_obj, dict):
                    continue
                context = cast("dict[str, object]", context_obj)
                underlying_error = context.get("error")
                if isinstance(underlying_error, ValueError):
                    return json_response_cls(
                        status_code=400,
                        content={"detail": str(underlying_error)},
                    )
        return await cast(
            "Any",
            request_validation_exception_handler,
        )(request, exc)

    app.add_exception_handler(request_validation_error_cls, _validation_error_handler)

    app.state.spawn_manager = spawn_manager

    state_root = spawn_manager.state_root
    repo_root = spawn_manager.repo_root
    spawn_id_lock = asyncio.Lock()

    async def _background_finalize(spawn_id: SpawnId) -> None:
        outcome = await spawn_manager.wait_for_completion(spawn_id)
        if outcome is None:
            return
        spawn_store.finalize_spawn(
            state_root,
            spawn_id,
            status=outcome.status,
            exit_code=outcome.exit_code,
            origin="runner",
            duration_secs=outcome.duration_secs,
            error=outcome.error,
        )

    async def reserve_spawn_id(
        *,
        chat_id: str,
        model: str,
        agent: str,
        harness: str,
        prompt: str,
    ) -> SpawnId:
        async with spawn_id_lock:
            return await asyncio.to_thread(
                spawn_store.start_spawn,
                state_root,
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

    def _validate_spawn_id(raw: str) -> SpawnId:
        if not _SPAWN_ID_RE.match(raw):
            raise http_exception_cls(status_code=400, detail=f"invalid spawn ID: {raw}")
        return SpawnId(raw)

    def _spawn_is_terminal(status: str) -> bool:
        return status in TERMINAL_SPAWN_STATUSES

    def _require_spawn(spawn_id: SpawnId) -> SpawnRecord:
        record = spawn_store.get_spawn(state_root, spawn_id)
        if record is None:
            raise http_exception_cls(status_code=404, detail="spawn not found")
        return record

    def _require_active_manager(spawn_id: SpawnId) -> None:
        if spawn_manager.get_connection(spawn_id) is None:
            raise http_exception_cls(status_code=404, detail="spawn not found")

    def _require_not_terminal(record: SpawnRecord) -> None:
        if _spawn_is_terminal(record.status):
            raise http_exception_cls(status_code=410, detail="spawn already terminal")

    def _require_not_finalizing(record: SpawnRecord) -> None:
        if record.status == "finalizing":
            raise http_exception_cls(
                status_code=503,
                detail="spawn is finalizing",
                headers={"Retry-After": "2"},
            )

    async def create_spawn(body: SpawnCreateRequest) -> dict[str, object]:
        prompt = body.prompt.strip()
        if not prompt:
            raise http_exception_cls(
                status_code=400,
                detail="prompt is required",
            )

        try:
            harness_id = HarnessId(body.harness.strip().lower())
        except ValueError as exc:
            raise http_exception_cls(
                status_code=400,
                detail=f"unsupported harness '{body.harness}'",
            ) from exc

        permissions = body.permissions
        if permissions is None:
            if not allow_unsafe_no_permissions:
                raise http_exception_cls(
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
            permission_resolver = UnsafeNoOpPermissionResolver()
        else:
            sandbox = permissions.sandbox.strip()
            approval = permissions.approval.strip()
            if not sandbox:
                raise http_exception_cls(
                    status_code=400,
                    detail="permissions.sandbox is required",
                )
            if not approval:
                raise http_exception_cls(
                    status_code=400,
                    detail="permissions.approval is required",
                )
            try:
                permission_config = build_permission_config(sandbox, approval=approval)
            except ValueError as exc:
                raise http_exception_cls(status_code=400, detail=str(exc)) from exc
            permission_resolver = TieredPermissionResolver(config=permission_config)

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
            repo_root=repo_root,
            env_overrides={},
        )
        adapter = get_default_harness_registry().get_subprocess_harness(harness_id)
        params = SpawnParams(
            prompt=prompt,
            model=ModelId(body.model.strip()) if body.model and body.model.strip() else None,
            agent=body.agent.strip() if body.agent else None,
        )
        spec: ResolvedLaunchSpec = adapter.resolve_launch_spec(params, permission_resolver)

        try:
            connection = await spawn_manager.start_spawn(config, spec)
            await spawn_manager._start_heartbeat(spawn_id)  # pyright: ignore[reportPrivateUsage]
        except Exception as exc:
            spawn_store.finalize_spawn(
                state_root,
                spawn_id,
                status="failed",
                exit_code=1,
                origin="launch_failure",
                error=str(exc),
            )
            raise http_exception_cls(
                status_code=400,
                detail=str(exc),
            ) from exc
        finalize_task = asyncio.create_task(_background_finalize(spawn_id))
        background_finalize_tasks.add(finalize_task)
        finalize_task.add_done_callback(background_finalize_tasks.discard)

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
            raise http_exception_cls(
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
                raise http_exception_cls(
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
            raise http_exception_cls(
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
        if _spawn_is_terminal(record.status):
            raise http_exception_cls(
                status_code=409,
                detail=f"spawn already terminal: {record.status}",
            )
        canceller = SignalCanceller(state_root=state_root, manager=spawn_manager)
        try:
            outcome = await canceller.cancel(typed_spawn_id)
        except ValueError as exc:
            raise http_exception_cls(status_code=404, detail="spawn not found") from exc
        if outcome.already_terminal:
            raise http_exception_cls(
                status_code=409,
                detail=f"spawn already terminal: {outcome.status}",
            )
        if outcome.finalizing:
            raise http_exception_cls(
                status_code=503,
                detail="spawn is finalizing",
                headers={"Retry-After": "2"},
            )
        return {
            "ok": True,
            "status": outcome.status,
            "origin": outcome.origin,
        }

    app.post("/api/spawns")(create_spawn)
    app.get("/api/spawns")(list_spawns)
    app.get("/api/spawns/{spawn_id}")(get_spawn)
    app.post("/api/spawns/{spawn_id}/inject")(inject_message)
    app.post("/api/spawns/{spawn_id}/cancel")(cancel_spawn)

    from meridian.lib.app.ws_endpoint import register_ws_routes

    register_ws_routes(
        app_obj,
        spawn_manager,
        validate_spawn_id=_validate_spawn_id,
    )

    frontend_dist = Path(__file__).resolve().parents[4] / "frontend" / "dist"
    if frontend_dist.is_dir():
        staticfiles_module = import_module("starlette.staticfiles")
        staticfiles = cast("_StaticFilesModule", staticfiles_module)
        staticfiles_factory = cast("Callable[..., object]", staticfiles.StaticFiles)
        app.mount(
            "/",
            staticfiles_factory(directory=str(frontend_dist), html=True),
            name="static",
        )

    return app_obj


__all__ = ["create_app"]
