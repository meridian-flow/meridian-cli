"""FastAPI application factory for Meridian app endpoints."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from importlib import import_module
from pathlib import Path
from typing import Protocol, cast

from pydantic import BaseModel

from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.state import spawn_store
from meridian.lib.streaming.spawn_manager import SpawnManager

_SPAWN_ID_RE = re.compile(r"^p\d+$")


class _AppState(Protocol):
    """App state payload carrying shared runtime singletons."""

    spawn_manager: SpawnManager


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    state: _AppState

    def add_middleware(self, middleware_class: type[object], **kwargs: object) -> None: ...
    def post(self, path: str) -> Callable[[Callable[..., object]], object]: ...
    def get(self, path: str) -> Callable[[Callable[..., object]], object]: ...
    def delete(self, path: str) -> Callable[[Callable[..., object]], object]: ...
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


class SpawnCreateRequest(BaseModel):
    """REST payload for creating one spawn."""

    harness: str
    prompt: str
    model: str | None = None
    agent: str | None = None


class InjectRequest(BaseModel):
    """REST payload for injecting one user message."""

    text: str


def _spawn_index_from_id(spawn_id: SpawnId) -> int:
    raw = str(spawn_id)
    if raw.startswith("p") and raw[1:].isdigit():
        return max(1, int(raw[1:]))
    return 1


def create_app(spawn_manager: SpawnManager) -> object:
    """Create the FastAPI application for Meridian app."""

    @asynccontextmanager
    async def lifespan(_: object) -> AsyncIterator[None]:
        # SpawnManager lifecycle is owned by caller for startup.
        yield
        await spawn_manager.shutdown()

    try:
        fastapi_module = import_module("fastapi")
        cors_module = import_module("fastapi.middleware.cors")
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

    app.add_middleware(
        cors.CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.spawn_manager = spawn_manager

    state_root = spawn_manager.state_root
    repo_root = spawn_manager.repo_root
    next_spawn_index = _spawn_index_from_id(spawn_store.next_spawn_id(state_root))
    spawn_id_lock = asyncio.Lock()

    async def reserve_spawn_id() -> SpawnId:
        nonlocal next_spawn_index
        async with spawn_id_lock:
            spawn_id = SpawnId(f"p{next_spawn_index}")
            next_spawn_index += 1
            return spawn_id

    def _validate_spawn_id(raw: str) -> SpawnId:
        if not _SPAWN_ID_RE.match(raw):
            raise http_exception_cls(status_code=400, detail=f"invalid spawn ID: {raw}")
        return SpawnId(raw)

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

        spawn_id = await reserve_spawn_id()
        config = ConnectionConfig(
            spawn_id=spawn_id,
            harness_id=harness_id,
            model=(body.model.strip() or None) if body.model is not None else None,
            agent=(body.agent.strip() or None) if body.agent is not None else None,
            prompt=prompt,
            repo_root=repo_root,
            env_overrides={},
        )

        try:
            connection = await spawn_manager.start_spawn(config)
        except Exception as exc:
            raise http_exception_cls(
                status_code=400,
                detail=str(exc),
            ) from exc

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

    async def inject_message(spawn_id: str, body: InjectRequest) -> dict[str, bool]:
        typed_spawn_id = _validate_spawn_id(spawn_id)
        text = body.text.strip()
        if not text:
            raise http_exception_cls(
                status_code=400,
                detail="text is required",
            )

        result = await spawn_manager.inject(typed_spawn_id, text, source="rest")
        if not result.success:
            raise http_exception_cls(
                status_code=400,
                detail=result.error or "inject failed",
            )
        return {"ok": True}

    async def cancel_spawn(spawn_id: str) -> dict[str, bool]:
        typed_spawn_id = _validate_spawn_id(spawn_id)
        result = await spawn_manager.cancel(typed_spawn_id, source="rest")
        if not result.success:
            raise http_exception_cls(
                status_code=400,
                detail=result.error or "cancel failed",
            )
        return {"ok": True}

    app.post("/api/spawns")(create_spawn)
    app.get("/api/spawns")(list_spawns)
    app.get("/api/spawns/{spawn_id}")(get_spawn)
    app.post("/api/spawns/{spawn_id}/inject")(inject_message)
    app.delete("/api/spawns/{spawn_id}")(cancel_spawn)

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
