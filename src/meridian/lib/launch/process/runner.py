"""Process launch orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.lifecycle import create_lifecycle_service
from meridian.lib.core.spawn_lifecycle import (
    has_durable_report_completion,
    resolve_execution_terminal_state,
)
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.claude_preflight import ensure_claude_session_accessible
from meridian.lib.harness.connections import get_connection_class
from meridian.lib.harness.connections.base import ConnectionConfig, HarnessConnection
from meridian.lib.harness.launch_spec import CodexLaunchSpec, OpenCodeLaunchSpec
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.artifact_io import write_projection_artifacts
from meridian.lib.launch.constants import (
    OUTPUT_FILENAME,
    PRIMARY_META_FILENAME,
    PRIMARY_TUI_LOG_FILENAME,
)
from meridian.lib.launch.launch_types import ResolvedLaunchSpec
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.paths import resolve_spawn_log_dir
from meridian.lib.state.session_store import (
    get_session_active_work_id,
    start_session,
    stop_session,
    update_session_harness_id,
    update_session_work_id,
)
from meridian.lib.state.spawn_store import FOREGROUND_LAUNCH_MODE

from ..context import LaunchContext, build_launch_context
from ..fork import materialize_fork
from ..request import LaunchCompositionSurface
from ..session_scope import session_scope
from ..types import SessionMode
from .ports import ProcessLauncher, ProcessLauncherSelector
from .primary_attach import PrimaryAttachError, PrimaryAttachLauncher, PrimaryAttachOutcome
from .pty_launcher import PtyProcessLauncher, can_use_pty
from .session import (
    build_session_metadata,
    resolve_attached_work_id,
    resolve_primary_session_mode,
)
from .subprocess_launcher import SubprocessProcessLauncher
from .windows_launcher import WindowsConsoleLauncher, can_use_windows_console_launcher

logger = logging.getLogger(__name__)


class ProcessOutcome(BaseModel):
    """Result of running the harness subprocess."""

    model_config = ConfigDict(frozen=True)

    command: tuple[str, ...]
    exit_code: int
    chat_id: str | None
    primary_spawn_id: str | None
    primary_started: float
    primary_started_epoch: float
    primary_started_local_iso: str | None
    resolved_harness_session_id: str


RunPrimaryProcessWithCapture = Callable[
    [tuple[str, ...], Path, dict[str, str], Path | None, Callable[[int], None] | None],
    tuple[int, int | None],
]
RunPrimaryAttach = Callable[
    [
        HarnessId,
        SpawnId,
        Path,
        Path,
        Path,
        dict[str, str],
        ResolvedLaunchSpec,
        ProcessLauncher,
        Callable[[int], None] | None,
    ],
    PrimaryAttachOutcome,
]


def select_process_launcher(output_log_path: Path | None) -> ProcessLauncher:
    """Choose the launch backend for one primary process invocation."""

    if can_use_windows_console_launcher():
        return WindowsConsoleLauncher()
    if can_use_pty(output_log_path=output_log_path):
        return PtyProcessLauncher()
    return SubprocessProcessLauncher()


def run_primary_process_with_capture(
    command: tuple[str, ...],
    cwd: Path,
    env: dict[str, str],
    output_log_path: Path | None,
    on_child_started: Callable[[int], None] | None = None,
    *,
    launcher_selector: ProcessLauncherSelector = select_process_launcher,
) -> tuple[int, int | None]:
    launcher: ProcessLauncher = launcher_selector(output_log_path)

    launched = launcher.launch(
        command=command,
        cwd=cwd,
        env=env,
        output_log_path=output_log_path,
        on_child_started=on_child_started,
    )
    return launched.exit_code, launched.pid


def _build_codex_attach_command(
    session_id: str,
    ws_url: str,
) -> tuple[str, ...]:
    """Build `codex resume {session_id} --remote {ws_url}`."""

    return ("codex", "resume", session_id, "--remote", ws_url)


def _resolve_codex_ws_url(connection: HarnessConnection[Any]) -> str:
    raw_config = getattr(connection, "_config", None)
    if isinstance(raw_config, ConnectionConfig) and raw_config.ws_port > 0:
        return f"ws://{raw_config.ws_bind_host}:{raw_config.ws_port}"
    raise PrimaryAttachError("Codex managed backend did not expose a websocket attach URL")


def _build_opencode_attach_command(
    session_id: str,
    http_url: str,
) -> tuple[str, ...]:
    """Build `opencode attach {http_url} --session {session_id}`."""

    return ("opencode", "attach", http_url, "--session", session_id)


def _reserve_local_port(host: str = "127.0.0.1") -> int:
    """Reserve one ephemeral TCP port and return it."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _resolve_opencode_http_url(connection: HarnessConnection[Any]) -> str:
    raw_base_url = getattr(connection, "_base_url", None)
    if isinstance(raw_base_url, str) and raw_base_url.strip():
        return raw_base_url.strip()
    raise PrimaryAttachError("OpenCode managed backend did not expose an HTTP attach URL")


def _cleanup_managed_primary_sidecars(spawn_dir: Path) -> None:
    """Delete managed sidecars when attach startup falls back to black-box launch."""

    for filename in (PRIMARY_META_FILENAME, OUTPUT_FILENAME):
        with suppress(OSError):
            (spawn_dir / filename).unlink()


async def _run_primary_attach(
    *,
    harness_id: HarnessId,
    spawn_id: SpawnId,
    spawn_dir: Path,
    project_root: Path,
    execution_cwd: Path,
    env: dict[str, str],
    spec: ResolvedLaunchSpec,
    process_launcher: ProcessLauncher,
    on_running: Callable[[int], None] | None = None,
) -> PrimaryAttachOutcome:
    """Launch managed backend + primary TUI attach flow for supported harnesses."""

    _ = project_root
    try:
        connection_factory = cast(
            "Callable[[], HarnessConnection[Any]]",
            get_connection_class(harness_id),
        )
        connection = connection_factory()
        if harness_id == HarnessId.CODEX:
            if not isinstance(spec, CodexLaunchSpec):
                raise PrimaryAttachError(
                    f"Expected CodexLaunchSpec, got {type(spec).__name__}"
                )
            ws_bind_host = "127.0.0.1"
            ws_port = _reserve_local_port(ws_bind_host)
            config = ConnectionConfig(
                spawn_id=spawn_id,
                harness_id=harness_id,
                prompt=spec.prompt,
                project_root=execution_cwd,
                env_overrides=dict(env),
                ws_bind_host=ws_bind_host,
                ws_port=ws_port,
            )
            launcher = PrimaryAttachLauncher(
                spawn_id=spawn_id,
                spawn_dir=spawn_dir,
                connection=connection,
                tui_command_builder=lambda session_id: _build_codex_attach_command(
                    session_id=session_id,
                    ws_url=_resolve_codex_ws_url(connection),
                ),
                process_launcher=process_launcher,
                on_running=on_running,
            )
            return await launcher.run(
                config=config,
                spec=spec,
                cwd=execution_cwd,
                env=env,
            )

        if harness_id == HarnessId.OPENCODE:
            if not isinstance(spec, OpenCodeLaunchSpec):
                raise PrimaryAttachError(
                    f"Expected OpenCodeLaunchSpec, got {type(spec).__name__}"
                )
            config = ConnectionConfig(
                spawn_id=spawn_id,
                harness_id=harness_id,
                prompt=spec.prompt,
                project_root=execution_cwd,
                env_overrides=dict(env),
            )
            launcher = PrimaryAttachLauncher(
                spawn_id=spawn_id,
                spawn_dir=spawn_dir,
                connection=connection,
                tui_command_builder=lambda session_id: _build_opencode_attach_command(
                    session_id=session_id,
                    http_url=_resolve_opencode_http_url(connection),
                ),
                process_launcher=process_launcher,
                on_running=on_running,
            )
            return await launcher.run(
                config=config,
                spec=spec,
                cwd=execution_cwd,
                env=env,
            )

        raise PrimaryAttachError(f"Managed primary attach is not supported for {harness_id.value}")
    except PrimaryAttachError:
        raise
    except Exception as exc:
        raise PrimaryAttachError(f"Managed primary attach failed for {harness_id.value}") from exc


def run_primary_attach(
    harness_id: HarnessId,
    spawn_id: SpawnId,
    spawn_dir: Path,
    project_root: Path,
    execution_cwd: Path,
    env: dict[str, str],
    spec: ResolvedLaunchSpec,
    process_launcher: ProcessLauncher,
    on_running: Callable[[int], None] | None = None,
) -> PrimaryAttachOutcome:
    """Run managed primary attach lifecycle from sync runner code."""

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            _run_primary_attach(
                harness_id=harness_id,
                spawn_id=spawn_id,
                spawn_dir=spawn_dir,
                project_root=project_root,
                execution_cwd=execution_cwd,
                env=env,
                spec=spec,
                process_launcher=process_launcher,
                on_running=on_running,
            )
        )
    raise PrimaryAttachError("Managed primary attach cannot run inside an active event loop")


def run_harness_process(
    launch_context: LaunchContext,
    harness_registry: HarnessRegistry,
    *,
    run_primary_process_with_capture_fn: RunPrimaryProcessWithCapture = (
        run_primary_process_with_capture
    ),
    run_primary_attach_fn: RunPrimaryAttach = run_primary_attach,
    start_session_fn: Callable[..., str] = start_session,
    stop_session_fn: Callable[..., None] = stop_session,
    update_session_harness_id_fn: Callable[..., None] = update_session_harness_id,
    update_session_work_id_fn: Callable[..., None] = update_session_work_id,
    get_session_active_work_id_fn: Callable[[Path, str], str | None] = get_session_active_work_id,
) -> ProcessOutcome:
    """Start session, spawn tracking, launch process, wait for exit."""

    project_root = launch_context.project_root
    execution_cwd = launch_context.execution_cwd
    runtime_root = launch_context.runtime_root
    preview_context = launch_context
    command = preview_context.argv
    spawn_request = preview_context.request
    preview_request = preview_context.resolved_request
    session_mode = resolve_primary_session_mode(preview_context)
    session_metadata = build_session_metadata(preview_request)
    resolved_harness_session_id = preview_context.seed_harness_session_id or ""
    session_scope_harness_session_id = resolved_harness_session_id
    if session_mode == SessionMode.FORK:
        session_scope_harness_session_id = (
            preview_request.session.requested_harness_session_id or ""
        ).strip() or session_scope_harness_session_id
    harness_adapter = preview_context.harness
    harness_id = HarnessId(session_metadata.harness)
    chat_id: str | None = None
    primary_spawn_id: SpawnId | None = None
    primary_started = 0.0
    primary_started_epoch = 0.0
    primary_started_local_iso: str | None = None
    artifacts = LocalStore(root_dir=runtime_root / "artifacts")
    lifecycle_service = create_lifecycle_service(project_root, runtime_root)

    resume_chat_id = (
        preview_request.session.continue_chat_id if session_mode == SessionMode.RESUME else None
    )
    exit_code = 2
    try:
        with session_scope(
            runtime_root=runtime_root,
            harness=session_metadata.harness,
            harness_session_id=session_scope_harness_session_id,
            model=session_metadata.model,
            chat_id=resume_chat_id,
            forked_from_chat_id=preview_request.session.forked_from_chat_id,
            agent=session_metadata.agent,
            agent_path=session_metadata.agent_path,
            skills=session_metadata.skills,
            skill_paths=session_metadata.skill_paths,
            execution_cwd=str(execution_cwd),
            kind="primary",
            _start_session=start_session_fn,
            _stop_session=stop_session_fn,
            _update_session_harness_id=update_session_harness_id_fn,
        ) as managed:
            chat_id = managed.chat_id
            attached_work_id = resolve_attached_work_id(
                runtime_root=runtime_root,
                chat_id=chat_id,
                explicit_work_id=preview_context.work_id,
                resume_chat_id=resume_chat_id,
                get_session_active_work_id_fn=get_session_active_work_id_fn,
                update_session_work_id_fn=update_session_work_id_fn,
            )
            try:
                should_fork = (
                    session_mode == SessionMode.FORK
                    and harness_id == HarnessId.CODEX
                    and bool((preview_request.session.requested_harness_session_id or "").strip())
                )
                primary_spawn_id = SpawnId(
                    lifecycle_service.start(
                        chat_id=chat_id,
                        model=session_metadata.model,
                        agent=session_metadata.agent,
                        agent_path=session_metadata.agent_path or None,
                        skills=session_metadata.skills,
                        skill_paths=session_metadata.skill_paths,
                        harness=session_metadata.harness,
                        kind="primary",
                        prompt=preview_request.prompt,
                        harness_session_id=None if should_fork else resolved_harness_session_id,
                        execution_cwd=str(execution_cwd),
                        launch_mode=FOREGROUND_LAUNCH_MODE,
                        work_id=attached_work_id,
                        runner_pid=os.getpid(),
                        status="queued",
                    )
                )
                if should_fork:
                    source_session_id = (
                        preview_request.session.requested_harness_session_id or ""
                    ).strip()
                    forked_session_id = materialize_fork(
                        adapter=harness_adapter,
                        source_session_id=source_session_id,
                        runtime_root=runtime_root,
                        spawn_id=primary_spawn_id,
                    )
                    spawn_request = spawn_request.model_copy(
                        update={
                            "session": spawn_request.session.model_copy(
                                update={
                                    "requested_harness_session_id": forked_session_id,
                                    "continue_fork": False,
                                }
                            )
                        }
                    )
                    resolved_harness_session_id = forked_session_id
                log_dir = resolve_spawn_log_dir(project_root, primary_spawn_id)
                primary_started = time.monotonic()
                primary_started_epoch = time.time()
                primary_started_local_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                runtime_request = spawn_request.model_copy(
                    update={"work_id_hint": attached_work_id}
                )
                runtime = preview_context.runtime.model_copy(
                    update={
                        "composition_surface": LaunchCompositionSurface.PRIMARY,
                        "runtime_root": runtime_root.as_posix(),
                        "project_paths_project_root": project_root.as_posix(),
                        "project_paths_execution_cwd": execution_cwd.as_posix(),
                        "report_output_path": (log_dir / "report.md").as_posix(),
                    }
                )
                plan_overrides: dict[str, str] = {}
                if runtime_request.autocompact is not None:
                    plan_overrides["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(
                        runtime_request.autocompact
                    )
                runtime_context = build_launch_context(
                    spawn_id=str(primary_spawn_id),
                    request=runtime_request,
                    runtime=runtime,
                    harness_registry=harness_registry,
                    plan_overrides=plan_overrides,
                    runtime_work_id=attached_work_id,
                )
                write_projection_artifacts(
                    log_dir=log_dir,
                    launch_context=runtime_context,
                    surface="primary",
                )
                command = runtime_context.argv
                resolved_harness_session_id = runtime_context.seed_harness_session_id or ""
                child_env = dict(runtime_context.env)
                if managed.chat_id:
                    child_env["MERIDIAN_CHAT_ID"] = managed.chat_id
                child_cwd = runtime_context.child_cwd
                output_log_path = log_dir / PRIMARY_TUI_LOG_FILENAME
                launch_spec = runtime_context.spec

                if (
                    harness_adapter.id == HarnessId.CLAUDE
                    and preview_request.session.source_execution_cwd
                    and resolved_harness_session_id
                ):
                    ensure_claude_session_accessible(
                        source_session_id=resolved_harness_session_id,
                        source_cwd=Path(preview_request.session.source_execution_cwd),
                        child_cwd=child_cwd,
                    )

                use_managed_backend = (
                    harness_id in {HarnessId.CODEX, HarnessId.OPENCODE}
                    and session_mode != SessionMode.FORK
                )

                def _record_primary_started(child_pid: int) -> None:
                    lifecycle_service.mark_running(
                        primary_spawn_id,
                        launch_mode=FOREGROUND_LAUNCH_MODE,
                        worker_pid=child_pid,
                    )

                if use_managed_backend:
                    try:
                        managed_outcome = run_primary_attach_fn(
                            harness_id,
                            primary_spawn_id,
                            log_dir,
                            project_root,
                            child_cwd,
                            child_env,
                            launch_spec,
                            select_process_launcher(None),
                            _record_primary_started,
                        )
                        exit_code = managed_outcome.exit_code
                        managed_session_id = (managed_outcome.session_id or "").strip()
                        if managed_session_id:
                            resolved_harness_session_id = managed_session_id
                            managed.record_harness_session_id(managed_session_id)
                            spawn_store.update_spawn(
                                runtime_root,
                                primary_spawn_id,
                                harness_session_id=managed_session_id,
                            )
                    except PrimaryAttachError as exc:
                        logger.warning(
                            "Managed backend failed, falling back to black-box TUI: %s",
                            exc,
                        )
                        _cleanup_managed_primary_sidecars(log_dir)
                        use_managed_backend = False

                if harness_id == HarnessId.CLAUDE or not use_managed_backend:
                    exit_code, _child_pid = run_primary_process_with_capture_fn(
                        command,
                        child_cwd,
                        child_env,
                        output_log_path,
                        _record_primary_started,
                    )
                with suppress(Exception):
                    lifecycle_service.record_exited(
                        primary_spawn_id,
                        exit_code=exit_code,
                    )
                if not use_managed_backend and output_log_path.exists():
                    artifacts.put(
                        make_artifact_key(primary_spawn_id, PRIMARY_TUI_LOG_FILENAME),
                        output_log_path.read_bytes(),
                    )
            finally:
                durable_report = False
                terminated_after_completion = False
                if primary_spawn_id is not None:
                    report_path = (
                        resolve_spawn_log_dir(project_root, primary_spawn_id) / "report.md"
                    )
                    try:
                        report_text = (
                            report_path.read_text(encoding="utf-8")
                            if report_path.is_file()
                            else None
                        )
                    except OSError:
                        report_text = None
                    durable_report = has_durable_report_completion(report_text)
                    terminated_after_completion = durable_report and exit_code in (143, -15)
                status, exit_code, _failure_reason = resolve_execution_terminal_state(
                    exit_code=exit_code,
                    failure_reason=None,
                    cancelled=False,
                    durable_report_completion=durable_report,
                    terminated_after_completion=terminated_after_completion,
                )
                if primary_spawn_id is not None:
                    duration = (
                        max(0.0, time.monotonic() - primary_started)
                        if primary_started > 0.0
                        else None
                    )
                    lifecycle_service.finalize(
                        primary_spawn_id,
                        status,
                        exit_code,
                        origin="launcher",
                        duration_secs=duration,
                    )
                try:
                    observed_harness_session_id = None
                    if primary_started_epoch > 0.0:
                        observed_harness_session_id = harness_adapter.observe_session_id(
                            artifacts=artifacts,
                            spawn_id=None,
                            current_session_id=resolved_harness_session_id,
                            project_root=project_root,
                            started_at_epoch=primary_started_epoch,
                            started_at_local_iso=primary_started_local_iso,
                        )
                    if (
                        observed_harness_session_id is not None
                        and observed_harness_session_id.strip()
                        and observed_harness_session_id.strip()
                        != resolved_harness_session_id.strip()
                    ):
                        resolved_harness_session_id = observed_harness_session_id.strip()
                        managed.record_harness_session_id(resolved_harness_session_id)
                        if primary_spawn_id is not None:
                            spawn_store.update_spawn(
                                runtime_root,
                                primary_spawn_id,
                                harness_session_id=resolved_harness_session_id,
                            )
                except Exception:
                    logger.debug(
                        "Best-effort harness session persistence failed",
                        exc_info=True,
                    )
    except FileNotFoundError:
        logger.debug("Harness command not found", exc_info=True)
        exit_code = 2

    return ProcessOutcome(
        command=command,
        exit_code=exit_code,
        chat_id=chat_id,
        primary_spawn_id=primary_spawn_id,
        primary_started=primary_started,
        primary_started_epoch=primary_started_epoch,
        primary_started_local_iso=primary_started_local_iso,
        resolved_harness_session_id=resolved_harness_session_id,
    )


__all__ = [
    "ProcessOutcome",
    "run_harness_process",
    "run_primary_attach",
    "run_primary_process_with_capture",
    "select_process_launcher",
]
