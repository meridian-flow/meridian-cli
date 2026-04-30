"""CLI command for the local headless chat backend."""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, cast

from cyclopts import App, Parameter

from meridian.lib.chat.backend_acquisition import ColdSpawnAcquisition
from meridian.lib.chat.event_pipeline import ChatEventPipeline
from meridian.lib.harness.ids import HarnessId
from meridian.lib.harness.launch_spec import (
    ClaudeLaunchSpec,
    CodexLaunchSpec,
    OpenCodeLaunchSpec,
)
from meridian.lib.harness.normalizers.registry import get_normalizer_factory
from meridian.lib.launch.launch_types import ResolvedLaunchSpec
from meridian.lib.safety.permissions import UnsafeNoOpPermissionResolver
from meridian.lib.state.user_paths import get_user_home
from meridian.lib.streaming.spawn_manager import SpawnManager


def register_chat_command(app: App) -> None:
    """Register the ``meridian chat`` command."""

    app.command(name="chat")(_chat)


def _chat(
    model: Annotated[
        str | None,
        Parameter(name=["--model", "-m"], help="Model id or alias for chat backends."),
    ] = None,
    harness: Annotated[
        str | None,
        Parameter(name="--harness", help="Harness id: claude, codex, or opencode."),
    ] = None,
    port: Annotated[int, Parameter(name="--port", help="Port to bind; 0 auto-assigns.")] = 0,
    host: Annotated[
        str,
        Parameter(name="--host", help="Host/interface to bind."),
    ] = "127.0.0.1",
) -> None:
    """Start the local headless chat backend server."""

    from meridian.cli.main import get_global_options

    effective_harness = harness or get_global_options().harness
    run_chat_server(model=model, harness=effective_harness, port=port, host=host)


def run_chat_server(
    *,
    model: str | None = None,
    harness: str | None = None,
    port: int = 0,
    host: str = "127.0.0.1",
    uvicorn_run: Callable[..., Any] | None = None,
    stdout: Any | None = None,
) -> int:
    """Configure and run the local chat backend; return the bound port."""

    import sys

    import uvicorn

    from meridian.lib.chat.server import app as chat_app
    from meridian.lib.chat.server import configure

    if port < 0 or port > 65535:
        raise ValueError("port must be between 0 and 65535")

    runtime_root = get_user_home()
    project_root = Path.cwd()
    harness_id = _resolve_harness_id(harness)
    acquisition = _build_backend_acquisition(
        runtime_root=runtime_root,
        project_root=project_root,
        harness_id=harness_id,
        model=(model or "").strip() or None,
    )
    configure(
        runtime_root=runtime_root,
        project_root=project_root,
        backend_acquisition=acquisition,
    )

    env_port = int(os.environ.get("PORT", "0") or "0")
    actual_port = port if port != 0 else (env_port or _find_free_port(host))
    output = stdout if stdout is not None else sys.stdout
    print(f"Chat backend: http://{host}:{actual_port}", file=output, flush=True)
    runner = uvicorn_run or uvicorn.run
    runner(chat_app, host=host, port=actual_port)
    return actual_port


def _resolve_harness_id(harness: str | None) -> HarnessId:
    raw = (harness or HarnessId.CLAUDE.value).strip().lower()
    try:
        return HarnessId(raw)
    except ValueError as exc:
        valid = ", ".join(item.value for item in HarnessId)
        raise ValueError(f"unsupported chat harness {raw!r}; expected one of: {valid}") from exc


def _find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _build_backend_acquisition(
    *,
    runtime_root: Path,
    project_root: Path,
    harness_id: HarnessId,
    model: str | None,
) -> ColdSpawnAcquisition:
    manager = SpawnManager(runtime_root=runtime_root, project_root=project_root)

    def pipeline_factory(chat_id: str, _execution_id: str) -> ChatEventPipeline:
        import meridian.lib.chat.server as chat_server

        runtime = vars(chat_server)["_runtime"]
        entry = runtime.live_entries.get(chat_id)
        if entry is None:
            raise RuntimeError(f"chat pipeline not configured for {chat_id}")
        return entry.pipeline

    return ColdSpawnAcquisition(
        spawn_manager=cast("Any", manager),
        normalizer_factory=get_normalizer_factory(harness_id),
        pipeline_factory=pipeline_factory,
        launch_spec_factory=lambda prompt: _launch_spec(
            harness_id=harness_id,
            prompt=prompt,
            model=model,
        ),
        project_root=project_root,
        harness_id=harness_id,
    )


def _launch_spec(*, harness_id: HarnessId, prompt: str, model: str | None) -> ResolvedLaunchSpec:
    permission_resolver = UnsafeNoOpPermissionResolver(_suppress_warning=True)
    if harness_id == HarnessId.CLAUDE:
        return ClaudeLaunchSpec(
            prompt=prompt,
            model=model,
            permission_resolver=permission_resolver,
        )
    if harness_id == HarnessId.CODEX:
        return CodexLaunchSpec(
            prompt=prompt,
            model=model,
            permission_resolver=permission_resolver,
        )
    if harness_id == HarnessId.OPENCODE:
        return OpenCodeLaunchSpec(
            prompt=prompt,
            model=model,
            permission_resolver=permission_resolver,
        )
    return ResolvedLaunchSpec(
        prompt=prompt,
        model=model,
        permission_resolver=permission_resolver,
    )


__all__ = ["register_chat_command", "run_chat_server"]
