"""CLI entry point for the single-spawn browser test chat."""

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import time
import webbrowser
from contextlib import suppress
from typing import Any
from uuid import uuid4

from meridian.lib.config.project_paths import resolve_project_config_paths
from meridian.lib.core.lifecycle import create_lifecycle_service
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.request import LaunchArgvIntent, LaunchRuntime, SpawnRequest
from meridian.lib.ops.runtime import resolve_runtime_root, resolve_runtime_root_and_config
from meridian.lib.state.user_paths import get_or_create_project_uuid
from meridian.lib.streaming.drain_policy import PersistentDrainPolicy
from meridian.lib.streaming.spawn_manager import SpawnManager

logger = logging.getLogger(__name__)

_DEFAULT_PROMPT = (
    "You are running inside Meridian Test Chat. Wait for user messages sent "
    "through the chat UI, then answer those messages directly."
)


def _normalize_harness(raw_harness: str) -> HarnessId:
    normalized = raw_harness.strip().lower()
    try:
        return HarnessId(normalized)
    except ValueError as exc:
        supported = ", ".join(item.value for item in HarnessId)
        raise ValueError(f"unsupported harness '{raw_harness}'. Supported: {supported}") from exc


def _should_open_browser(host: str, no_open_browser: bool, tailscale: bool) -> bool:
    if no_open_browser or tailscale:
        return False
    return host in {"127.0.0.1", "localhost"}


def run_test_chat(
    *,
    harness: str,
    port: int = 7778,
    host: str = "127.0.0.1",
    model: str | None = None,
    system_prompt: str | None = None,
    idle_timeout: int = 3600,
    cors_origins: list[str] | None = None,
    tailscale: bool = False,
    no_open_browser: bool = False,
    debug: bool = False,
) -> None:
    """Start a focused browser chat session for one harness-backed spawn."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)-5s:     %(message)s")

    uvicorn_module = importlib.import_module("uvicorn")

    from meridian.lib.app.server import create_app
    from meridian.lib.app.test_chat_routes import register_test_chat_routes

    harness_id = _normalize_harness(harness)
    normalized_model = model.strip() if model is not None and model.strip() else None
    prompt = (
        system_prompt.strip()
        if system_prompt is not None and system_prompt.strip()
        else _DEFAULT_PROMPT
    )

    project_root, _ = resolve_runtime_root_and_config(None)
    runtime_root = resolve_runtime_root(project_root)
    project_paths = resolve_project_config_paths(project_root=project_root)
    project_uuid = get_or_create_project_uuid(project_root / ".meridian")
    manager = SpawnManager(runtime_root=runtime_root, project_root=project_root, debug=debug)
    lifecycle_service = create_lifecycle_service(project_root, runtime_root)

    # Resolve CORS origins (tailscale auto-detection + explicit origins).
    all_origins = list(cors_origins or [])
    if tailscale:
        from meridian.cli.app_cmd import _detect_tailscale_origins

        ts_origins = _detect_tailscale_origins(port)
        if ts_origins:
            for origin in ts_origins:
                if origin not in all_origins:
                    all_origins.append(origin)
            logger.info("Tailscale origin: %s", ts_origins[0])
        else:
            logger.warning(
                "--tailscale was set but could not detect Tailscale hostname. "
                "Is Tailscale installed and running? (`tailscale status`)"
            )

    session_holder: dict[str, object] | None = None
    active_spawn_id: SpawnId | None = None
    finalize_task: asyncio.Task[None] | None = None
    idle_task: asyncio.Task[None] | None = None
    last_user_message_at = time.monotonic()
    server: Any | None = None
    browser_url = f"http://{host}:{port}/"

    def mark_user_message() -> None:
        nonlocal last_user_message_at
        last_user_message_at = time.monotonic()

    async def finalize_spawn_when_done(spawn_id: SpawnId) -> None:
        outcome = await manager.wait_for_completion(spawn_id)
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

    async def idle_watch(spawn_id: SpawnId) -> None:
        if idle_timeout <= 0:
            return

        while True:
            remaining = idle_timeout - (time.monotonic() - last_user_message_at)
            if remaining > 0:
                await asyncio.sleep(min(remaining, 5.0))
                continue

            await manager.stop_spawn(
                spawn_id,
                status="cancelled",
                exit_code=124,
                error="idle timeout",
            )
            if server is not None:
                server.should_exit = True
            return

    async def startup_hook(_app: object) -> None:
        nonlocal active_spawn_id, finalize_task, idle_task, session_holder

        chat_id = str(uuid4())
        spawn_id = SpawnId(
            lifecycle_service.start(
                chat_id=chat_id,
                model=normalized_model or "unknown",
                agent="test-chat",
                harness=harness_id.value,
                kind="streaming",
                prompt=prompt,
                launch_mode="app",
                runner_pid=os.getpid(),
                status="running",
                execution_cwd=project_paths.execution_cwd.as_posix(),
            )
        )
        active_spawn_id = spawn_id

        config = ConnectionConfig(
            spawn_id=spawn_id,
            harness_id=harness_id,
            prompt=prompt,
            project_root=project_paths.execution_cwd,
            env_overrides={},
        )
        spawn_req = SpawnRequest(
            prompt=prompt,
            model=normalized_model,
            harness=harness_id.value,
            agent="test-chat",
        )
        launch_runtime = LaunchRuntime(
            argv_intent=LaunchArgvIntent.SPEC_ONLY,
            runtime_root=runtime_root.as_posix(),
            project_paths_project_root=project_paths.project_root.as_posix(),
            project_paths_execution_cwd=project_paths.execution_cwd.as_posix(),
        )
        launch_ctx = build_launch_context(
            spawn_id=str(spawn_id),
            request=spawn_req,
            runtime=launch_runtime,
            harness_registry=get_default_harness_registry(),
        )

        try:
            await manager.start_spawn(
                config,
                launch_ctx.spec,
                drain_policy=PersistentDrainPolicy(),
            )
            await manager._start_heartbeat(spawn_id)  # pyright: ignore[reportPrivateUsage]
        except Exception as exc:
            lifecycle_service.finalize(
                str(spawn_id),
                "failed",
                1,
                origin="launch_failure",
                error=str(exc),
            )
            raise

        session_holder = {
            "spawn_id": str(spawn_id),
            "harness": harness_id.value,
            "model": normalized_model or "unknown",
            "chat_id": chat_id,
            "session_log_path": str(runtime_root / "spawns" / str(spawn_id) / "output.jsonl"),
            "capabilities_url": f"/api/spawns/{spawn_id}/ws",
        }
        finalize_task = asyncio.create_task(finalize_spawn_when_done(spawn_id))
        idle_task = asyncio.create_task(idle_watch(spawn_id))

        if _should_open_browser(host, no_open_browser, tailscale):
            loop = asyncio.get_running_loop()
            loop.call_soon(webbrowser.open, browser_url)

    async def shutdown_hook(_app: object) -> None:
        if idle_task is not None and not idle_task.done():
            idle_task.cancel()
            with suppress(asyncio.CancelledError):
                await idle_task
        if active_spawn_id is not None:
            await manager.stop_spawn(
                active_spawn_id,
                status="cancelled",
                exit_code=130,
                error="shutdown",
            )
        if finalize_task is not None:
            await asyncio.gather(finalize_task, return_exceptions=True)

    app = create_app(
        manager,
        project_uuid=project_uuid,
        runtime_root=runtime_root,
        transport="tcp",
        host=host,
        port=port,
        cors_origins=all_origins,
        startup_hook=startup_hook,
        shutdown_hook=shutdown_hook,
        on_user_message=mark_user_message,
        pre_static_routes=lambda app: register_test_chat_routes(
            app, session_getter=lambda: session_holder
        ),
    )

    print(f"Starting meridian test chat at {browser_url}")
    config = uvicorn_module.Config(app, host=host, port=port, log_level="info")
    resolved_server = uvicorn_module.Server(config)
    server = resolved_server
    try:
        resolved_server.run()
    finally:
        if active_spawn_id is not None:
            logger.debug("test chat stopped", extra={"spawn_id": str(active_spawn_id)})


__all__ = ["run_test_chat"]
