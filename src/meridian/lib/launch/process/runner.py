"""Process launch orchestration."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.lifecycle import create_lifecycle_service
from meridian.lib.core.spawn_lifecycle import (
    has_durable_report_completion,
    resolve_execution_terminal_state,
)
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.claude_preflight import ensure_claude_session_accessible
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import LocalStore, make_artifact_key
from meridian.lib.state.atomic import atomic_write_text
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
from .pty_launcher import PtyProcessLauncher, can_use_pty
from .session import (
    build_session_metadata,
    resolve_attached_work_id,
    resolve_primary_session_mode,
)
from .subprocess_launcher import SubprocessProcessLauncher
from .windows_launcher import WindowsConsoleLauncher, can_use_windows_console_launcher

logger = logging.getLogger(__name__)
_PRIMARY_OUTPUT_FILENAME = "output.jsonl"


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


def run_harness_process(
    launch_context: LaunchContext,
    harness_registry: HarnessRegistry,
    *,
    run_primary_process_with_capture_fn: RunPrimaryProcessWithCapture = (
        run_primary_process_with_capture
    ),
    start_session_fn: Callable[..., str] = start_session,
    stop_session_fn: Callable[..., None] = stop_session,
    update_session_harness_id_fn: Callable[..., None] = update_session_harness_id,
    update_session_work_id_fn: Callable[..., None] = update_session_work_id,
    get_session_active_work_id_fn: Callable[[Path, str], str | None] = get_session_active_work_id,
) -> ProcessOutcome:
    """Start session, spawn tracking, launch process, wait for exit."""

    repo_root = launch_context.repo_root
    execution_cwd = launch_context.execution_cwd
    state_root = launch_context.state_root
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
            (preview_request.session.requested_harness_session_id or "").strip()
            or session_scope_harness_session_id
        )
    harness_adapter = preview_context.harness
    harness_id = HarnessId(session_metadata.harness)
    chat_id: str | None = None
    primary_spawn_id: SpawnId | None = None
    primary_started = 0.0
    primary_started_epoch = 0.0
    primary_started_local_iso: str | None = None
    artifacts = LocalStore(root_dir=state_root / "artifacts")
    lifecycle_service = create_lifecycle_service(repo_root, state_root)

    resume_chat_id = (
        preview_request.session.continue_chat_id
        if session_mode == SessionMode.RESUME
        else None
    )
    exit_code = 2
    try:
        with session_scope(
            state_root=state_root,
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
                state_root=state_root,
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
                    and bool(
                        (preview_request.session.requested_harness_session_id or "").strip()
                    )
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
                        state_root=state_root,
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
                log_dir = resolve_spawn_log_dir(repo_root, primary_spawn_id)
                primary_started = time.monotonic()
                primary_started_epoch = time.time()
                primary_started_local_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                runtime_request = spawn_request.model_copy(
                    update={"work_id_hint": attached_work_id}
                )
                runtime = preview_context.runtime.model_copy(
                    update={
                        "composition_surface": LaunchCompositionSurface.PRIMARY,
                        "state_root": state_root.as_posix(),
                        "project_paths_repo_root": repo_root.as_posix(),
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
                appended_system_prompt = getattr(
                    runtime_context.spec,
                    "appended_system_prompt",
                    runtime_context.run_params.appended_system_prompt,
                )
                if isinstance(appended_system_prompt, str) and appended_system_prompt:
                    atomic_write_text(log_dir / "system-prompt.md", appended_system_prompt)
                
                # Write starting-prompt.md with user-turn content (from projection)
                # Phase 3A: Use user_turn_content from projection for Claude primary
                user_turn_content = getattr(
                    runtime_context.spec,
                    "user_turn_content",
                    runtime_context.run_params.user_turn_content,
                )
                starting_prompt = (
                    user_turn_content.strip()
                    if isinstance(user_turn_content, str) and user_turn_content
                    else runtime_context.request.prompt.strip()
                )
                if starting_prompt:
                    atomic_write_text(log_dir / "starting-prompt.md", starting_prompt)
                
                # Write projection-manifest.json for observability (S-4d)
                harness_id_value = (
                    harness_adapter.id.value
                    if hasattr(harness_adapter.id, "value")
                    else str(harness_adapter.id)
                )
                has_system_prompt = bool(appended_system_prompt)
                has_user_turn_content = bool(user_turn_content)
                
                # Phase 3A: Update manifest to reflect proper Claude channel separation
                projection_manifest = {
                    "harness": harness_id_value,
                    "surface": "primary",
                    "channels": {
                        "system_instruction": (
                            "append-system-prompt" if has_system_prompt else "none"
                        ),
                        "user_task_prompt": (
                            "user-turn" if has_user_turn_content else "inline"
                        ),
                        "task_context": (
                            "user-turn" if has_user_turn_content else "inline"
                        ),
                    },
                }
                atomic_write_text(
                    log_dir / "projection-manifest.json",
                    json.dumps(projection_manifest, indent=2),
                )
                command = runtime_context.argv
                resolved_harness_session_id = runtime_context.seed_harness_session_id or ""
                child_env = dict(runtime_context.env)
                if managed.chat_id:
                    child_env["MERIDIAN_CHAT_ID"] = managed.chat_id
                child_cwd = runtime_context.child_cwd
                output_log_path = log_dir / _PRIMARY_OUTPUT_FILENAME

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

                def _record_primary_started(child_pid: int) -> None:
                    lifecycle_service.mark_running(
                        primary_spawn_id,
                        launch_mode=FOREGROUND_LAUNCH_MODE,
                        worker_pid=child_pid,
                    )

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
                if output_log_path.exists():
                    artifacts.put(
                        make_artifact_key(primary_spawn_id, _PRIMARY_OUTPUT_FILENAME),
                        output_log_path.read_bytes(),
                    )
            finally:
                durable_report = False
                terminated_after_completion = False
                if primary_spawn_id is not None:
                    report_path = resolve_spawn_log_dir(repo_root, primary_spawn_id) / "report.md"
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
                            spawn_id=primary_spawn_id,
                            current_session_id=resolved_harness_session_id,
                            repo_root=repo_root,
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
                                state_root,
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
    "run_primary_process_with_capture",
    "select_process_launcher",
]
