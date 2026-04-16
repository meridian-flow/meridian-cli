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
from pydantic import BaseModel, ConfigDict

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.domain import Spawn, SpawnStatus
from meridian.lib.core.sink import OutputSink
from meridian.lib.core.types import HarnessId, ModelId, SpawnId
from meridian.lib.launch.cwd import resolve_child_execution_cwd
from meridian.lib.launch.fork import materialize_fork
from meridian.lib.launch.request import (
    ExecutionBudget,
    LaunchRuntime,
    RetryPolicy,
    SessionRequest,
    SpawnRequest,
)
from meridian.lib.launch.session_scope import session_scope
from meridian.lib.launch.streaming_runner import execute_with_streaming
from meridian.lib.ops.work_attachment import ensure_explicit_work_item
from meridian.lib.safety.permissions import (
    resolve_permission_pipeline,
)
from meridian.lib.state import spawn_store
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.paths import (
    ProjectPaths,
    resolve_project_paths,
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

from ..runtime import OperationRuntime, build_runtime, resolve_chat_id, runtime_context
from .models import SpawnActionOutput, SpawnCreateInput
from .plan import ExecutionPolicy, PreparedSpawnPlan, SessionContinuation
from .query import read_spawn_row

logger = structlog.get_logger(__name__)
_BACKGROUND_SUBMIT_MESSAGE = "Background spawn submitted."
_BACKGROUND_STDOUT_FILENAME = "background-launcher.stdout.log"
_BACKGROUND_STDERR_FILENAME = "background-launcher.stderr.log"
_BG_WORKER_REQUEST_FILENAME = "bg-worker-request.json"
_BACKGROUND_RUNTIME_ARTIFACTS = (
    _BACKGROUND_STDOUT_FILENAME,
    _BACKGROUND_STDERR_FILENAME,
    _BG_WORKER_REQUEST_FILENAME,
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


class BackgroundWorkerLaunchRequest(BaseModel):
    """Background worker request payload persisted to disk."""

    model_config = ConfigDict(frozen=True)

    request: SpawnRequest
    runtime: LaunchRuntime


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
    project_paths = resolve_project_paths(repo_root=runtime.repo_root)
    state_root = resolve_state_paths(project_paths.repo_root).root_dir
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
        # I-10: do NOT pre-populate harness_session_id on fork starts.
        # materialize_fork() writes it via update_spawn after the row exists.
        harness_session_id=(
            None if prepared.session.continue_fork else prepared.session.harness_session_id
        ),
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
    project_paths: ProjectPaths,
    spawn_id: SpawnId,
    prepared: PreparedSpawnPlan,
    *,
    desc: str = "",
    work_id: str | None = None,
) -> None:
    """Write resolved execution params to the spawn directory."""
    params_path = resolve_spawn_log_dir(project_paths.repo_root, spawn_id) / "params.json"
    prompt_path = resolve_spawn_log_dir(project_paths.repo_root, spawn_id) / "prompt.md"
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


def _persist_bg_worker_request(log_dir: Path, payload: BackgroundWorkerLaunchRequest) -> None:
    """Write background worker launch request to the spawn log directory."""

    params_path = log_dir / _BG_WORKER_REQUEST_FILENAME
    atomic_write_text(params_path, payload.model_dump_json(indent=2) + "\n")


def _load_bg_worker_request(log_dir: Path) -> BackgroundWorkerLaunchRequest:
    """Load background worker launch request from the spawn log directory."""

    params_path = log_dir / _BG_WORKER_REQUEST_FILENAME
    return BackgroundWorkerLaunchRequest.model_validate_json(
        params_path.read_text(encoding="utf-8")
    )


def _metadata_int(metadata: dict[str, str], key: str) -> int | None:
    raw = (metadata.get(key) or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _resolve_session_continuation(
    *,
    request: SpawnRequest,
    harness_id: HarnessId,
    harness_adapter: Any,
) -> SessionContinuation:
    requested_harness_session_id = (
        (request.session.requested_harness_session_id or "").strip() or None
    )
    requested_continue_fork = request.session.continue_fork
    requested_harness = (request.session.continue_harness or "").strip()
    if request.session.continue_source_tracked and requested_harness_session_id is None:
        raise ValueError(
            "Source reference has no recorded harness session — cannot continue/fork."
        )

    resolved_continue_harness_session_id: str | None = None
    resolved_continue_fork = False
    if requested_harness_session_id:
        if (
            requested_harness
            and requested_harness != str(harness_id)
        ) or not harness_adapter.capabilities.supports_session_resume:
            resolved_continue_harness_session_id = None
        else:
            resolved_continue_harness_session_id = requested_harness_session_id
            if requested_continue_fork:
                if harness_adapter.capabilities.supports_session_fork:
                    resolved_continue_fork = True
                else:
                    resolved_continue_fork = False

    # I-10: fork materialization is deferred to the calling executor, which
    # calls materialize_fork() via the sole owner in launch/fork.py, after both
    # the spawn row and chat row exist.  resolved_continue_fork=True is preserved
    # here so the executor knows a fork is needed.

    return SessionContinuation(
        harness_session_id=resolved_continue_harness_session_id,
        continue_harness=request.session.continue_harness,
        continue_source_tracked=request.session.continue_source_tracked,
        continue_source_ref=request.session.continue_source_ref,
        continue_chat_id=request.session.continue_chat_id,
        continue_fork=resolved_continue_fork,
        forked_from_chat_id=request.session.forked_from_chat_id,
        source_execution_cwd=request.session.source_execution_cwd,
    )


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
    project_paths: ProjectPaths,
    launch_request: BackgroundWorkerLaunchRequest,
    sink: OutputSink | None = None,
    ctx: RuntimeContext | None = None,
) -> int:
    resolved_context = runtime_context(ctx)
    runtime = build_runtime(str(project_paths.repo_root), sink=sink)
    state_root = resolve_state_paths(project_paths.repo_root).root_dir
    spawn_record = spawn_store.get_spawn(state_root, spawn_id)
    if spawn_record is None:
        logger.error("Spawn not found for background execution.", spawn_id=str(spawn_id))
        return 1
    request = launch_request.request
    runtime_request = launch_request.runtime
    resolved_model = (request.model or spawn_record.model or "").strip()
    resolved_harness_id = (request.harness or spawn_record.harness or "").strip()
    resolved_prompt = (request.prompt or spawn_record.prompt or "").strip()
    if not resolved_prompt or not resolved_model or not resolved_harness_id:
        logger.error(
            "Background spawn request missing required launch fields.",
            spawn_id=str(spawn_id),
            model=resolved_model,
            harness=resolved_harness_id,
        )
        return 1

    permission_config, permission_resolver = resolve_permission_pipeline(
        sandbox=request.sandbox,
        allowed_tools=request.allowed_tools,
        disallowed_tools=request.disallowed_tools,
        approval=request.approval or "default",
    )
    harness_id = HarnessId(resolved_harness_id)
    harness_adapter = runtime.harness_registry.get_subprocess_harness(harness_id)
    resolved_session = _resolve_session_continuation(
        request=request,
        harness_id=harness_id,
        harness_adapter=harness_adapter,
    )
    spawn_status: SpawnStatus = (
        spawn_record.status if spawn_record.status != "unknown" else "queued"
    )
    spawn = Spawn(
        spawn_id=SpawnId(spawn_record.id),
        prompt=resolved_prompt,
        model=ModelId(resolved_model),
        status=spawn_status,
    )

    autocompact = _metadata_int(request.agent_metadata, "autocompact_pct")
    resolved_agent_name = request.agent if request.agent is not None else spawn_record.agent
    resolved_agent_path = spawn_record.agent_path or request.agent_metadata.get(
        "session_agent_path", ""
    )
    resolved_skills = request.skills or spawn_record.skills
    resolved_skill_paths = spawn_record.skill_paths
    resolved_execution_cwd = (
        (runtime_request.project_paths_execution_cwd or "").strip() or None
    )
    if not resolved_execution_cwd:
        resolved_execution_cwd = str(
            resolve_child_execution_cwd(
                repo_root=project_paths.repo_root,
                spawn_id=str(spawn_id),
                harness_id=resolved_harness_id,
            )
        )

    plan = PreparedSpawnPlan(
        model=resolved_model,
        harness_id=resolved_harness_id,
        effort=request.effort,
        prompt=spawn.prompt,
        agent_name=resolved_agent_name,
        skills=resolved_skills,
        skill_paths=resolved_skill_paths,
        agent_path=resolved_agent_path,
        reference_files=request.reference_files,
        template_vars=request.template_vars,
        context_from_resolved=(request.context_from,) if request.context_from else (),
        mcp_tools=request.mcp_tools,
        session_agent=spawn_record.agent or request.agent_metadata.get("session_agent", ""),
        session_agent_path=resolved_agent_path,
        adhoc_agent_payload=request.agent_metadata.get("adhoc_agent_payload", ""),
        appended_system_prompt=request.agent_metadata.get("appended_system_prompt") or None,
        autocompact=autocompact,
        warning=request.agent_metadata.get("warning") or None,
        session=resolved_session,
        execution=ExecutionPolicy(
            timeout_secs=(
                float(request.budget.timeout_secs)
                if request.budget.timeout_secs is not None
                else None
            ),
            kill_grace_secs=float(request.budget.kill_grace_secs),
            max_retries=max(request.retry.max_attempts - 1, 0),
            retry_backoff_secs=request.retry.backoff_secs,
            permission_config=permission_config,
            permission_resolver=permission_resolver,
            allowed_tools=request.allowed_tools,
            disallowed_tools=request.disallowed_tools,
        ),
        cli_command=(),
        passthrough_args=request.extra_args,
        request=request,
    )

    with _session_execution_context(
        state_root=state_root,
        harness_id=resolved_harness_id,
        harness_session_id=(
            resolved_session.harness_session_id or spawn_record.harness_session_id or ""
        ),
        model=resolved_model,
        session_agent=spawn_record.agent or request.agent_metadata.get("session_agent", ""),
        session_agent_path=resolved_agent_path,
        skills=resolved_skills,
        session_skill_paths=resolved_skill_paths,
        run_agent_name=resolved_agent_name,
        inherited_work_id=spawn_record.work_id,
        forked_from_chat_id=resolved_session.forked_from_chat_id,
        execution_cwd=resolved_execution_cwd,
    ) as session_context:
        resolved_plan = plan.model_copy(update={"agent_name": session_context.resolved_agent_name})
        # I-10/I-11: spawn row AND chat row now both exist.  Materialize any
        # pending fork via the sole owner so the spawn row receives the forked
        # session ID via update_spawn (not pre-populated on the start row).
        if resolved_session.continue_fork and resolved_session.harness_session_id:
            forked_session_id = materialize_fork(
                adapter=harness_adapter,
                source_session_id=resolved_session.harness_session_id,
                state_root=state_root,
                spawn_id=spawn.spawn_id,
            )
            resolved_plan = resolved_plan.model_copy(
                update={
                    "session": resolved_plan.session.model_copy(
                        update={
                            "harness_session_id": forked_session_id,
                            "continue_fork": False,
                        }
                    )
                }
            )
        run_env_overrides = _spawn_child_env(
            str(spawn.spawn_id),
            work_id=session_context.work_id or spawn_record.work_id,
            state_root=state_root,
            autocompact=plan.autocompact,
            ctx=resolved_context,
        )
        runtime_work_id = session_context.work_id or spawn_record.work_id
        resolved_request = _spawn_request_from_prepared(
            prepared=resolved_plan,
            work_id_hint=runtime_work_id,
        )
        launch_runtime = runtime_request.model_copy(
            update={
                "launch_mode": BACKGROUND_LAUNCH_MODE,
                "state_root": state_root.as_posix(),
                "project_paths_repo_root": project_paths.repo_root.as_posix(),
                "project_paths_execution_cwd": resolved_execution_cwd,
            }
        )
        return await execute_with_streaming(
            spawn,
            plan=resolved_plan,
            request=resolved_request,
            launch_runtime=launch_runtime,
            repo_root=project_paths.repo_root,
            state_root=state_root,
            artifacts=runtime.artifacts,
            registry=runtime.harness_registry,
            cwd=Path(resolved_execution_cwd),
            env_overrides=run_env_overrides,
            runtime_work_id=runtime_work_id,
            harness_session_id_observer=session_context.harness_session_id_observer,
            debug=runtime_request.debug,
        )


def _build_background_worker_command(
    *,
    spawn_id: str,
    project_paths: ProjectPaths,
) -> tuple[str, ...]:
    return (
        sys.executable,
        "-m",
        "meridian.lib.ops.spawn.execute",
        "--spawn-id",
        spawn_id,
        "--repo-root",
        project_paths.repo_root.as_posix(),
    )


def _spawn_request_from_prepared(
    *,
    prepared: PreparedSpawnPlan,
    work_id_hint: str | None,
) -> SpawnRequest:
    metadata: dict[str, str] = {}
    if prepared.session_agent:
        metadata["session_agent"] = prepared.session_agent
    if prepared.session_agent_path:
        metadata["session_agent_path"] = prepared.session_agent_path
    if prepared.adhoc_agent_payload:
        metadata["adhoc_agent_payload"] = prepared.adhoc_agent_payload
    if prepared.appended_system_prompt:
        metadata["appended_system_prompt"] = prepared.appended_system_prompt
    if prepared.warning:
        metadata["warning"] = prepared.warning
    if prepared.autocompact is not None:
        metadata["autocompact_pct"] = str(prepared.autocompact)

    timeout_secs = (
        int(prepared.execution.timeout_secs)
        if prepared.execution.timeout_secs is not None
        else None
    )
    kill_grace_secs = int(prepared.execution.kill_grace_secs)

    return SpawnRequest(
        prompt=prepared.prompt,
        model=prepared.model,
        harness=prepared.harness_id,
        agent=prepared.agent_name,
        skills=prepared.skills,
        extra_args=prepared.passthrough_args,
        mcp_tools=prepared.mcp_tools,
        sandbox=prepared.execution.permission_config.sandbox,
        approval=prepared.execution.permission_config.approval,
        allowed_tools=prepared.execution.allowed_tools,
        disallowed_tools=prepared.execution.disallowed_tools,
        autocompact=prepared.autocompact is not None,
        effort=prepared.effort,
        retry=RetryPolicy(
            max_attempts=max(prepared.execution.max_retries + 1, 1),
            backoff_secs=prepared.execution.retry_backoff_secs,
        ),
        budget=ExecutionBudget(
            timeout_secs=timeout_secs,
            kill_grace_secs=kill_grace_secs,
        ),
        session=SessionRequest(
            continue_chat_id=prepared.session.continue_chat_id,
            requested_harness_session_id=prepared.session.harness_session_id,
            continue_fork=prepared.session.continue_fork,
            source_execution_cwd=prepared.session.source_execution_cwd,
            forked_from_chat_id=prepared.session.forked_from_chat_id,
            continue_harness=prepared.session.continue_harness,
            continue_source_tracked=prepared.session.continue_source_tracked,
            continue_source_ref=prepared.session.continue_source_ref,
        ),
        context_from=(
            prepared.context_from_resolved[0] if len(prepared.context_from_resolved) == 1 else None
        ),
        reference_files=prepared.reference_files,
        template_vars=prepared.template_vars,
        work_id_hint=work_id_hint,
        agent_metadata=metadata,
    )


def execute_spawn_background(
    *,
    payload: SpawnCreateInput,
    prepared: PreparedSpawnPlan,
    runtime: OperationRuntime,
    ctx: RuntimeContext | None = None,
) -> SpawnActionOutput:
    resolved_context = runtime_context(ctx)
    project_paths = resolve_project_paths(repo_root=runtime.repo_root)
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
        execution_cwd=str(project_paths.execution_cwd),
        ctx=resolved_context,
    )
    spawn_id_text = str(context.spawn.spawn_id)
    execution_cwd_str = str(
        resolve_child_execution_cwd(
            repo_root=project_paths.repo_root,
            spawn_id=spawn_id_text,
            harness_id=prepared.harness_id,
        )
    )
    # Record pre-computed execution_cwd immediately so it's correct even if
    # the background worker dies before runner.py's authoritative update.
    if execution_cwd_str != str(project_paths.repo_root):
        spawn_store.update_spawn(
            context.state_root,
            context.spawn.spawn_id,
            execution_cwd=execution_cwd_str,
        )
    log_dir = resolve_spawn_log_dir(project_paths.repo_root, context.spawn.spawn_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        _write_params_json(
            project_paths,
            context.spawn.spawn_id,
            prepared,
            desc=payload.desc,
            work_id=context.work_id,
        )
    except Exception:
        logger.warning("Failed to write params.json", spawn_id=spawn_id_text, exc_info=True)

    try:
        persisted_request = prepared.request or _spawn_request_from_prepared(
            prepared=prepared,
            work_id_hint=context.work_id,
        )
        launch_runtime = LaunchRuntime(
            launch_mode=BACKGROUND_LAUNCH_MODE,
            debug=payload.debug,
            state_root=context.state_root.as_posix(),
            project_paths_repo_root=project_paths.repo_root.as_posix(),
            project_paths_execution_cwd=execution_cwd_str,
        )
        _persist_bg_worker_request(
            log_dir,
            BackgroundWorkerLaunchRequest(
                request=persisted_request,
                runtime=launch_runtime,
            ),
        )
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
        project_paths=project_paths,
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
                cwd=project_paths.execution_cwd,
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
    project_paths = resolve_project_paths(repo_root=runtime.repo_root)
    context = _init_spawn(
        payload=payload,
        prepared=prepared,
        runtime=runtime,
        desc=payload.desc,
        work_id=payload.work,
        status="queued",
        launch_mode=FOREGROUND_LAUNCH_MODE,
        runner_pid=os.getpid(),
        execution_cwd=str(project_paths.execution_cwd),
        ctx=resolved_context,
    )
    spawn = context.spawn
    execution_cwd_str = str(
        resolve_child_execution_cwd(
            repo_root=project_paths.repo_root,
            spawn_id=str(spawn.spawn_id),
            harness_id=prepared.harness_id,
        )
    )
    if execution_cwd_str != str(project_paths.repo_root):
        # Pre-compute execution CWD for immediate visibility.
        # runner.py writes the authoritative value right before execution.
        spawn_store.update_spawn(
            context.state_root,
            spawn.spawn_id,
            execution_cwd=execution_cwd_str,
        )
    try:
        _write_params_json(
            project_paths,
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
        # I-10/I-11: spawn row AND chat row now both exist.  Materialize any
        # pending fork via the sole owner so the spawn row receives the forked
        # session ID via update_spawn (not pre-populated on the start row).
        if prepared.session.continue_fork and prepared.session.harness_session_id:
            harness_adapter = runtime.harness_registry.get_subprocess_harness(
                HarnessId(prepared.harness_id)
            )
            forked_session_id = materialize_fork(
                adapter=harness_adapter,
                source_session_id=prepared.session.harness_session_id,
                state_root=context.state_root,
                spawn_id=spawn.spawn_id,
            )
            resolved_plan = resolved_plan.model_copy(
                update={
                    "session": resolved_plan.session.model_copy(
                        update={
                            "harness_session_id": forked_session_id,
                            "continue_fork": False,
                        }
                    )
                }
            )
        run_env_overrides = _spawn_child_env(
            str(spawn.spawn_id),
            work_id=session_context.work_id or context.work_id,
            state_root=context.state_root,
            autocompact=prepared.autocompact,
            ctx=resolved_context,
        )
        runtime_work_id = session_context.work_id or context.work_id
        launch_request = _spawn_request_from_prepared(
            prepared=resolved_plan,
            work_id_hint=runtime_work_id,
        )
        launch_runtime = LaunchRuntime(
            launch_mode=FOREGROUND_LAUNCH_MODE,
            debug=payload.debug,
            harness_command_override=os.getenv("MERIDIAN_HARNESS_COMMAND", "").strip() or None,
            state_root=context.state_root.as_posix(),
            project_paths_repo_root=project_paths.repo_root.as_posix(),
            project_paths_execution_cwd=project_paths.execution_cwd.as_posix(),
        )
        exit_code = asyncio.run(
            execute_with_streaming(
                spawn,
                plan=resolved_plan,
                request=launch_request,
                launch_runtime=launch_runtime,
                repo_root=project_paths.repo_root,
                state_root=context.state_root,
                artifacts=runtime.artifacts,
                registry=runtime.harness_registry,
                cwd=project_paths.execution_cwd,
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
    row = read_spawn_row(project_paths.repo_root, str(spawn.spawn_id))
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
    project_paths = resolve_project_paths(repo_root=repo_root)
    spawn_id = SpawnId(parsed.spawn_id)
    state_root = resolve_state_paths(project_paths.repo_root).root_dir
    log_dir = resolve_spawn_log_dir(project_paths.repo_root, spawn_id)
    try:
        try:
            launch_request = _load_bg_worker_request(log_dir)
        except Exception as exc:
            error = f"Failed to load background worker request: {exc}"
            spawn_store.finalize_spawn(
                state_root,
                spawn_id,
                status="failed",
                exit_code=1,
                origin="launch_failure",
                error=error,
            )
            logger.error(
                "Failed to load background worker request.",
                spawn_id=str(spawn_id),
                log_dir=log_dir.as_posix(),
                exc_info=True,
            )
            return 1

        return asyncio.run(
            _execute_existing_spawn(
                spawn_id=spawn_id,
                project_paths=project_paths,
                launch_request=launch_request,
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
