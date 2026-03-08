"""Spawn execution helpers shared by sync and async spawn handlers."""


import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol, cast

import structlog
from pydantic import BaseModel, ConfigDict
from meridian.lib.catalog.agent import (
    AgentProfile,
    load_agent_profile,
    parse_agent_profile,
)
from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.domain import Spawn
from meridian.lib.launch.runner import execute_with_finalization
from meridian.lib.harness.adapter import PermissionResolver
from meridian.lib.harness.materialize import cleanup_materialized, materialize_for_harness
from meridian.lib.safety.permissions import (
    PermissionConfig,
    build_permission_resolver,
    parse_permission_tier,
)
from meridian.lib.core.sink import OutputSink
from meridian.lib.state.session_store import (
    start_session,
    stop_session,
    update_session_harness_id,
)
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_spawn_log_dir, resolve_space_dir
from meridian.lib.core.types import ModelId, SpawnId, SpaceId

from ..runtime import OperationRuntime, build_runtime, require_space_id
from .models import SpawnActionOutput, SpawnCreateInput
from .query import read_report_text, read_spawn_row

logger = structlog.get_logger(__name__)
_BACKGROUND_SUBMIT_MESSAGE = "Background spawn submitted."
_BACKGROUND_PID_FILENAME = "background.pid"
_BACKGROUND_STDOUT_FILENAME = "background-launcher.stdout.log"
_BACKGROUND_STDERR_FILENAME = "background-launcher.stderr.log"


def minutes_to_seconds(timeout_minutes: float | None) -> float | None:
    if timeout_minutes is None:
        return None
    return timeout_minutes * 60.0


class _PreparedCreateLike(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def harness_id(self) -> str: ...

    @property
    def warning(self) -> str | None: ...

    @property
    def composed_prompt(self) -> str: ...

    @property
    def skills(self) -> tuple[str, ...]: ...

    @property
    def reference_files(self) -> tuple[str, ...]: ...

    @property
    def template_vars(self) -> dict[str, str]: ...

    @property
    def mcp_tools(self) -> tuple[str, ...]: ...

    @property
    def agent_name(self) -> str | None: ...

    @property
    def session_agent(self) -> str: ...

    @property
    def session_agent_path(self) -> str: ...

    @property
    def skill_paths(self) -> tuple[str, ...]: ...

    @property
    def cli_command(self) -> tuple[str, ...]: ...

    @property
    def permission_config(self) -> PermissionConfig: ...

    @property
    def permission_resolver(self) -> PermissionResolver: ...

    @property
    def allowed_tools(self) -> tuple[str, ...]: ...

    @property
    def continue_harness_session_id(self) -> str | None: ...

    @property
    def continue_fork(self) -> bool: ...


class _SpawnContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn: Spawn
    space_id: SpaceId
    space_dir: Path
    current_depth: int


class _SessionExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    chat_id: str
    resolved_agent_name: str | None
    harness_session_id_observer: Callable[[str], None]


def _runtime_context(ctx: RuntimeContext | None) -> RuntimeContext:
    if ctx is not None:
        return ctx
    return RuntimeContext.from_environment()


def _optional_space_id(space_id: str | None) -> SpaceId | None:
    if space_id is None:
        return None
    normalized = space_id.strip()
    if not normalized:
        return None
    return SpaceId(normalized)


def _optional_spawn_id(spawn_id: str | None) -> SpawnId | None:
    if spawn_id is None:
        return None
    normalized = spawn_id.strip()
    if not normalized:
        return None
    return SpawnId(normalized)


def depth_limits(max_depth: int, *, ctx: RuntimeContext | None = None) -> tuple[int, int]:
    current_depth = _runtime_context(ctx).depth
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0.")
    return current_depth, max_depth


def _emit_subrun_event(
    payload: dict[str, Any],
    *,
    sink: OutputSink,
    ctx: RuntimeContext | None = None,
) -> None:
    runtime_context = _runtime_context(ctx)
    if runtime_context.depth <= 0:
        return
    event_payload = dict(payload)
    event_payload["v"] = 1
    parent_spawn_id = str(runtime_context.spawn_id or "")
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
    space_id: str | None,
    spawn_id: str | None = None,
    *,
    ctx: RuntimeContext | None = None,
) -> dict[str, str]:
    runtime_context = _runtime_context(ctx)
    # Preserve Meridian spawn context across nesting without forwarding unrelated
    # parent process environment variables.
    child_env = {key: value for key, value in os.environ.items() if key.startswith("MERIDIAN_")}
    resolved_space_id = _optional_space_id(space_id) or runtime_context.space_id
    resolved_spawn_id = _optional_spawn_id(spawn_id)
    if resolved_space_id is not None and resolved_spawn_id is not None:
        child_context = runtime_context.child_context(
            space_id=resolved_space_id,
            spawn_id=resolved_spawn_id,
        )
    else:
        child_context = RuntimeContext(
            space_id=resolved_space_id,
            spawn_id=resolved_spawn_id,
            parent_spawn_id=runtime_context.spawn_id if runtime_context.spawn_id is not None else None,
            depth=runtime_context.depth + 1,
            repo_root=runtime_context.repo_root,
            state_root=runtime_context.state_root,
            chat_id=runtime_context.chat_id,
        )
    child_env.update(child_context.to_env_overrides())
    if runtime_context.spawn_id is None:
        child_env.pop("MERIDIAN_PARENT_SPAWN_ID", None)
    if resolved_spawn_id is None:
        child_env.pop("MERIDIAN_SPAWN_ID", None)
    # Drop legacy name now that canonical spawn vars are used everywhere.
    child_env.pop("MERIDIAN_PARENT_RUN_ID", None)
    return child_env


def _skill_sources_from_session(
    *,
    skills: tuple[str, ...],
    session_skill_paths: tuple[str, ...],
) -> dict[str, Path]:
    skill_sources: dict[str, Path] = {}
    for skill_name, skill_path in zip(skills, session_skill_paths):
        normalized_path = skill_path.strip()
        if not normalized_path:
            continue
        skill_sources[skill_name] = Path(normalized_path).expanduser().resolve().parent
    return skill_sources


def _load_session_agent_profile(
    *,
    repo_root: Path,
    session_agent: str,
    session_agent_path: str,
    run_agent_name: str | None,
) -> AgentProfile | None:
    normalized_agent = session_agent.strip() or (run_agent_name or "").strip()
    if not normalized_agent:
        return None

    normalized_path = session_agent_path.strip()
    if normalized_path:
        candidate = Path(normalized_path).expanduser().resolve()
        if candidate.is_file():
            try:
                return parse_agent_profile(candidate)
            except OSError:
                logger.warning(
                    "Failed to parse session agent profile from path; trying registry lookup.",
                    agent=normalized_agent,
                    agent_path=normalized_path,
                    exc_info=True,
                )
    try:
        return load_agent_profile(normalized_agent, repo_root=repo_root)
    except FileNotFoundError:
        logger.warning(
            "Session agent profile not found for harness materialization.",
            agent=normalized_agent,
            agent_path=normalized_path,
        )
        return None


def _materialize_session_agent_name(
    *,
    repo_root: Path,
    harness_id: str,
    chat_id: str,
    session_agent: str,
    session_agent_path: str,
    run_agent_name: str | None,
    skills: tuple[str, ...],
    session_skill_paths: tuple[str, ...],
) -> str | None:
    normalized_harness = harness_id.strip()
    if not normalized_harness:
        return None

    skill_sources = _skill_sources_from_session(
        skills=skills,
        session_skill_paths=session_skill_paths,
    )
    profile = _load_session_agent_profile(
        repo_root=repo_root,
        session_agent=session_agent,
        session_agent_path=session_agent_path,
        run_agent_name=run_agent_name,
    )
    materialized = materialize_for_harness(
        profile,
        skill_sources,
        normalized_harness,
        repo_root,
        chat_id,
    )
    resolved_agent = materialized.agent_name.strip()
    return resolved_agent or None


def _cleanup_session_materialized(*, harness_id: str, repo_root: Path, chat_id: str) -> None:
    normalized_harness = harness_id.strip()
    if not normalized_harness:
        return
    try:
        cleanup_materialized(normalized_harness, repo_root, chat_id)
    except Exception:
        logger.warning(
            "Failed to cleanup materialized harness resources.",
            harness_id=normalized_harness,
            chat_id=chat_id,
            exc_info=True,
        )


def _resolve_chat_id(*, ctx: RuntimeContext | None = None) -> str:
    chat_id = _runtime_context(ctx).chat_id
    if chat_id:
        return chat_id
    return "c0"


def _resolve_space(
    repo_root: Path,
    payload_space: str | None,
    *,
    ctx: RuntimeContext | None = None,
) -> tuple[SpaceId, Path]:
    runtime_context = _runtime_context(ctx)
    resolved = require_space_id(payload_space, space_id=runtime_context.space_id)
    return resolved, resolve_space_dir(repo_root, resolved)


def _init_spawn(
    *,
    payload: SpawnCreateInput,
    prepared: _PreparedCreateLike,
    runtime: OperationRuntime,
    ctx: RuntimeContext | None = None,
) -> _SpawnContext:
    runtime_context = _runtime_context(ctx)
    space_id, space_dir = _resolve_space(runtime.repo_root, payload.space, ctx=runtime_context)
    spawn_id = spawn_store.start_spawn(
        space_dir,
        chat_id=_resolve_chat_id(ctx=runtime_context),
        model=prepared.model,
        agent=prepared.agent_name or "",
        harness=prepared.harness_id,
        kind="child",
        prompt=prepared.composed_prompt,
        harness_session_id=prepared.continue_harness_session_id,
    )
    spawn = Spawn(
        spawn_id=SpawnId(spawn_id),
        prompt=prepared.composed_prompt,
        model=ModelId(prepared.model),
        status="running",
        space_id=space_id,
    )
    current_depth = runtime_context.depth
    run_start_event: dict[str, Any] = {
        "t": "meridian.spawn.start",
        "id": str(spawn.spawn_id),
        "model": prepared.model,
        "d": current_depth,
    }
    if prepared.agent_name is not None:
        run_start_event["agent"] = prepared.agent_name
    _emit_subrun_event(run_start_event, sink=runtime.sink, ctx=runtime_context)
    return _SpawnContext(
        spawn=spawn,
        space_id=space_id,
        space_dir=space_dir,
        current_depth=current_depth,
    )


def _write_params_json(
    repo_root: Path,
    spawn_id: SpawnId,
    space_id: str,
    prepared: _PreparedCreateLike,
) -> None:
    """Write resolved execution params to the spawn directory."""
    params_path = resolve_spawn_log_dir(repo_root, spawn_id, space_id) / "params.json"
    params_path.parent.mkdir(parents=True, exist_ok=True)
    params_payload = {
        "model": prepared.model,
        "harness": prepared.harness_id,
        "agent": prepared.agent_name,
        "prompt_length": len(prepared.composed_prompt),
        "reference_files": list(prepared.reference_files),
        "template_vars": prepared.template_vars,
        "skills": list(prepared.skills),
        "permission_tier": prepared.permission_config.tier.value,
        "continue_session": prepared.continue_harness_session_id,
        "continue_fork": prepared.continue_fork,
    }
    fd, tmp = tempfile.mkstemp(dir=str(params_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(params_payload, handle, indent=2)
        os.replace(tmp, params_path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@contextmanager
def _session_execution_context(
    *,
    space_dir: Path,
    harness_id: str,
    harness_session_id: str,
    model: str,
    session_agent: str,
    session_agent_path: str,
    skills: tuple[str, ...],
    session_skill_paths: tuple[str, ...],
    repo_root: Path,
    run_agent_name: str | None,
) -> Iterator[_SessionExecutionContext]:
    chat_id = start_session(
        space_dir,
        harness=harness_id,
        harness_session_id=harness_session_id,
        model=model,
        agent=session_agent,
        agent_path=session_agent_path,
        skills=skills,
        skill_paths=session_skill_paths,
    )
    resolved_agent_name = run_agent_name
    try:
        materialized_agent_name = _materialize_session_agent_name(
            repo_root=repo_root,
            harness_id=harness_id,
            chat_id=chat_id,
            session_agent=session_agent,
            session_agent_path=session_agent_path,
            run_agent_name=run_agent_name,
            skills=skills,
            session_skill_paths=session_skill_paths,
        )
        if materialized_agent_name is not None and materialized_agent_name != resolved_agent_name:
            resolved_agent_name = materialized_agent_name
        yield _SessionExecutionContext(
            chat_id=chat_id,
            resolved_agent_name=resolved_agent_name,
            harness_session_id_observer=lambda session_id: update_session_harness_id(
                space_dir,
                chat_id,
                session_id,
            ),
        )
    finally:
        try:
            stop_session(space_dir, chat_id)
        finally:
            _cleanup_session_materialized(
                harness_id=harness_id,
                repo_root=repo_root,
                chat_id=chat_id,
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
    allowed_tools: tuple[str, ...] = (),
    cli_permission_override: bool = False,
    continue_harness_session_id: str | None = None,
    continue_fork: bool = False,
    space_id_hint: str | None = None,
    session_agent: str = "",
    session_agent_path: str = "",
    session_skill_paths: tuple[str, ...] = (),
    sink: OutputSink | None = None,
    ctx: RuntimeContext | None = None,
) -> int:
    runtime_context = _runtime_context(ctx)
    runtime = build_runtime(str(repo_root), sink=sink)
    space_id_text = (space_id_hint or str(runtime_context.space_id or "")).strip()
    if not space_id_text:
        logger.error("Missing space ID for spawn execution.", spawn_id=str(spawn_id))
        return 1

    space_dir = resolve_space_dir(repo_root, space_id_text)
    spawn_record = spawn_store.get_spawn(space_dir, spawn_id)
    if spawn_record is None or spawn_record.model is None or spawn_record.prompt is None:
        logger.error("Spawn not found for background execution.", spawn_id=str(spawn_id))
        return 1
    spawn = Spawn(
        spawn_id=SpawnId(spawn_record.id),
        prompt=spawn_record.prompt,
        model=ModelId(spawn_record.model),
        status="running",
        space_id=SpaceId(space_id_text),
    )

    resolver = build_permission_resolver(
        allowed_tools=allowed_tools,
        permission_config=permission_config,
        cli_permission_override=cli_permission_override,
    )

    with _session_execution_context(
        space_dir=space_dir,
        harness_id=spawn_record.harness or "",
        harness_session_id=spawn_record.harness_session_id or "",
        model=spawn_record.model,
        session_agent=session_agent,
        session_agent_path=session_agent_path,
        skills=skills,
        session_skill_paths=session_skill_paths,
        repo_root=runtime.repo_root,
        run_agent_name=agent_name,
    ) as session_context:
        return await execute_with_finalization(
            spawn,
            repo_root=runtime.repo_root,
            space_dir=space_dir,
            artifacts=runtime.artifacts,
            registry=runtime.harness_registry,
            permission_resolver=resolver,
            permission_config=permission_config,
            cwd=runtime.repo_root,
            timeout_seconds=minutes_to_seconds(timeout),
            kill_grace_seconds=(
                minutes_to_seconds(runtime.config.kill_grace_minutes) or 0.0
            ),
            skills=skills,
            agent=session_context.resolved_agent_name,
            mcp_tools=mcp_tools,
            env_overrides=_spawn_child_env(
                space_id_text,
                str(spawn.spawn_id),
                ctx=runtime_context,
            ),
            max_retries=runtime.config.max_retries,
            retry_backoff_seconds=runtime.config.retry_backoff_seconds,
            continue_harness_session_id=continue_harness_session_id,
            continue_fork=continue_fork,
            harness_session_id_observer=session_context.harness_session_id_observer,
        )


def _build_background_worker_command(
    *,
    spawn_id: str,
    repo_root: Path,
    space_id: str | None,
    timeout: float | None,
    skills: tuple[str, ...],
    agent_name: str | None,
    mcp_tools: tuple[str, ...],
    permission_config: PermissionConfig,
    allowed_tools: tuple[str, ...],
    cli_permission_override: bool,
    continue_harness_session_id: str | None,
    continue_fork: bool,
    session_agent: str,
    session_agent_path: str,
    session_skill_paths: tuple[str, ...],
) -> tuple[str, ...]:
    command: list[str] = [
        sys.executable,
        "-m",
        "meridian.lib.ops.spawn.execute",
        "--spawn-id",
        spawn_id,
        "--repo-root",
        repo_root.as_posix(),
        "--permission-tier",
        permission_config.tier.value,
    ]
    if space_id is not None:
        command.extend(["--space-id", space_id])
    if timeout is not None:
        command.extend(["--timeout", str(timeout)])
    if agent_name is not None:
        command.extend(["--agent", agent_name])
    for skill in skills:
        command.extend(["--skill", skill])
    for tool in mcp_tools:
        command.extend(["--mcp-tool", tool])
    for tool in allowed_tools:
        command.extend(["--allowed-tool", tool])
    if cli_permission_override:
        command.append("--cli-permission-override")
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
    return tuple(command)


def execute_spawn_background(
    *,
    payload: SpawnCreateInput,
    prepared: _PreparedCreateLike,
    runtime: OperationRuntime,
    ctx: RuntimeContext | None = None,
) -> SpawnActionOutput:
    runtime_context = _runtime_context(ctx)
    if payload.stream:
        logger.warning("--stream is ignored with --background; output goes to spawn log files.")
    context = _init_spawn(payload=payload, prepared=prepared, runtime=runtime, ctx=runtime_context)
    spawn_id_text = str(context.spawn.spawn_id)
    space_id_str = str(context.space_id)
    try:
        _write_params_json(runtime.repo_root, context.spawn.spawn_id, space_id_str, prepared)
    except Exception:
        logger.warning("Failed to write params.json", spawn_id=spawn_id_text, exc_info=True)

    launch_command = _build_background_worker_command(
        spawn_id=spawn_id_text,
        repo_root=runtime.repo_root,
        space_id=space_id_str,
        timeout=payload.timeout,
        skills=prepared.skills,
        agent_name=prepared.agent_name,
        mcp_tools=prepared.mcp_tools,
        permission_config=prepared.permission_config,
        allowed_tools=prepared.allowed_tools,
        cli_permission_override=payload.permission_tier is not None,
        continue_harness_session_id=prepared.continue_harness_session_id,
        continue_fork=prepared.continue_fork,
        session_agent=prepared.session_agent,
        session_agent_path=prepared.session_agent_path,
        session_skill_paths=prepared.skill_paths,
    )
    log_dir = resolve_spawn_log_dir(runtime.repo_root, context.spawn.spawn_id, context.spawn.space_id)
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / _BACKGROUND_STDOUT_FILENAME
    stderr_path = log_dir / _BACKGROUND_STDERR_FILENAME

    launch_env = dict(os.environ)
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
            context.space_dir,
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
            exit_code=1,
        )

    (log_dir / _BACKGROUND_PID_FILENAME).write_text(f"{process.pid}\n", encoding="utf-8")
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
        background=True,
    )


def execute_spawn_blocking(
    *,
    payload: SpawnCreateInput,
    prepared: _PreparedCreateLike,
    runtime: OperationRuntime,
    ctx: RuntimeContext | None = None,
) -> SpawnActionOutput:
    runtime_context = _runtime_context(ctx)
    context = _init_spawn(payload=payload, prepared=prepared, runtime=runtime, ctx=runtime_context)
    spawn = context.spawn
    try:
        _write_params_json(runtime.repo_root, spawn.spawn_id, str(context.space_id), prepared)
    except Exception:
        logger.warning("Failed to write params.json", spawn_id=str(spawn.spawn_id), exc_info=True)
    started = time.monotonic()
    space_id_str = str(context.space_id)
    stream_stdout_to_terminal = payload.stream
    event_observer = None
    # Spawn execution stays silent unless --stream is explicitly enabled.

    with _session_execution_context(
        space_dir=context.space_dir,
        harness_id=prepared.harness_id,
        harness_session_id=prepared.continue_harness_session_id or "",
        model=prepared.model,
        session_agent=prepared.session_agent,
        session_agent_path=prepared.session_agent_path,
        skills=prepared.skills,
        session_skill_paths=prepared.skill_paths,
        repo_root=runtime.repo_root,
        run_agent_name=prepared.agent_name,
    ) as session_context:
        exit_code = asyncio.run(
            execute_with_finalization(
                spawn,
                repo_root=runtime.repo_root,
                space_dir=context.space_dir,
                artifacts=runtime.artifacts,
                registry=runtime.harness_registry,
                permission_resolver=prepared.permission_resolver,
                permission_config=prepared.permission_config,
                cwd=runtime.repo_root,
                timeout_seconds=minutes_to_seconds(payload.timeout),
                kill_grace_seconds=(
                    minutes_to_seconds(runtime.config.kill_grace_minutes) or 0.0
                ),
                skills=prepared.skills,
                agent=session_context.resolved_agent_name,
                mcp_tools=prepared.mcp_tools,
                env_overrides=_spawn_child_env(
                    space_id_str,
                    str(spawn.spawn_id),
                    ctx=runtime_context,
                ),
                max_retries=runtime.config.max_retries,
                retry_backoff_seconds=runtime.config.retry_backoff_seconds,
                continue_harness_session_id=prepared.continue_harness_session_id,
                continue_fork=prepared.continue_fork,
                event_observer=event_observer,
                stream_stdout_to_terminal=stream_stdout_to_terminal,
                stream_stderr_to_terminal=payload.stream,
                harness_session_id_observer=session_context.harness_session_id_observer,
            )
        )
    duration = time.monotonic() - started
    row = read_spawn_row(runtime.repo_root, str(spawn.spawn_id), space=space_id_str)
    _, report_text = read_report_text(runtime.repo_root, str(spawn.spawn_id), space=space_id_str)
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
        ctx=runtime_context,
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
        report=report_text,
        exit_code=exit_code,
        duration_secs=duration,
    )


def _build_background_worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m meridian.lib.ops.spawn.execute")
    parser.add_argument("--spawn-id", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--space-id", default=None)
    parser.add_argument("--timeout", type=float, default=None)
    parser.add_argument("--skill", action="append", default=[])
    parser.add_argument("--agent", default=None)
    parser.add_argument("--mcp-tool", action="append", default=[])
    parser.add_argument("--allowed-tool", action="append", default=[])
    parser.add_argument("--permission-tier", required=True)
    parser.add_argument("--cli-permission-override", action="store_true")
    parser.add_argument("--continue-harness-session-id", default=None)
    parser.add_argument("--continue-fork", action="store_true")
    parser.add_argument("--session-agent", default="")
    parser.add_argument("--session-agent-path", default="")
    parser.add_argument("--session-skill-path", action="append", default=[])
    return parser


def _background_worker_main(
    argv: Sequence[str] | None = None,
    *,
    ctx: RuntimeContext | None = None,
) -> int:
    runtime_context = _runtime_context(ctx)
    parser = _build_background_worker_parser()
    parsed = parser.parse_args(list(argv) if argv is not None else None)

    permission_config = PermissionConfig(
        tier=parse_permission_tier(parsed.permission_tier),
        approval="confirm",
    )
    allowed_tools = tuple(str(item) for item in parsed.allowed_tool)
    return asyncio.run(
        _execute_existing_spawn(
            spawn_id=SpawnId(parsed.spawn_id),
            repo_root=Path(parsed.repo_root).expanduser().resolve(),
            space_id_hint=parsed.space_id,
            timeout=parsed.timeout,
            skills=tuple(str(item) for item in parsed.skill),
            agent_name=cast("str | None", parsed.agent),
            mcp_tools=tuple(str(item) for item in parsed.mcp_tool),
            permission_config=permission_config,
            allowed_tools=allowed_tools,
            cli_permission_override=bool(parsed.cli_permission_override),
            continue_harness_session_id=cast("str | None", parsed.continue_harness_session_id),
            continue_fork=bool(parsed.continue_fork),
            session_agent=str(parsed.session_agent),
            session_agent_path=str(parsed.session_agent_path),
            session_skill_paths=tuple(str(item) for item in parsed.session_skill_path),
            ctx=runtime_context,
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
