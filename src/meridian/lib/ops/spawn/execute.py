"""Spawn execution helpers shared by sync and async spawn handlers."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, cast

import structlog
from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.domain import Spawn, SpawnStatus
from meridian.lib.core.sink import OutputSink
from meridian.lib.core.types import ModelId, SpawnId
from meridian.lib.launch.cwd import resolve_child_execution_cwd
from meridian.lib.launch.launch_types import PermissionResolver
from meridian.lib.launch.session_scope import session_scope
from meridian.lib.launch.streaming_runner import execute_with_streaming
from meridian.lib.ops.work_attachment import ensure_explicit_work_item
from meridian.lib.safety.permissions import (
    PermissionConfig,
    resolve_permission_pipeline,
)
from meridian.lib.state import spawn_store
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.paths import (
    resolve_spawn_log_dir,
    resolve_state_paths,
    resolve_work_scratch_dir,
)
from meridian.lib.state.session_store import get_session_active_work_id, update_session_work_id
from meridian.lib.state.spawn_store import (
    BACKGROUND_LAUNCH_MODE,
    FOREGROUND_LAUNCH_MODE,
    LaunchMode,
    mark_spawn_running,
)
from meridian.lib.utils.time import minutes_to_seconds

from ..runtime import OperationRuntime, build_runtime, resolve_chat_id, runtime_context
from .models import SpawnActionOutput, SpawnCreateInput
from .plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation
from .query import read_spawn_row

logger = structlog.get_logger(__name__)
_BACKGROUND_SUBMIT_MESSAGE = "Background spawn submitted."
_BACKGROUND_STDOUT_FILENAME = "background-launcher.stdout.log"
_BACKGROUND_STDERR_FILENAME = "background-launcher.stderr.log"
_BG_WORKER_PARAMS_FILENAME = "bg-worker-params.json"
_BACKGROUND_RUNTIME_ARTIFACTS = (
    _BACKGROUND_STDOUT_FILENAME,
    _BACKGROUND_STDERR_FILENAME,
    _BG_WORKER_PARAMS_FILENAME,
)


class _SpawnContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn: Spawn
    state_root: Path
    current_depth: int
    work_id: str | None = None


class _SessionExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    chat_id: str
    work_id: str | None = None
    resolved_agent_name: str | None
    harness_session_id_observer: Callable[[str], None]


class BackgroundWorkerParams(BaseModel):
    """Parameters for background worker execution, persisted to disk."""

    model_config = ConfigDict(frozen=True)

    timeout: float | None = None
    skills: tuple[str, ...] = ()
    agent_name: str | None = None
    mcp_tools: tuple[str, ...] = ()
    sandbox: str | None = None
    approval: str = "default"
    allowed_tools: tuple[str, ...] = ()
    passthrough_args: tuple[str, ...] = ()
    session: SessionContinuation = Field(default_factory=SessionContinuation)
    session_agent: str = ""
    session_agent_path: str = ""
    session_skill_paths: tuple[str, ...] = ()
    adhoc_agent_payload: str = ""
    appended_system_prompt: str | None = None
    autocompact: int | None = None
    execution_cwd: str | None = None
    debug: bool = False


def _cleanup_background_runtime_artifacts(log_dir: Path) -> None:
    """Remove non-durable launcher artifacts after terminal completion."""
    for name in _BACKGROUND_RUNTIME_ARTIFACTS:
        target = log_dir / name
        with suppress(FileNotFoundError):
            target.unlink()


def depth_limits(max_depth: int, *, ctx: RuntimeContext | None = None) -> tuple[int, int]:
    current_depth = runtime_context(ctx).depth
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0.")
    return current_depth, max_depth


def _emit_subrun_event(
    payload: dict[str, Any],
    *,
    sink: OutputSink,
    ctx: RuntimeContext | None = None,
) -> None:
    resolved_context = runtime_context(ctx)
    if resolved_context.depth <= 0:
        return
    event_payload = dict(payload)
    event_payload["v"] = 1
    parent_id = str(resolved_context.spawn_id or "")
    event_payload["parent"] = parent_id or None
    event_payload["ts"] = time.time()
    sink.event(event_payload)


def depth_exceeded_output(current_depth: int, max_depth: int) -> SpawnActionOutput:
    return SpawnActionOutput(
        command="spawn.create",
        status="failed",
        message=f"Max agent depth ({max_depth}) reached. Complete this task directly.",
        error="max_depth_exceeded",
        current_depth=current_depth,
        max_depth=max_depth,
    )


def _spawn_child_env(
    spawn_id: str | None = None,
    *,
    work_id: str | None = None,
    state_root: Path | None = None,
    autocompact: int | None = None,
    ctx: RuntimeContext | None = None,
) -> dict[str, str]:
    _ = spawn_id, work_id, state_root, ctx
    child_env: dict[str, str] = {}
    # K5 boundary: RuntimeContext.child_context() in launch/context.py is the sole
    # producer of MERIDIAN_* child overrides. Plan overrides stay non-MERIDIAN.
    if autocompact is not None:
        child_env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(autocompact)
    return child_env


def _spawn_background_worker_env(
    *,
    work_id: str | None = None,
    state_root: Path | None = None,
    autocompact: int | None = None,
) -> dict[str, str]:
    """Build child env overrides for the detached background worker process."""

    child_env: dict[str, str] = {}
    normalized_work_id = (work_id or "").strip()
    if normalized_work_id:
        child_env["MERIDIAN_WORK_ID"] = normalized_work_id
        if state_root is not None:
            child_env["MERIDIAN_WORK_DIR"] = resolve_work_scratch_dir(
                state_root,
                normalized_work_id,
            ).as_posix()
    if autocompact is not None:
        child_env["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] = str(autocompact)
    return child_env


def _resolve_work_id(
    *,
    payload: SpawnCreateInput,
    runtime_context: RuntimeContext,
    work_id: str | None = None,
) -> str | None:
    requested_work_id = (work_id or payload.work).strip()
    if requested_work_id:
        return requested_work_id
    inherited_work_id = (runtime_context.work_id or "").strip()
    return inherited_work_id or None


def _init_spawn(
    *,
    payload: SpawnCreateInput,
    prepared: PreparedSpawnPlan,
    runtime: OperationRuntime,
    desc: str | None = None,
    work_id: str | None = None,
    status: SpawnStatus = "running",
    launch_mode: LaunchMode | None = None,
    runner_pid: int | None = None,
    execution_cwd: str | None = None,
    ctx: RuntimeContext | None = None,
) -> _SpawnContext:
    resolved_context = runtime_context(ctx)
    state_root = resolve_state_paths(runtime.repo_root).root_dir
    resolved_work_id = _resolve_work_id(
        payload=payload,
        runtime_context=resolved_context,
        work_id=work_id,
    )
    if (payload.work or "").strip():
        resolved_work_id = cast("str", resolved_work_id)
        resolved_work_id = ensure_explicit_work_item(state_root, resolved_work_id)
    resolved_desc = (desc if desc is not None else payload.desc).strip() or None
    spawn_id = spawn_store.start_spawn(
        state_root,
        chat_id=resolve_chat_id(ctx=resolved_context, fallback="c0"),
        parent_id=str(resolved_context.spawn_id) if resolved_context.spawn_id else None,
        model=prepared.model,
        agent=prepared.agent_name or "",
        agent_path=prepared.agent_path or None,
        skills=prepared.skills,
        skill_paths=prepared.skill_paths,
        harness=prepared.harness_id,
        kind="child",
        prompt=prepared.prompt,
        desc=resolved_desc,
        work_id=resolved_work_id,
        harness_session_id=prepared.session.harness_session_id,
        execution_cwd=execution_cwd,
        launch_mode=launch_mode,
        runner_pid=runner_pid,
        status=status,
    )
    spawn = Spawn(
        spawn_id=SpawnId(spawn_id),
        prompt=prepared.prompt,
        model=ModelId(prepared.model),
        status=status,
    )
    current_depth = resolved_context.depth
    run_start_event: dict[str, Any] = {
        "t": "meridian.spawn.start",
        "id": str(spawn.spawn_id),
        "model": prepared.model,
        "d": current_depth,
    }
    if prepared.agent_name is not None:
        run_start_event["agent"] = prepared.agent_name
    _emit_subrun_event(run_start_event, sink=runtime.sink, ctx=resolved_context)
    return _SpawnContext(
        spawn=spawn,
        state_root=state_root,
        current_depth=current_depth,
        work_id=resolved_work_id,
    )


def _write_params_json(
    repo_root: Path,
    spawn_id: SpawnId,
    prepared: PreparedSpawnPlan,
    *,
    desc: str = "",
    work_id: str | None = None,
) -> None:
    """Write resolved execution params to the spawn directory."""
    params_path = resolve_spawn_log_dir(repo_root, spawn_id) / "params.json"
    prompt_path = resolve_spawn_log_dir(repo_root, spawn_id) / "prompt.md"
    params_path.parent.mkdir(parents=True, exist_ok=True)
    params_payload = {
        "model": prepared.model,
        "harness": prepared.harness_id,
        "agent": prepared.agent_name,
        "agent_path": prepared.agent_path,
        "adhoc_agent_payload": prepared.adhoc_agent_payload,
        "desc": desc,
        "work_id": work_id,
        "prompt_length": len(prepared.prompt),
        "reference_files": list(prepared.reference_files),
        "template_vars": prepared.template_vars,
        "skills": list(prepared.skills),
        "skill_paths": list(prepared.skill_paths),
        "continue_session": prepared.session.harness_session_id,
        "continue_fork": prepared.session.continue_fork,
        "forked_from_chat_id": prepared.session.forked_from_chat_id,
    }
    atomic_write_text(params_path, json.dumps(params_payload, indent=2) + "\n")
    atomic_write_text(prompt_path, prepared.prompt)


def _persist_bg_worker_params(log_dir: Path, params: BackgroundWorkerParams) -> None:
    """Write background worker params to the spawn log directory."""
    params_path = log_dir / _BG_WORKER_PARAMS_FILENAME
    atomic_write_text(params_path, params.model_dump_json(indent=2) + "\n")


def _load_bg_worker_params(log_dir: Path) -> BackgroundWorkerParams:
    """Load background worker params from the spawn log directory."""
    params_path = log_dir / _BG_WORKER_PARAMS_FILENAME
    return BackgroundWorkerParams.model_validate_json(params_path.read_text(encoding="utf-8"))


@contextmanager
def _session_execution_context(
    *,
    state_root: Path,
    harness_id: str,
    harness_session_id: str,
    model: str,
    session_agent: str,
    session_agent_path: str,
    skills: tuple[str, ...],
    session_skill_paths: tuple[str, ...],
    run_agent_name: str | None,
    inherited_work_id: str | None = None,
    forked_from_chat_id: str | None = None,
    execution_cwd: str | None = None,
) -> Iterator[_SessionExecutionContext]:
    with session_scope(
        state_root=state_root,
        harness=harness_id,
        harness_session_id=harness_session_id,
        model=model,
        agent=session_agent,
        agent_path=session_agent_path,
        skills=skills,
        skill_paths=session_skill_paths,
        forked_from_chat_id=forked_from_chat_id,
        execution_cwd=execution_cwd,
    ) as managed:
        attached_work_id = get_session_active_work_id(state_root, managed.chat_id)
        if attached_work_id is None:
            attached_work_id = (inherited_work_id or "").strip() or None
            if attached_work_id is not None:
                update_session_work_id(state_root, managed.chat_id, attached_work_id)
        yield _SessionExecutionContext(
            chat_id=managed.chat_id,
            work_id=attached_work_id,
            resolved_agent_name=run_agent_name,
            harness_session_id_observer=managed.record_harness_session_id,
        )


async def _execute_existing_spawn(
    *,
    spawn_id: SpawnId,
    repo_root: Path,
    timeout: float | None,
    skills: tuple[str, ...],
    agent_name: str | None,
    mcp_tools: tuple[str, ...],
    permission_config: PermissionConfig,
    permission_resolver: PermissionResolver,
    allowed_tools: tuple[str, ...] = (),
    passthrough_args: tuple[str, ...] = (),
    session: SessionContinuation | None = None,
    session_agent: str = "",
    session_agent_path: str = "",
    session_skill_paths: tuple[str, ...] = (),
    adhoc_agent_payload: str = "",
    appended_system_prompt: str | None = None,
    autocompact: int | None = None,
    execution_cwd: str | None = None,
    debug: bool = False,
    sink: OutputSink | None = None,
    ctx: RuntimeContext | None = None,
) -> int:
    resolved_context = runtime_context(ctx)
    runtime = build_runtime(str(repo_root), sink=sink)
    state_root = resolve_state_paths(repo_root).root_dir
    spawn_record = spawn_store.get_spawn(state_root, spawn_id)
    if spawn_record is None or spawn_record.model is None or spawn_record.prompt is None:
        logger.error("Spawn not found for background execution.", spawn_id=str(spawn_id))
        return 1
    spawn_status: SpawnStatus = (
        spawn_record.status if spawn_record.status != "unknown" else "queued"
    )
    spawn = Spawn(
        spawn_id=SpawnId(spawn_record.id),
        prompt=spawn_record.prompt,
        model=ModelId(spawn_record.model),
        status=spawn_status,
    )
    resolved_session = session or SessionContinuation()

    plan = PreparedSpawnPlan(
        model=spawn_record.model,
        harness_id=spawn_record.harness or "",
        prompt=spawn.prompt,
        agent_name=agent_name,
        skills=skills,
        skill_paths=session_skill_paths,
        agent_path=session_agent_path,
        reference_files=(),
        template_vars={},
        mcp_tools=mcp_tools,
        session_agent=session_agent,
        session_agent_path=session_agent_path,
        adhoc_agent_payload=adhoc_agent_payload,
        appended_system_prompt=appended_system_prompt,
        autocompact=autocompact,
        session=resolved_session,
        execution=ExecutionPolicy(
            timeout_secs=minutes_to_seconds(timeout),
            kill_grace_secs=minutes_to_seconds(runtime.config.kill_grace_minutes) or 0.0,
            max_retries=runtime.config.max_retries,
            retry_backoff_secs=runtime.config.retry_backoff_seconds,
            permission_config=permission_config,
            permission_resolver=permission_resolver,
            allowed_tools=allowed_tools,
        ),
        cli_command=(),
        passthrough_args=passthrough_args,
    )
    resolved_execution_cwd = execution_cwd
    if not resolved_execution_cwd:
        resolved_execution_cwd = str(
            resolve_child_execution_cwd(
                repo_root=repo_root,
                spawn_id=str(spawn_id),
                harness_id=spawn_record.harness or "",
            )
        )

    with _session_execution_context(
        state_root=state_root,
        harness_id=spawn_record.harness or "",
        harness_session_id=spawn_record.harness_session_id or "",
        model=spawn_record.model,
        session_agent=session_agent,
        session_agent_path=session_agent_path,
        skills=skills,
        session_skill_paths=session_skill_paths,
        run_agent_name=agent_name,
        inherited_work_id=spawn_record.work_id,
        forked_from_chat_id=resolved_session.forked_from_chat_id,
        execution_cwd=resolved_execution_cwd,
    ) as session_context:
        resolved_plan = plan.model_copy(update={"agent_name": session_context.resolved_agent_name})
        run_env_overrides = _spawn_child_env(
            str(spawn.spawn_id),
            work_id=session_context.work_id or spawn_record.work_id,
            state_root=state_root,
            autocompact=plan.autocompact,
            ctx=resolved_context,
        )
        runtime_work_id = session_context.work_id or spawn_record.work_id
        return await execute_with_streaming(
            spawn,
            plan=resolved_plan,
            repo_root=runtime.repo_root,
            state_root=state_root,
            artifacts=runtime.artifacts,
            registry=runtime.harness_registry,
            cwd=runtime.repo_root,
            env_overrides=run_env_overrides,
            runtime_work_id=runtime_work_id,
            harness_session_id_observer=session_context.harness_session_id_observer,
            debug=debug,
        )


def _build_background_worker_command(
    *,
    spawn_id: str,
    repo_root: Path,
) -> tuple[str, ...]:
    return (
        sys.executable,
        "-m",
        "meridian.lib.ops.spawn.execute",
        "--spawn-id",
        spawn_id,
        "--repo-root",
        repo_root.as_posix(),
    )


def execute_spawn_background(
    *,
    payload: SpawnCreateInput,
    prepared: PreparedSpawnPlan,
    runtime: OperationRuntime,
    ctx: RuntimeContext | None = None,
) -> SpawnActionOutput:
    resolved_context = runtime_context(ctx)
    if payload.stream:
        logger.warning("--stream requires --foreground; output goes to spawn log files.")
    context = _init_spawn(
        payload=payload,
        prepared=prepared,
        runtime=runtime,
        desc=payload.desc,
        work_id=payload.work,
        status="queued",
        launch_mode=BACKGROUND_LAUNCH_MODE,
        execution_cwd=str(runtime.repo_root),
        ctx=resolved_context,
    )
    spawn_id_text = str(context.spawn.spawn_id)
    execution_cwd_str = str(
        resolve_child_execution_cwd(
            repo_root=runtime.repo_root,
            spawn_id=spawn_id_text,
            harness_id=prepared.harness_id,
        )
    )
    # Record pre-computed execution_cwd immediately so it's correct even if
    # the background worker dies before runner.py's authoritative update.
    if execution_cwd_str != str(runtime.repo_root):
        spawn_store.update_spawn(
            context.state_root,
            context.spawn.spawn_id,
            execution_cwd=execution_cwd_str,
        )
    log_dir = resolve_spawn_log_dir(runtime.repo_root, context.spawn.spawn_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        _write_params_json(
            runtime.repo_root,
            context.spawn.spawn_id,
            prepared,
            desc=payload.desc,
            work_id=context.work_id,
        )
    except Exception:
        logger.warning("Failed to write params.json", spawn_id=spawn_id_text, exc_info=True)

    try:
        bg_params = BackgroundWorkerParams(
            timeout=payload.timeout,
            skills=prepared.skills,
            agent_name=prepared.agent_name,
            mcp_tools=prepared.mcp_tools,
            sandbox=prepared.execution.permission_config.sandbox,
            approval=prepared.execution.permission_config.approval,
            allowed_tools=prepared.execution.allowed_tools,
            passthrough_args=prepared.passthrough_args,
            session=prepared.session,
            session_agent=prepared.session_agent,
            session_agent_path=prepared.session_agent_path,
            session_skill_paths=prepared.skill_paths,
            adhoc_agent_payload=prepared.adhoc_agent_payload,
            appended_system_prompt=prepared.appended_system_prompt,
            autocompact=prepared.autocompact,
            execution_cwd=execution_cwd_str,
            debug=payload.debug,
        )
        _persist_bg_worker_params(log_dir, bg_params)
    except Exception as exc:
        spawn_store.finalize_spawn(
            context.state_root,
            context.spawn.spawn_id,
            status="failed",
            exit_code=1,
            origin="launch_failure",
            error=str(exc),
        )
        _cleanup_background_runtime_artifacts(log_dir)
        logger.exception(
            "Failed to persist background worker params.",
            spawn_id=spawn_id_text,
        )
        return SpawnActionOutput(
            command="spawn.create",
            status="failed",
            spawn_id=spawn_id_text,
            message=f"Failed to launch background spawn: {exc}",
            error="background_launch_failed",
            model=prepared.model,
            harness_id=prepared.harness_id,
            warning=prepared.warning,
            agent=prepared.agent_name,
            reference_files=prepared.reference_files,
            template_vars=prepared.template_vars,
            context_from_resolved=prepared.context_from_resolved,
            exit_code=1,
        )

    launch_command = _build_background_worker_command(
        spawn_id=spawn_id_text,
        repo_root=runtime.repo_root,
    )
    stdout_path = log_dir / _BACKGROUND_STDOUT_FILENAME
    stderr_path = log_dir / _BACKGROUND_STDERR_FILENAME

    launch_env = dict(os.environ)
    launch_env.update(
        _spawn_background_worker_env(
            work_id=context.work_id,
            state_root=context.state_root,
            autocompact=prepared.autocompact,
        )
    )
    try:
        with (
            stdout_path.open("ab") as stdout_handle,
            stderr_path.open("ab") as stderr_handle,
        ):
            process = subprocess.Popen(
                launch_command,
                cwd=runtime.repo_root,
                env=launch_env,
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
                close_fds=True,
            )
    except OSError as exc:
        spawn_store.finalize_spawn(
            context.state_root,
            context.spawn.spawn_id,
            status="failed",
            exit_code=1,
            origin="launch_failure",
            error=str(exc),
        )
        _cleanup_background_runtime_artifacts(log_dir)
        logger.exception(
            "Failed to launch background spawn worker.",
            spawn_id=spawn_id_text,
            command=list(launch_command),
        )
        return SpawnActionOutput(
            command="spawn.create",
            status="failed",
            spawn_id=spawn_id_text,
            message=f"Failed to launch background spawn: {exc}",
            error="background_launch_failed",
            model=prepared.model,
            harness_id=prepared.harness_id,
            warning=prepared.warning,
            agent=prepared.agent_name,
            reference_files=prepared.reference_files,
            template_vars=prepared.template_vars,
            context_from_resolved=prepared.context_from_resolved,
            exit_code=1,
        )

    mark_spawn_running(
        context.state_root,
        context.spawn.spawn_id,
        launch_mode=BACKGROUND_LAUNCH_MODE,
        runner_pid=process.pid,
    )
    # The Popen object goes out of scope without wait(). This is intentional:
    # the child spawns in its own session (start_new_session=True) and is
    # re-parented to init/systemd. We only need the PID for diagnostics.
    return SpawnActionOutput(
        command="spawn.create",
        status="running",
        spawn_id=spawn_id_text,
        message=_BACKGROUND_SUBMIT_MESSAGE,
        model=prepared.model,
        harness_id=prepared.harness_id,
        warning=prepared.warning,
        agent=prepared.agent_name,
        reference_files=prepared.reference_files,
        template_vars=prepared.template_vars,
        context_from_resolved=prepared.context_from_resolved,
        background=True,
    )


def execute_spawn_blocking(
    *,
    payload: SpawnCreateInput,
    prepared: PreparedSpawnPlan,
    runtime: OperationRuntime,
    ctx: RuntimeContext | None = None,
) -> SpawnActionOutput:
    resolved_context = runtime_context(ctx)
    context = _init_spawn(
        payload=payload,
        prepared=prepared,
        runtime=runtime,
        desc=payload.desc,
        work_id=payload.work,
        status="queued",
        launch_mode=FOREGROUND_LAUNCH_MODE,
        runner_pid=os.getpid(),
        execution_cwd=str(runtime.repo_root),
        ctx=resolved_context,
    )
    spawn = context.spawn
    execution_cwd_str = str(
        resolve_child_execution_cwd(
            repo_root=runtime.repo_root,
            spawn_id=str(spawn.spawn_id),
            harness_id=prepared.harness_id,
        )
    )
    if execution_cwd_str != str(runtime.repo_root):
        # Pre-compute execution CWD for immediate visibility.
        # runner.py writes the authoritative value right before execution.
        spawn_store.update_spawn(
            context.state_root,
            spawn.spawn_id,
            execution_cwd=execution_cwd_str,
        )
    try:
        _write_params_json(
            runtime.repo_root,
            spawn.spawn_id,
            prepared,
            desc=payload.desc,
            work_id=context.work_id,
        )
    except Exception:
        logger.warning("Failed to write params.json", spawn_id=str(spawn.spawn_id), exc_info=True)
    # Emit spawn ID immediately so the caller can reference it while blocking.
    print(json.dumps({"spawn_id": str(spawn.spawn_id), "status": "running"}), flush=True)
    started = time.monotonic()
    stream_stdout_to_terminal = payload.stream
    event_observer = None
    # Spawn execution stays silent unless --stream is explicitly enabled.

    with _session_execution_context(
        state_root=context.state_root,
        harness_id=prepared.harness_id,
        harness_session_id=prepared.session.harness_session_id or "",
        model=prepared.model,
        session_agent=prepared.session_agent,
        session_agent_path=prepared.session_agent_path,
        skills=prepared.skills,
        session_skill_paths=prepared.skill_paths,
        run_agent_name=prepared.agent_name,
        inherited_work_id=context.work_id,
        forked_from_chat_id=prepared.session.forked_from_chat_id,
        execution_cwd=execution_cwd_str,
    ) as session_context:
        resolved_plan = prepared.model_copy(
            update={"agent_name": session_context.resolved_agent_name}
        )
        run_env_overrides = _spawn_child_env(
            str(spawn.spawn_id),
            work_id=session_context.work_id or context.work_id,
            state_root=context.state_root,
            autocompact=prepared.autocompact,
            ctx=resolved_context,
        )
        runtime_work_id = session_context.work_id or context.work_id
        exit_code = asyncio.run(
            execute_with_streaming(
                spawn,
                plan=resolved_plan,
                repo_root=runtime.repo_root,
                state_root=context.state_root,
                artifacts=runtime.artifacts,
                registry=runtime.harness_registry,
                cwd=runtime.repo_root,
                env_overrides=run_env_overrides,
                runtime_work_id=runtime_work_id,
                event_observer=event_observer,
                stream_stdout_to_terminal=stream_stdout_to_terminal,
                stream_stderr_to_terminal=payload.stream,
                harness_session_id_observer=session_context.harness_session_id_observer,
                debug=payload.debug,
            )
        )
    duration = time.monotonic() - started
    row = read_spawn_row(runtime.repo_root, str(spawn.spawn_id))
    # Report is read on-demand via `spawn show`, not inlined here.
    status = "failed"
    if row is not None:
        status = row.status
    done_secs = duration
    tokens_total: int | None = None
    if row is not None:
        row_duration = row.duration_secs
        if row_duration is not None:
            done_secs = row_duration
        input_tokens = row.input_tokens
        output_tokens = row.output_tokens
        if input_tokens is not None and output_tokens is not None:
            tokens_total = input_tokens + output_tokens
    _emit_subrun_event(
        {
            "t": "meridian.spawn.done",
            "id": str(spawn.spawn_id),
            "exit": exit_code,
            "secs": done_secs,
            "tok": tokens_total,
            "d": context.current_depth,
        },
        sink=runtime.sink,
        ctx=resolved_context,
    )

    return SpawnActionOutput(
        command="spawn.create",
        status=status,
        spawn_id=str(spawn.spawn_id),
        message="Spawn completed.",
        model=prepared.model,
        harness_id=prepared.harness_id,
        warning=prepared.warning,
        agent=session_context.resolved_agent_name,
        reference_files=prepared.reference_files,
        template_vars=prepared.template_vars,
        context_from_resolved=prepared.context_from_resolved,
        report=None,
        exit_code=exit_code,
        duration_secs=duration,
    )


def _build_background_worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m meridian.lib.ops.spawn.execute")
    parser.add_argument("--spawn-id", required=True)
    parser.add_argument("--repo-root", required=True)
    return parser


def _background_worker_main(
    argv: Sequence[str] | None = None,
    *,
    ctx: RuntimeContext | None = None,
) -> int:
    resolved_context = runtime_context(ctx)
    parser = _build_background_worker_parser()
    parsed = parser.parse_args(list(argv) if argv is not None else None)

    repo_root = Path(parsed.repo_root).expanduser().resolve()
    spawn_id = SpawnId(parsed.spawn_id)
    state_root = resolve_state_paths(repo_root).root_dir
    log_dir = resolve_spawn_log_dir(repo_root, spawn_id)
    try:
        try:
            params = _load_bg_worker_params(log_dir)
        except Exception as exc:
            error = f"Failed to load background worker params: {exc}"
            spawn_store.finalize_spawn(
                state_root,
                spawn_id,
                status="failed",
                exit_code=1,
                origin="launch_failure",
                error=error,
            )
            logger.error(
                "Failed to load background worker params.",
                spawn_id=str(spawn_id),
                log_dir=log_dir.as_posix(),
                exc_info=True,
            )
            return 1

        permission_config, permission_resolver = resolve_permission_pipeline(
            sandbox=params.sandbox,
            allowed_tools=params.allowed_tools,
            approval=params.approval,
        )
        return asyncio.run(
            _execute_existing_spawn(
                spawn_id=spawn_id,
                repo_root=repo_root,
                timeout=params.timeout,
                skills=params.skills,
                agent_name=params.agent_name,
                mcp_tools=params.mcp_tools,
                permission_config=permission_config,
                permission_resolver=permission_resolver,
                allowed_tools=params.allowed_tools,
                passthrough_args=params.passthrough_args,
                session=params.session,
                session_agent=params.session_agent,
                session_agent_path=params.session_agent_path,
                session_skill_paths=params.session_skill_paths,
                adhoc_agent_payload=params.adhoc_agent_payload,
                appended_system_prompt=params.appended_system_prompt,
                autocompact=params.autocompact,
                execution_cwd=params.execution_cwd,
                debug=params.debug,
                ctx=resolved_context,
            )
        )
    finally:
        _cleanup_background_runtime_artifacts(log_dir)


if __name__ == "__main__":
    raise SystemExit(_background_worker_main())


__all__ = [
    "depth_exceeded_output",
    "depth_limits",
    "execute_spawn_background",
    "execute_spawn_blocking",
]
