"""Spawn execution helpers shared by sync and async spawn handlers."""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import structlog
from pydantic import BaseModel, ConfigDict

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.domain import Spawn, SpawnStatus
from meridian.lib.core.sink import OutputSink
from meridian.lib.core.types import ModelId, SpawnId
from meridian.lib.harness.adapter import PermissionResolver
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.launch.session_scope import session_scope
from meridian.lib.ops.work_attachment import ensure_explicit_work_item
from meridian.lib.safety.permissions import (
    PermissionConfig,
    resolve_permission_pipeline,
)
from meridian.lib.state import spawn_store
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.paths import resolve_spawn_log_dir, resolve_state_paths
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
from .query import read_report_text, read_spawn_row

logger = structlog.get_logger(__name__)
_BACKGROUND_SUBMIT_MESSAGE = "Background spawn submitted."
_BACKGROUND_PID_FILENAME = "background.pid"
_BACKGROUND_STDOUT_FILENAME = "background-launcher.stdout.log"
_BACKGROUND_STDERR_FILENAME = "background-launcher.stderr.log"


def _parse_csv_skills(raw: str) -> tuple[str, ...]:
    trimmed = raw.strip()
    if not trimmed:
        return ()

    parts = [part.strip() for part in trimmed.split(",")]
    if any(not part for part in parts):
        raise ValueError("Invalid value for '--skills': expected comma-separated non-empty names.")
    return tuple(parts)


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


def _optional_spawn_id(spawn_id: str | None) -> SpawnId | None:
    if spawn_id is None:
        return None
    normalized = spawn_id.strip()
    if not normalized:
        return None
    return SpawnId(normalized)


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
    parent_spawn_id = str(resolved_context.spawn_id or "")
    event_payload["parent"] = parent_spawn_id or None
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
    resolved_context = runtime_context(ctx)
    # Preserve Meridian spawn context across nesting without forwarding unrelated
    # parent process environment variables.
    child_env = {key: value for key, value in os.environ.items() if key.startswith("MERIDIAN_")}
    resolved_spawn_id = _optional_spawn_id(spawn_id)
    if resolved_spawn_id is not None:
        child_context = resolved_context.child_context(spawn_id=resolved_spawn_id)
    else:
        child_context = RuntimeContext(
            spawn_id=resolved_spawn_id,
            parent_spawn_id=resolved_context.spawn_id
            if resolved_context.spawn_id is not None
            else None,
            depth=resolved_context.depth + 1,
            repo_root=resolved_context.repo_root,
            state_root=state_root or resolved_context.state_root,
            chat_id=resolved_context.chat_id,
            work_id=resolved_context.work_id,
        )
    resolved_work_id = (work_id or "").strip() or child_context.work_id
    if resolved_work_id != child_context.work_id or (
        state_root is not None and state_root != child_context.state_root
    ):
        child_context = child_context.model_copy(
            update={
                "state_root": state_root if state_root is not None else child_context.state_root,
                "work_id": resolved_work_id,
            }
        )
    child_env.update(child_context.to_env_overrides())
    if resolved_context.spawn_id is None:
        child_env.pop("MERIDIAN_PARENT_SPAWN_ID", None)
    if resolved_spawn_id is None:
        child_env.pop("MERIDIAN_SPAWN_ID", None)
    if not resolved_work_id:
        child_env.pop("MERIDIAN_WORK_ID", None)
        child_env.pop("MERIDIAN_WORK_DIR", None)
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
        model=prepared.model,
        agent=prepared.agent_name or "",
        agent_path=prepared.agent_path or None,
        agent_source=prepared.agent_source,
        skills=prepared.skills,
        skill_paths=prepared.skill_paths,
        skill_sources=prepared.skill_sources,
        bootstrap_required_items=prepared.bootstrap_required_items,
        bootstrap_missing_items=prepared.bootstrap_missing_items,
        harness=prepared.harness_id,
        kind="child",
        prompt=prepared.prompt,
        desc=resolved_desc,
        work_id=resolved_work_id,
        harness_session_id=prepared.session.harness_session_id,
        launch_mode=launch_mode,
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
        "agent_source": prepared.agent_source,
        "adhoc_agent_payload": prepared.adhoc_agent_payload,
        "desc": desc,
        "work_id": work_id,
        "prompt_length": len(prepared.prompt),
        "reference_files": list(prepared.reference_files),
        "template_vars": prepared.template_vars,
        "skills": list(prepared.skills),
        "skill_paths": list(prepared.skill_paths),
        "skill_sources": prepared.skill_sources,
        "bootstrap_required_items": list(prepared.bootstrap_required_items),
        "bootstrap_missing_items": list(prepared.bootstrap_missing_items),
        "continue_session": prepared.session.harness_session_id,
        "continue_fork": prepared.session.continue_fork,
    }
    atomic_write_text(params_path, json.dumps(params_payload, indent=2) + "\n")
    atomic_write_text(prompt_path, prepared.prompt)


@contextmanager
def _session_execution_context(
    *,
    state_root: Path,
    harness_id: str,
    harness_session_id: str,
    model: str,
    session_agent: str,
    session_agent_path: str,
    session_agent_source: str | None,
    skills: tuple[str, ...],
    session_skill_paths: tuple[str, ...],
    skill_sources: dict[str, str],
    bootstrap_required_items: tuple[str, ...],
    bootstrap_missing_items: tuple[str, ...],
    run_agent_name: str | None,
    inherited_work_id: str | None = None,
) -> Iterator[_SessionExecutionContext]:
    with session_scope(
        state_root=state_root,
        harness=harness_id,
        harness_session_id=harness_session_id,
        model=model,
        agent=session_agent,
        agent_path=session_agent_path,
        agent_source=session_agent_source,
        skills=skills,
        skill_paths=session_skill_paths,
        skill_sources=skill_sources,
        bootstrap_required_items=bootstrap_required_items,
        bootstrap_missing_items=bootstrap_missing_items,
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
    continue_harness_session_id: str | None = None,
    continue_fork: bool = False,
    session_agent: str = "",
    session_agent_path: str = "",
    session_skill_paths: tuple[str, ...] = (),
    adhoc_agent_payload: str = "",
    appended_system_prompt: str | None = None,
    autocompact: int | None = None,
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

    plan = PreparedSpawnPlan(
        model=spawn_record.model,
        harness_id=spawn_record.harness or "",
        prompt=spawn.prompt,
        agent_name=agent_name,
        skills=skills,
        skill_paths=session_skill_paths,
        agent_path=session_agent_path,
        agent_source=spawn_record.agent_source,
        skill_sources=spawn_record.skill_sources,
        bootstrap_required_items=spawn_record.bootstrap_required_items,
        bootstrap_missing_items=spawn_record.bootstrap_missing_items,
        reference_files=(),
        template_vars={},
        mcp_tools=mcp_tools,
        session_agent=session_agent,
        session_agent_path=session_agent_path,
        adhoc_agent_payload=adhoc_agent_payload,
        appended_system_prompt=appended_system_prompt,
        autocompact=autocompact,
        session=SessionContinuation(
            harness_session_id=continue_harness_session_id,
            continue_fork=continue_fork,
        ),
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

    with _session_execution_context(
        state_root=state_root,
        harness_id=spawn_record.harness or "",
        harness_session_id=spawn_record.harness_session_id or "",
        model=spawn_record.model,
        session_agent=session_agent,
        session_agent_path=session_agent_path,
        session_agent_source=spawn_record.agent_source,
        skills=skills,
        session_skill_paths=session_skill_paths,
        skill_sources=spawn_record.skill_sources,
        bootstrap_required_items=spawn_record.bootstrap_required_items,
        bootstrap_missing_items=spawn_record.bootstrap_missing_items,
        run_agent_name=agent_name,
        inherited_work_id=spawn_record.work_id,
    ) as session_context:
        resolved_plan = plan.model_copy(update={"agent_name": session_context.resolved_agent_name})
        return await execute_with_finalization(
            spawn,
            plan=resolved_plan,
            repo_root=runtime.repo_root,
            state_root=state_root,
            artifacts=runtime.artifacts,
            registry=runtime.harness_registry,
            cwd=runtime.repo_root,
            env_overrides=_spawn_child_env(
                str(spawn.spawn_id),
                work_id=session_context.work_id or spawn_record.work_id,
                state_root=state_root,
                autocompact=plan.autocompact,
                ctx=resolved_context,
            ),
            harness_session_id_observer=session_context.harness_session_id_observer,
        )


def _build_background_worker_command(
    *,
    spawn_id: str,
    repo_root: Path,
    timeout: float | None,
    skills: tuple[str, ...],
    agent_name: str | None,
    mcp_tools: tuple[str, ...],
    permission_config: PermissionConfig,
    allowed_tools: tuple[str, ...],
    passthrough_args: tuple[str, ...],
    continue_harness_session_id: str | None,
    continue_fork: bool,
    session_agent: str,
    session_agent_path: str,
    session_skill_paths: tuple[str, ...],
    adhoc_agent_payload: str = "",
    appended_system_prompt: str | None = None,
    autocompact: int | None = None,
) -> tuple[str, ...]:
    command: list[str] = [
        sys.executable,
        "-m",
        "meridian.lib.ops.spawn.execute",
        "--spawn-id",
        spawn_id,
        "--repo-root",
        repo_root.as_posix(),
    ]
    if permission_config.tier is not None:
        command.extend(["--permission-tier", permission_config.tier.value])
    command.extend(["--approval", permission_config.approval])
    if timeout is not None:
        command.extend(["--timeout", str(timeout)])
    if agent_name is not None:
        command.extend(["--agent", agent_name])
    if skills:
        command.extend(["--skills", ",".join(skills)])
    for tool in mcp_tools:
        command.extend(["--mcp-tool", tool])
    for tool in allowed_tools:
        command.extend(["--allowed-tool", tool])
    for passthrough_arg in passthrough_args:
        command.extend(["--harness-arg", passthrough_arg])
    if adhoc_agent_payload.strip():
        command.extend(["--adhoc-agent-payload", adhoc_agent_payload])
    if continue_harness_session_id is not None and continue_harness_session_id.strip():
        command.extend(["--continue-harness-session-id", continue_harness_session_id.strip()])
    if continue_fork:
        command.append("--continue-fork")
    if session_agent:
        command.extend(["--session-agent", session_agent])
    if session_agent_path:
        command.extend(["--session-agent-path", session_agent_path])
    for skill_path in session_skill_paths:
        command.extend(["--session-skill-path", skill_path])
    if autocompact is not None:
        command.extend(["--autocompact", str(autocompact)])
    if appended_system_prompt is not None:
        command.extend(["--appended-system-prompt", appended_system_prompt])
    return tuple(command)


def execute_spawn_background(
    *,
    payload: SpawnCreateInput,
    prepared: PreparedSpawnPlan,
    runtime: OperationRuntime,
    ctx: RuntimeContext | None = None,
) -> SpawnActionOutput:
    resolved_context = runtime_context(ctx)
    if payload.stream:
        logger.warning("--stream is ignored with --background; output goes to spawn log files.")
    context = _init_spawn(
        payload=payload,
        prepared=prepared,
        runtime=runtime,
        desc=payload.desc,
        work_id=payload.work,
        status="queued",
        launch_mode=BACKGROUND_LAUNCH_MODE,
        ctx=resolved_context,
    )
    spawn_id_text = str(context.spawn.spawn_id)
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

    launch_command = _build_background_worker_command(
        spawn_id=spawn_id_text,
        repo_root=runtime.repo_root,
        timeout=payload.timeout,
        skills=prepared.skills,
        agent_name=prepared.agent_name,
        mcp_tools=prepared.mcp_tools,
        permission_config=prepared.execution.permission_config,
        allowed_tools=prepared.execution.allowed_tools,
        passthrough_args=prepared.passthrough_args,
        continue_harness_session_id=prepared.session.harness_session_id,
        continue_fork=prepared.session.continue_fork,
        session_agent=prepared.session_agent,
        session_agent_path=prepared.session_agent_path,
        session_skill_paths=prepared.skill_paths,
        adhoc_agent_payload=prepared.adhoc_agent_payload,
        appended_system_prompt=prepared.appended_system_prompt,
        autocompact=prepared.autocompact,
    )
    log_dir = resolve_spawn_log_dir(runtime.repo_root, context.spawn.spawn_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / _BACKGROUND_STDOUT_FILENAME
    stderr_path = log_dir / _BACKGROUND_STDERR_FILENAME

    launch_env = dict(os.environ)
    launch_env.update(
        _spawn_child_env(
            spawn_id=spawn_id_text,
            work_id=context.work_id,
            state_root=context.state_root,
            autocompact=prepared.autocompact,
            ctx=resolved_context,
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
            error=str(exc),
        )
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

    atomic_write_text(log_dir / _BACKGROUND_PID_FILENAME, f"{process.pid}\n")
    mark_spawn_running(
        context.state_root,
        context.spawn.spawn_id,
        launch_mode=BACKGROUND_LAUNCH_MODE,
        wrapper_pid=process.pid,
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
        ctx=resolved_context,
    )
    spawn = context.spawn
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
        session_agent_source=prepared.agent_source,
        skills=prepared.skills,
        session_skill_paths=prepared.skill_paths,
        skill_sources=prepared.skill_sources,
        bootstrap_required_items=prepared.bootstrap_required_items,
        bootstrap_missing_items=prepared.bootstrap_missing_items,
        run_agent_name=prepared.agent_name,
        inherited_work_id=context.work_id,
    ) as session_context:
        resolved_plan = prepared.model_copy(
            update={"agent_name": session_context.resolved_agent_name}
        )
        exit_code = asyncio.run(
            execute_with_finalization(
                spawn,
                plan=resolved_plan,
                repo_root=runtime.repo_root,
                state_root=context.state_root,
                artifacts=runtime.artifacts,
                registry=runtime.harness_registry,
                cwd=runtime.repo_root,
                env_overrides=_spawn_child_env(
                    str(spawn.spawn_id),
                    work_id=session_context.work_id or context.work_id,
                    state_root=context.state_root,
                    autocompact=prepared.autocompact,
                    ctx=resolved_context,
                ),
                event_observer=event_observer,
                stream_stdout_to_terminal=stream_stdout_to_terminal,
                stream_stderr_to_terminal=payload.stream,
                harness_session_id_observer=session_context.harness_session_id_observer,
            )
        )
    duration = time.monotonic() - started
    row = read_spawn_row(runtime.repo_root, str(spawn.spawn_id))
    _, report_text = read_report_text(runtime.repo_root, str(spawn.spawn_id))
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
        report=report_text,
        exit_code=exit_code,
        duration_secs=duration,
    )


def _build_background_worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m meridian.lib.ops.spawn.execute")
    parser.add_argument("--spawn-id", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--skills", default="")
    parser.add_argument("--agent", default=None)
    parser.add_argument("--mcp-tool", action="append", default=[])
    parser.add_argument("--allowed-tool", action="append", default=[])
    parser.add_argument("--permission-tier", required=False, default=None)
    parser.add_argument("--approval", default="default")
    parser.add_argument("--harness-arg", action="append", default=[])
    parser.add_argument("--continue-harness-session-id", default=None)
    parser.add_argument("--continue-fork", action="store_true")
    parser.add_argument("--session-agent", default="")
    parser.add_argument("--session-agent-path", default="")
    parser.add_argument("--session-skill-path", action="append", default=[])
    parser.add_argument("--adhoc-agent-payload", default="")
    parser.add_argument("--appended-system-prompt", default=None)
    parser.add_argument("--autocompact", type=int, default=None)
    return parser


def _background_worker_main(
    argv: Sequence[str] | None = None,
    *,
    ctx: RuntimeContext | None = None,
) -> int:
    resolved_context = runtime_context(ctx)
    parser = _build_background_worker_parser()
    parsed = parser.parse_args(list(argv) if argv is not None else None)

    allowed_tools = tuple(str(item) for item in parsed.allowed_tool)
    permission_config, permission_resolver = resolve_permission_pipeline(
        sandbox=cast("str | None", parsed.permission_tier),
        allowed_tools=allowed_tools,
        approval=str(parsed.approval),
    )
    return asyncio.run(
        _execute_existing_spawn(
            spawn_id=SpawnId(parsed.spawn_id),
            repo_root=Path(parsed.repo_root).expanduser().resolve(),
            timeout=parsed.timeout,
            skills=_parse_csv_skills(str(parsed.skills)),
            agent_name=cast("str | None", parsed.agent),
            mcp_tools=tuple(str(item) for item in parsed.mcp_tool),
            permission_config=permission_config,
            permission_resolver=permission_resolver,
            allowed_tools=allowed_tools,
            passthrough_args=tuple(str(item) for item in parsed.harness_arg),
            continue_harness_session_id=cast("str | None", parsed.continue_harness_session_id),
            continue_fork=bool(parsed.continue_fork),
            session_agent=str(parsed.session_agent),
            session_agent_path=str(parsed.session_agent_path),
            session_skill_paths=tuple(str(item) for item in parsed.session_skill_path),
            adhoc_agent_payload=str(parsed.adhoc_agent_payload),
            appended_system_prompt=cast("str | None", parsed.appended_system_prompt),
            autocompact=cast("int | None", parsed.autocompact),
            ctx=resolved_context,
        )
    )


if __name__ == "__main__":
    raise SystemExit(_background_worker_main())


__all__ = [
    "depth_exceeded_output",
    "depth_limits",
    "execute_spawn_background",
    "execute_spawn_blocking",
]
