"""FastAPI application factory for Meridian app endpoints."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

# Re-export for backward compatibility
from meridian.lib.app.spawn_routes import (
    InjectRequest,
    PermissionRequest,
    SpawnCreateRequest,
)
from meridian.lib.config.project_paths import resolve_project_paths
from meridian.lib.core.lifecycle import create_lifecycle_service
from meridian.lib.state.paths import resolve_repo_state_paths
from meridian.lib.streaming.spawn_manager import SpawnManager

logger = logging.getLogger(__name__)


class _AppState(Protocol):
    """App state payload carrying shared runtime singletons."""

    spawn_manager: SpawnManager
    stream_broadcaster: object


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
    http_exception_cls = fastapi.HTTPException
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
                if isinstance(underlying_error, ValueError) and "mutually exclusive" in str(
                    underlying_error
                ):
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
    project_paths = resolve_project_paths(repo_root=spawn_manager.repo_root)
    repo_state_root = resolve_repo_state_paths(project_paths.repo_root).root_dir
    lifecycle_service = create_lifecycle_service(project_paths.repo_root, state_root)
    spawn_id_lock = asyncio.Lock()

    # Import route registration functions
    from meridian.lib.app.spawn_routes import (
        HTTPExceptionCallable,
        register_spawn_query_routes,
        register_spawn_routes,
        validate_spawn_id,
    )
    from meridian.lib.app.stream import register_stream_routes
    from meridian.lib.app.work_routes import register_work_routes
    from meridian.lib.app.ws_endpoint import register_ws_routes
    from meridian.lib.core.types import SpawnId

    http_exception = cast("HTTPExceptionCallable", http_exception_cls)

    # Register expanded spawn query routes first so static paths win over
    # /api/spawns/{spawn_id} path parameter route.
    register_spawn_query_routes(
        app_obj,
        state_root=state_root,
        http_exception=http_exception,
    )

    # Register SSE stream routes and capture shared broadcaster.
    event_broadcaster = register_stream_routes(
        app_obj,
        spawn_manager,
        state_root=state_root,
    )

    # Register spawn routes
    register_spawn_routes(
        app_obj,
        spawn_manager,
        state_root=state_root,
        project_paths=project_paths,
        lifecycle_service=lifecycle_service,
        spawn_id_lock=spawn_id_lock,
        background_finalize_tasks=background_finalize_tasks,
        event_broadcaster=event_broadcaster,
        allow_unsafe_no_permissions=allow_unsafe_no_permissions,
        http_exception=http_exception,
    )

    # Register work routes (stub for now)
    register_work_routes(
        app_obj,
        state_root=state_root,
        repo_state_root=repo_state_root,
        repo_root=project_paths.repo_root,
        event_broadcaster=event_broadcaster,
        http_exception=http_exception,
    )

    # Register WebSocket routes
    def _validate_spawn_id_wrapper(raw: str) -> SpawnId:
        return validate_spawn_id(raw, http_exception)

    register_ws_routes(
        app_obj,
        spawn_manager,
        validate_spawn_id=_validate_spawn_id_wrapper,
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


__all__ = [
    "InjectRequest",
    "PermissionRequest",
    "SpawnCreateRequest",
    "create_app",
]
