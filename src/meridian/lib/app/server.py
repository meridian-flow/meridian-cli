"""FastAPI application factory for Meridian app endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import shutil
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Literal, Protocol, cast

# Re-export for backward compatibility
from meridian.lib.app.spawn_routes import (
    InjectRequest,
    PermissionRequest,
    SpawnCreateRequest,
)
from meridian.lib.config.project_paths import resolve_project_config_paths
from meridian.lib.core.lifecycle import create_lifecycle_service
from meridian.lib.platform import IS_WINDOWS
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.paths import resolve_project_paths
from meridian.lib.streaming.spawn_manager import SpawnManager

logger = logging.getLogger(__name__)


class _AppState(Protocol):
    """App state payload carrying shared runtime singletons."""

    spawn_manager: SpawnManager
    stream_broadcaster: object
    project_uuid: str
    instance_id: str
    instance_token: str | None
    meridian_dir: str | None


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
    def add_route(
        self,
        path: str,
        endpoint: Callable[..., object],
        methods: list[str] | None = None,
    ) -> None: ...
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
    project_uuid: str = "test-project-uuid",
    runtime_root: Path | None = None,
    transport: Literal["tcp", "uds"] = "tcp",
    host: str | None = None,
    port: int | None = None,
    socket_path: str | None = None,
    allow_unsafe_no_permissions: bool = False,
) -> object:
    """Create the FastAPI application for Meridian app."""

    background_finalize_tasks: set[asyncio.Task[None]] = set()
    resolved_runtime_root = runtime_root or spawn_manager.runtime_root

    @asynccontextmanager
    async def lifespan(app_ctx: object) -> AsyncIterator[None]:
        app_ctx_fastapi = cast("_FastAPIApp", app_ctx)
        instance_id = str(uuid.uuid4())
        app_ctx_fastapi.state.instance_id = instance_id
        app_ctx_fastapi.state.project_uuid = project_uuid
        instance_dir = resolved_runtime_root / "app" / str(os.getpid())
        instance_dir.mkdir(parents=True, exist_ok=True)

        token_value = getattr(app_ctx_fastapi.state, "instance_token", None)
        token = (
            token_value
            if isinstance(token_value, str) and token_value
            else secrets.token_hex(32)
        )
        token_file = instance_dir / "token"
        token_fd = os.open(
            str(token_file),
            os.O_CREAT | os.O_WRONLY | os.O_TRUNC,
            0o600,
        )
        try:
            if not IS_WINDOWS:
                os.fchmod(token_fd, 0o600)  # Defense-in-depth for PID reuse.
            os.write(token_fd, token.encode("utf-8"))
            os.fsync(token_fd)
        finally:
            os.close(token_fd)
        app_ctx_fastapi.state.instance_token = token

        endpoint = {
            "schema_version": 1,
            "instance_id": instance_id,
            "transport": transport,
            "socket_path": socket_path if transport == "uds" else None,
            "host": host if transport == "tcp" else None,
            "port": port if transport == "tcp" else None,
            "project_uuid": project_uuid,
            "repo_root": spawn_manager.project_root.as_posix(),
            "pid": os.getpid(),
            "started_at": datetime.now(UTC).isoformat(),
        }
        atomic_write_text(instance_dir / "endpoint.json", json.dumps(endpoint, indent=2))

        # SpawnManager lifecycle is owned by caller for startup.
        try:
            yield
        finally:
            shutil.rmtree(instance_dir, ignore_errors=True)
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
    app.state.project_uuid = project_uuid
    app.state.instance_id = ""
    app.state.instance_token = secrets.token_hex(32)

    async def health_check() -> dict[str, str]:
        return {
            "status": "ok",
            "project_uuid": app.state.project_uuid,
            "instance_id": app.state.instance_id,
        }

    app.get("/api/health")(health_check)

    runtime_root = resolved_runtime_root
    project_paths = resolve_project_config_paths(project_root=spawn_manager.project_root)
    project_state_dir = resolve_project_paths(project_paths.project_root).root_dir
    app.state.meridian_dir = str(project_state_dir)
    lifecycle_service = create_lifecycle_service(project_paths.project_root, runtime_root)
    spawn_id_lock = asyncio.Lock()

    # Import route registration functions
    from meridian.lib.app.extension_routes import (
        make_discovery_routes,
        make_invoke_routes,
    )
    from meridian.lib.app.file_routes import register_file_routes
    from meridian.lib.app.file_service import FileService
    from meridian.lib.app.http_types import HTTPExceptionCallable
    from meridian.lib.app.spawn_routes import (
        register_spawn_query_routes,
        register_spawn_routes,
        validate_spawn_id,
    )
    from meridian.lib.app.stream import SpawnMultiSubscriberManager, register_stream_routes
    from meridian.lib.app.work_routes import register_work_routes
    from meridian.lib.app.ws_endpoint import register_ws_routes
    from meridian.lib.core.types import SpawnId
    from meridian.lib.extensions.context import (
        ExtensionCommandServices,
        ExtensionInvocationContextBuilder,
    )
    from meridian.lib.extensions.dispatcher import ExtensionCommandDispatcher
    from meridian.lib.extensions.registry import build_first_party_registry
    from meridian.lib.extensions.types import ExtensionSurface

    http_exception = cast("HTTPExceptionCallable", http_exception_cls)

    # Register expanded spawn query routes first so static paths win over
    # /api/spawns/{spawn_id} path parameter route.
    register_spawn_query_routes(
        app_obj,
        runtime_root=runtime_root,
        http_exception=http_exception,
    )

    # Register SSE stream routes and capture shared broadcaster.
    event_broadcaster = register_stream_routes(
        app_obj,
        spawn_manager,
        runtime_root=runtime_root,
    )
    multi_sub_manager = SpawnMultiSubscriberManager(spawn_manager)

    # Register spawn routes
    register_spawn_routes(
        app_obj,
        spawn_manager,
        runtime_root=runtime_root,
        project_paths=project_paths,
        lifecycle_service=lifecycle_service,
        spawn_id_lock=spawn_id_lock,
        background_finalize_tasks=background_finalize_tasks,
        event_broadcaster=event_broadcaster,
        allow_unsafe_no_permissions=allow_unsafe_no_permissions,
        http_exception=http_exception,
    )

    # Register work routes
    register_work_routes(
        app_obj,
        runtime_root=runtime_root,
        project_state_dir=project_state_dir,
        project_root=project_paths.project_root,
        event_broadcaster=event_broadcaster,
        http_exception=http_exception,
    )

    # Register file routes
    file_service = FileService(project_paths.project_root)
    register_file_routes(
        app_obj,
        file_service,
        http_exception=http_exception,
    )

    # Register catalog routes (models + agents)
    from meridian.lib.app.catalog_routes import register_catalog_routes

    register_catalog_routes(
        app_obj,
        project_root=project_paths.project_root,
        http_exception=http_exception,
    )

    # Register KB analysis routes
    from meridian.lib.app.kb_routes import register_kb_routes

    register_kb_routes(
        app_obj,
        project_root=project_paths.project_root,
        http_exception=http_exception,
    )

    # Register thread inspector routes
    from meridian.lib.app.thread_routes import register_thread_routes

    register_thread_routes(
        app_obj,
        runtime_root=runtime_root,
        artifact_root=runtime_root / "artifacts",
        http_exception=http_exception,
    )

    # Register WebSocket routes
    def _validate_spawn_id_wrapper(raw: str) -> SpawnId:
        return validate_spawn_id(raw, http_exception)

    register_ws_routes(
        app_obj,
        spawn_manager,
        multi_sub_manager=multi_sub_manager,
        validate_spawn_id=_validate_spawn_id_wrapper,
    )

    # Register extension discovery + invoke routes before static mount.
    ext_registry = build_first_party_registry()
    meridian_dir_value = getattr(app.state, "meridian_dir", None)
    ext_services = ExtensionCommandServices(
        runtime_root=runtime_root,
        meridian_dir=Path(meridian_dir_value) if isinstance(meridian_dir_value, str) else None,
    )
    ext_dispatcher = ExtensionCommandDispatcher(
        ext_registry,
        observability_log=resolved_runtime_root / "extension-invocations.jsonl",
    )

    def make_http_context_builder() -> ExtensionInvocationContextBuilder:
        return ExtensionInvocationContextBuilder(ExtensionSurface.HTTP).with_project_uuid(
            project_uuid
        )

    ext_token = getattr(app.state, "instance_token", None)

    discovery_routes = make_discovery_routes(ext_registry)
    for route in discovery_routes:
        route_methods = sorted(route.methods) if route.methods else None
        app.add_route(route.path, route.endpoint, methods=route_methods)

    if isinstance(ext_token, str) and ext_token:
        invoke_routes = make_invoke_routes(
            dispatcher=ext_dispatcher,
            context_builder_factory=make_http_context_builder,
            services=ext_services,
            token=ext_token,
        )
        for route in invoke_routes:
            route_methods = sorted(route.methods) if route.methods else None
            app.add_route(route.path, route.endpoint, methods=route_methods)

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
