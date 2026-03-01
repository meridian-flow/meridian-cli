"""Run execution helpers shared by sync and async run handlers."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol, cast

import structlog

from meridian.lib.config.agent import (
    AgentProfile,
    load_agent_profile,
    parse_agent_profile,
)
from meridian.lib.domain import Run
from meridian.lib.exec.spawn import execute_with_finalization
from meridian.lib.exec.terminal import TerminalEventFilter, resolve_visible_categories
from meridian.lib.harness.adapter import PermissionResolver
from meridian.lib.harness.materialize import cleanup_materialized, materialize_for_harness
from meridian.lib.ops._runtime import (
    SPACE_REQUIRED_ERROR,
    OperationRuntime,
    build_runtime,
    resolve_space_id,
)
from meridian.lib.safety.permissions import (
    PermissionConfig,
    build_permission_resolver,
    parse_permission_tier,
)
from meridian.lib.space.session_store import (
    start_session,
    stop_session,
    update_session_harness_id,
)
from meridian.lib.state import run_store
from meridian.lib.state.paths import resolve_run_log_dir, resolve_space_dir
from meridian.lib.types import ModelId, RunId, SpaceId

from ._run_models import RunActionOutput, RunCreateInput
from ._run_query import _read_run_row

_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()
logger = structlog.get_logger(__name__)
_BACKGROUND_SUBMIT_MESSAGE = "Background run submitted."
_BACKGROUND_PID_FILENAME = "background.pid"
_BACKGROUND_STDOUT_FILENAME = "background-launcher.stdout.log"
_BACKGROUND_STDERR_FILENAME = "background-launcher.stderr.log"


class _PreparedCreateLike(Protocol):
    model: str
    harness_id: str
    warning: str | None
    composed_prompt: str
    skills: tuple[str, ...]
    reference_files: tuple[str, ...]
    template_vars: dict[str, str]
    report_path: str
    mcp_tools: tuple[str, ...]
    agent_name: str | None
    session_agent: str
    session_agent_path: str
    skill_paths: tuple[str, ...]
    cli_command: tuple[str, ...]
    permission_config: PermissionConfig
    permission_resolver: PermissionResolver
    allowed_tools: tuple[str, ...]
    continue_harness_session_id: str | None
    continue_fork: bool


def _read_non_negative_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if value < 0:
        raise ValueError(f"{name} must be >= 0.")
    return value


def _depth_limits(max_depth: int) -> tuple[int, int]:
    current_depth = _read_non_negative_int_env("MERIDIAN_DEPTH", 0)
    if max_depth < 0:
        raise ValueError("max_depth must be >= 0.")
    return current_depth, max_depth


def _emit_subrun_event(payload: dict[str, Any]) -> None:
    if _read_non_negative_int_env("MERIDIAN_DEPTH", 0) <= 0:
        return
    event_payload = dict(payload)
    event_payload["v"] = 1
    parent_run_id = os.getenv("MERIDIAN_PARENT_RUN_ID", "").strip()
    event_payload["parent"] = parent_run_id or None
    event_payload["ts"] = time.time()
    print(json.dumps(event_payload, separators=(",", ":")), file=sys.stdout, flush=True)


def _depth_exceeded_output(current_depth: int, max_depth: int) -> RunActionOutput:
    return RunActionOutput(
        command="run.spawn",
        status="failed",
        message=f"Max agent depth ({max_depth}) reached. Complete this task directly.",
        error="max_depth_exceeded",
        current_depth=current_depth,
        max_depth=max_depth,
    )


def _run_child_env(
    space_id: str | None,
    parent_run_id: str | None = None,
) -> dict[str, str]:
    # Preserve Meridian run context across nesting without forwarding unrelated
    # parent process environment variables.
    child_env = {key: value for key, value in os.environ.items() if key.startswith("MERIDIAN_")}
    current_depth = _read_non_negative_int_env("MERIDIAN_DEPTH", 0)
    child_env["MERIDIAN_DEPTH"] = str(current_depth + 1)
    if space_id is not None:
        child_env["MERIDIAN_SPACE_ID"] = space_id
    if parent_run_id is None:
        child_env.pop("MERIDIAN_PARENT_RUN_ID", None)
    else:
        normalized_parent = parent_run_id.strip()
        if normalized_parent:
            child_env["MERIDIAN_PARENT_RUN_ID"] = normalized_parent
        else:
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


def _resolve_chat_id() -> str:
    chat_id = os.getenv("MERIDIAN_CHAT_ID", "").strip()
    if chat_id:
        return chat_id
    return "c0"


def _resolve_space(repo_root: Path, payload_space: str | None) -> tuple[SpaceId, Path]:
    resolved = resolve_space_id(payload_space)
    if resolved is None:
        raise ValueError(SPACE_REQUIRED_ERROR)
    return resolved, resolve_space_dir(repo_root, resolved)


def _stdout_is_tty() -> bool:
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False


async def _execute_existing_run(
    *,
    run_id: RunId,
    repo_root: Path,
    timeout_secs: float | None,
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
) -> int:
    runtime = build_runtime(str(repo_root))
    space_id_text = (space_id_hint or os.getenv("MERIDIAN_SPACE_ID", "")).strip()
    if not space_id_text:
        logger.error("Missing space ID for run execution.", run_id=str(run_id))
        return 1

    space_dir = resolve_space_dir(repo_root, space_id_text)
    run_record = run_store.get_run(space_dir, run_id)
    if run_record is None or run_record.model is None or run_record.prompt is None:
        logger.error("Run not found for background execution.", run_id=str(run_id))
        return 1
    run = Run(
        run_id=RunId(run_record.id),
        prompt=run_record.prompt,
        model=ModelId(run_record.model),
        status="running",
        space_id=SpaceId(space_id_text),
    )

    resolver = build_permission_resolver(
        allowed_tools=allowed_tools,
        permission_config=permission_config,
        cli_permission_override=cli_permission_override,
    )

    chat_id = start_session(
        space_dir,
        harness=run_record.harness or "",
        harness_session_id=run_record.harness_session_id or "",
        model=run_record.model,
        agent=session_agent,
        agent_path=session_agent_path,
        skills=skills,
        skill_paths=session_skill_paths,
    )
    resolved_agent_name = agent_name
    try:
        materialized_agent_name = _materialize_session_agent_name(
            repo_root=runtime.repo_root,
            harness_id=run_record.harness or "",
            chat_id=chat_id,
            session_agent=session_agent,
            session_agent_path=session_agent_path,
            run_agent_name=agent_name,
            skills=skills,
            session_skill_paths=session_skill_paths,
        )
        if materialized_agent_name is not None and materialized_agent_name != resolved_agent_name:
            resolved_agent_name = materialized_agent_name

        return await execute_with_finalization(
            run,
            repo_root=runtime.repo_root,
            space_dir=space_dir,
            artifacts=runtime.artifacts,
            registry=runtime.harness_registry,
            permission_resolver=resolver,
            permission_config=permission_config,
            cwd=runtime.repo_root,
            timeout_seconds=timeout_secs,
            kill_grace_seconds=runtime.config.kill_grace_seconds,
            skills=skills,
            agent=resolved_agent_name,
            mcp_tools=mcp_tools,
            env_overrides=_run_child_env(
                space_id_text,
                str(run.run_id),
            ),
            max_retries=runtime.config.max_retries,
            retry_backoff_seconds=runtime.config.retry_backoff_seconds,
            continue_harness_session_id=continue_harness_session_id,
            continue_fork=continue_fork,
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
                harness_id=run_record.harness or "",
                repo_root=runtime.repo_root,
                chat_id=chat_id,
            )


def _build_background_worker_command(
    *,
    run_id: str,
    repo_root: Path,
    space_id: str | None,
    timeout_secs: float | None,
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
        "meridian.lib.ops._run_execute",
        "--run-id",
        run_id,
        "--repo-root",
        repo_root.as_posix(),
        "--permission-tier",
        permission_config.tier.value,
    ]
    if space_id is not None:
        command.extend(["--space-id", space_id])
    if timeout_secs is not None:
        command.extend(["--timeout-secs", str(timeout_secs)])
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


def _execute_run_background(
    *,
    payload: RunCreateInput,
    prepared: _PreparedCreateLike,
    runtime: OperationRuntime,
) -> RunActionOutput:
    if payload.stream:
        logger.warning("--stream is ignored with --background; output goes to run log files.")
    space_id, space_dir = _resolve_space(runtime.repo_root, payload.space)
    run_id = run_store.start_run(
        space_dir,
        chat_id=_resolve_chat_id(),
        model=prepared.model,
        agent=prepared.agent_name or "",
        harness=prepared.harness_id,
        prompt=prepared.composed_prompt,
        harness_session_id=prepared.continue_harness_session_id,
    )
    run = Run(
        run_id=RunId(run_id),
        prompt=prepared.composed_prompt,
        model=ModelId(prepared.model),
        status="running",
        space_id=space_id,
    )
    run_id_text = str(run.run_id)
    space_id_str = str(space_id)

    current_depth = _read_non_negative_int_env("MERIDIAN_DEPTH", 0)
    run_start_event: dict[str, Any] = {
        "t": "meridian.run.start",
        "id": run_id_text,
        "model": prepared.model,
        "d": current_depth,
    }
    if prepared.agent_name is not None:
        run_start_event["agent"] = prepared.agent_name
    _emit_subrun_event(run_start_event)

    launch_command = _build_background_worker_command(
        run_id=run_id_text,
        repo_root=runtime.repo_root,
        space_id=space_id_str,
        timeout_secs=payload.timeout_secs,
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
    log_dir = resolve_run_log_dir(runtime.repo_root, run.run_id, run.space_id)
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
        run_store.finalize_run(
            space_dir,
            run.run_id,
            status="failed",
            exit_code=1,
            error=str(exc),
        )
        logger.exception(
            "Failed to launch background run worker.",
            run_id=run_id_text,
            command=list(launch_command),
        )
        return RunActionOutput(
            command="run.spawn",
            status="failed",
            run_id=run_id_text,
            message=f"Failed to launch background run: {exc}",
            error="background_launch_failed",
            model=prepared.model,
            harness_id=prepared.harness_id,
            warning=prepared.warning,
            agent=prepared.agent_name,
            reference_files=prepared.reference_files,
            template_vars=prepared.template_vars,
            report_path=prepared.report_path,
            exit_code=1,
        )

    (log_dir / _BACKGROUND_PID_FILENAME).write_text(f"{process.pid}\n", encoding="utf-8")
    # The Popen object goes out of scope without wait(). This is intentional:
    # the child runs in its own session (start_new_session=True) and is
    # re-parented to init/systemd. We only need the PID for diagnostics.
    return RunActionOutput(
        command="run.spawn",
        status="running",
        run_id=run_id_text,
        message=_BACKGROUND_SUBMIT_MESSAGE,
        model=prepared.model,
        harness_id=prepared.harness_id,
        warning=prepared.warning,
        agent=prepared.agent_name,
        reference_files=prepared.reference_files,
        template_vars=prepared.template_vars,
        report_path=prepared.report_path,
        background=True,
    )


def _execute_run_blocking(
    *,
    payload: RunCreateInput,
    prepared: _PreparedCreateLike,
    runtime: OperationRuntime,
) -> RunActionOutput:
    space_id, space_dir = _resolve_space(runtime.repo_root, payload.space)
    run_id = run_store.start_run(
        space_dir,
        chat_id=_resolve_chat_id(),
        model=prepared.model,
        agent=prepared.agent_name or "",
        harness=prepared.harness_id,
        prompt=prepared.composed_prompt,
        harness_session_id=prepared.continue_harness_session_id,
    )
    run = Run(
        run_id=RunId(run_id),
        prompt=prepared.composed_prompt,
        model=ModelId(prepared.model),
        status="running",
        space_id=space_id,
    )
    current_depth = _read_non_negative_int_env("MERIDIAN_DEPTH", 0)
    run_start_event: dict[str, Any] = {
        "t": "meridian.run.start",
        "id": str(run.run_id),
        "model": prepared.model,
        "d": current_depth,
    }
    if prepared.agent_name is not None:
        run_start_event["agent"] = prepared.agent_name
    _emit_subrun_event(run_start_event)

    started = time.monotonic()
    space_id_str = str(space_id)
    event_observer = None
    # --stream: raw firehose (stdout+stderr piped to terminal), no filtering.
    # Otherwise (TTY or not): use TerminalEventFilter for structured output.
    # Non-TTY callers (CI, parent agents) should never get raw dumps.
    stream_stdout_to_terminal = payload.stream
    if not payload.stream:
        event_filter = TerminalEventFilter(
            visible_categories=resolve_visible_categories(
                verbose=payload.verbose,
                quiet=payload.quiet,
                config=runtime.config.output,
            ),
            output_stream=sys.stderr,
            root_depth=_read_non_negative_int_env("MERIDIAN_DEPTH", 0),
        )
        event_observer = event_filter.observe

    chat_id = start_session(
        space_dir,
        harness=prepared.harness_id,
        harness_session_id=prepared.continue_harness_session_id or "",
        model=prepared.model,
        agent=prepared.session_agent,
        agent_path=prepared.session_agent_path,
        skills=prepared.skills,
        skill_paths=prepared.skill_paths,
    )
    resolved_agent_name = prepared.agent_name
    try:
        materialized_agent_name = _materialize_session_agent_name(
            repo_root=runtime.repo_root,
            harness_id=prepared.harness_id,
            chat_id=chat_id,
            session_agent=prepared.session_agent,
            session_agent_path=prepared.session_agent_path,
            run_agent_name=prepared.agent_name,
            skills=prepared.skills,
            session_skill_paths=prepared.skill_paths,
        )
        if materialized_agent_name is not None and materialized_agent_name != resolved_agent_name:
            resolved_agent_name = materialized_agent_name

        exit_code = asyncio.run(
            execute_with_finalization(
                run,
                repo_root=runtime.repo_root,
                space_dir=space_dir,
                artifacts=runtime.artifacts,
                registry=runtime.harness_registry,
                permission_resolver=prepared.permission_resolver,
                permission_config=prepared.permission_config,
                cwd=runtime.repo_root,
                timeout_seconds=payload.timeout_secs,
                kill_grace_seconds=runtime.config.kill_grace_seconds,
                skills=prepared.skills,
                agent=resolved_agent_name,
                mcp_tools=prepared.mcp_tools,
                env_overrides=_run_child_env(
                    space_id_str,
                    str(run.run_id),
                ),
                max_retries=runtime.config.max_retries,
                retry_backoff_seconds=runtime.config.retry_backoff_seconds,
                continue_harness_session_id=prepared.continue_harness_session_id,
                continue_fork=prepared.continue_fork,
                event_observer=event_observer,
                stream_stdout_to_terminal=stream_stdout_to_terminal,
                stream_stderr_to_terminal=payload.stream or payload.verbose,
                harness_session_id_observer=lambda session_id: update_session_harness_id(
                    space_dir,
                    chat_id,
                    session_id,
                ),
            )
        )
    finally:
        try:
            stop_session(space_dir, chat_id)
        finally:
            _cleanup_session_materialized(
                harness_id=prepared.harness_id,
                repo_root=runtime.repo_root,
                chat_id=chat_id,
            )
    duration = time.monotonic() - started

    row = _read_run_row(runtime.repo_root, str(run.run_id), space=space_id_str)
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
            "t": "meridian.run.done",
            "id": str(run.run_id),
            "exit": exit_code,
            "secs": done_secs,
            "tok": tokens_total,
            "d": current_depth,
        }
    )

    return RunActionOutput(
        command="run.spawn",
        status=status,
        run_id=str(run.run_id),
        message="Run completed.",
        model=prepared.model,
        harness_id=prepared.harness_id,
        warning=prepared.warning,
        agent=resolved_agent_name,
        reference_files=prepared.reference_files,
        template_vars=prepared.template_vars,
        report_path=prepared.report_path,
        exit_code=exit_code,
        duration_secs=duration,
    )


async def _execute_run_non_blocking(
    *,
    run_id: RunId,
    repo_root: Path,
    timeout_secs: float | None,
    skills: tuple[str, ...],
    agent_name: str | None,
    mcp_tools: tuple[str, ...],
    permission_config: PermissionConfig,
    allowed_tools: tuple[str, ...] = (),
    cli_permission_override: bool = False,
    continue_harness_session_id: str | None = None,
    continue_fork: bool = False,
    session_agent: str = "",
    session_agent_path: str = "",
    session_skill_paths: tuple[str, ...] = (),
) -> None:
    _ = await _execute_existing_run(
        run_id=run_id,
        repo_root=repo_root,
        timeout_secs=timeout_secs,
        skills=skills,
        agent_name=agent_name,
        mcp_tools=mcp_tools,
        permission_config=permission_config,
        allowed_tools=allowed_tools,
        cli_permission_override=cli_permission_override,
        continue_harness_session_id=continue_harness_session_id,
        continue_fork=continue_fork,
        session_agent=session_agent,
        session_agent_path=session_agent_path,
        session_skill_paths=session_skill_paths,
    )


def _track_task(task: asyncio.Task[None]) -> None:
    _BACKGROUND_TASKS.add(task)

    def _cleanup(done: asyncio.Task[None]) -> None:
        try:
            done.result()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Background run task failed.")
        finally:
            _BACKGROUND_TASKS.discard(done)

    task.add_done_callback(_cleanup)


def _build_background_worker_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m meridian.lib.ops._run_execute")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--space-id", default=None)
    parser.add_argument("--timeout-secs", type=float, default=None)
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


def _background_worker_main(argv: Sequence[str] | None = None) -> int:
    parser = _build_background_worker_parser()
    parsed = parser.parse_args(list(argv) if argv is not None else None)

    permission_config = PermissionConfig(
        tier=parse_permission_tier(parsed.permission_tier),
        unsafe=False,
    )
    allowed_tools = tuple(str(item) for item in parsed.allowed_tool)
    return asyncio.run(
        _execute_existing_run(
            run_id=RunId(parsed.run_id),
            repo_root=Path(parsed.repo_root).expanduser().resolve(),
            space_id_hint=parsed.space_id,
            timeout_secs=parsed.timeout_secs,
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
        )
    )


if __name__ == "__main__":
    raise SystemExit(_background_worker_main())
