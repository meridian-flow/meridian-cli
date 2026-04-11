"""Async subprocess execution and finalization guarantees."""

import asyncio
import json
import os
import signal
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ConfigDict

from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.domain import Spawn
from meridian.lib.core.spawn_lifecycle import (
    has_durable_report_completion,
    resolve_execution_terminal_state,
)
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import (
    SpawnParams,
    StreamEvent,
)
from meridian.lib.harness.claude_preflight import ensure_claude_session_accessible
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.cwd import resolve_child_execution_cwd
from meridian.lib.launch.launch_types import PreflightResult
from meridian.lib.safety.budget import Budget, BudgetBreach, LiveBudgetTracker
from meridian.lib.safety.guardrails import GuardrailFailure, run_guardrails
from meridian.lib.safety.redaction import SecretSpec, redact_secret_bytes
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import ArtifactStore, make_artifact_key
from meridian.lib.state.atomic import atomic_write_bytes, atomic_write_text
from meridian.lib.state.paths import resolve_spawn_log_dir, resolve_state_paths
from meridian.lib.state.spawn_store import FOREGROUND_LAUNCH_MODE

from .env import build_harness_child_env
from .errors import ErrorCategory, classify_error, should_retry
from .extract import (
    FinalizeExtraction,
    enrich_finalize,
    reset_finalize_attempt_artifacts,
)
from .heartbeat import heartbeat_scope
from .session_ids import extract_latest_session_id
from .signals import (
    SignalForwarder,
    map_process_exit_code,
    signal_coordinator,
    signal_process_group,
)
from .stream_capture import (
    capture_stderr_stream,
    capture_stdout_stream,
    extract_latest_tokens_payload,
)
from .timeout import (
    DEFAULT_KILL_GRACE_SECONDS,
    SpawnTimeoutError,
    terminate_process,
    wait_for_process_exit,
    wait_for_process_returncode,
)

if TYPE_CHECKING:
    from meridian.lib.ops.spawn.plan import PreparedSpawnPlan

OUTPUT_FILENAME = "output.jsonl"
STDERR_FILENAME = "stderr.log"
TOKENS_FILENAME = "tokens.json"
REPORT_FILENAME = "report.md"
DEFAULT_INFRA_EXIT_CODE = 2
POST_EXIT_PIPE_DRAIN_TIMEOUT_SECONDS = 1.0
_DEFAULT_CONFIG = MeridianConfig()
DEFAULT_GUARDRAIL_TIMEOUT_SECONDS = _DEFAULT_CONFIG.guardrail_timeout_minutes * 60.0
logger = structlog.get_logger(__name__)


def _raw_return_code_matches_sigterm(raw_return_code: int) -> bool:
    if raw_return_code >= 0:
        return False
    try:
        return signal.Signals(-raw_return_code) == signal.SIGTERM
    except ValueError:
        return False


class SpawnResult(BaseModel):
    """Result from one spawned harness process."""

    model_config = ConfigDict(frozen=True)

    exit_code: int
    raw_return_code: int
    timed_out: bool
    received_signal: signal.Signals | None
    output_log_path: Path
    stderr_log_path: Path
    budget_breach: BudgetBreach | None = None
    terminated_by_report_watchdog: bool = False


def run_log_dir(repo_root: Path, spawn_id: SpawnId) -> Path:
    """Resolve run artifact directory from a spawn ID."""

    return resolve_spawn_log_dir(repo_root, spawn_id)


def _read_captured_output(path: Path) -> bytes:
    if not path.exists():
        return b""
    return path.read_bytes()


def _persist_captured_artifacts(
    *,
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    output_log_path: Path,
    stderr_log_path: Path,
    tokens_payload: bytes | None,
) -> None:
    stdout_bytes = _read_captured_output(output_log_path)
    stderr_bytes = _read_captured_output(stderr_log_path)
    resolved_tokens_payload = tokens_payload
    if resolved_tokens_payload is None and stdout_bytes:
        resolved_tokens_payload = extract_latest_tokens_payload(stdout_bytes)

    artifacts.put(make_artifact_key(spawn_id, OUTPUT_FILENAME), stdout_bytes)
    artifacts.put(make_artifact_key(spawn_id, STDERR_FILENAME), stderr_bytes)
    if resolved_tokens_payload is not None:
        artifacts.put(make_artifact_key(spawn_id, TOKENS_FILENAME), resolved_tokens_payload)


async def _terminate_after_cancellation(
    process: asyncio.subprocess.Process,
    *,
    kill_grace_seconds: float,
) -> None:
    if process.returncode is not None:
        return

    # Task cancellation is usually driven by caller/user interruption, so we mirror
    # Ctrl-C semantics and let children handle graceful SIGINT shutdown paths.
    signal_process_group(process, signal.SIGINT)
    try:
        await wait_for_process_returncode(process, timeout_seconds=kill_grace_seconds)
    except SpawnTimeoutError:
        if process.returncode is None:
            signal_process_group(process, signal.SIGKILL)
            await wait_for_process_returncode(process)


async def _report_watchdog(
    report_path: Path,
    process: asyncio.subprocess.Process,
    grace_secs: float = 60.0,
) -> bool:
    """Kill harness process if report.md appears but process doesn't exit.

    Polls for report.md creation, then waits a grace period for clean exit.
    If the process is still alive after grace, terminates it via the
    existing terminate_process() helper.
    """
    poll_interval = 5.0
    while not report_path.exists():
        if process.returncode is not None:
            return False  # Process exited cleanly, no watchdog needed
        await asyncio.sleep(poll_interval)

    # Report exists. Wait grace period, checking for activity.
    deadline = asyncio.get_running_loop().time() + grace_secs
    while asyncio.get_running_loop().time() < deadline:
        if process.returncode is not None:
            return False  # Clean exit during grace
        await asyncio.sleep(poll_interval)

    # Still alive after grace — terminate
    if process.returncode is None:
        logger.info(
            "Report watchdog: harness wrote report but process still alive "
            "after %.0fs grace. Terminating.",
            grace_secs,
        )
        await terminate_process(process, grace_seconds=10.0)
        return True
    return False


async def spawn_and_stream(
    *,
    spawn_id: SpawnId,
    command: tuple[str, ...],
    cwd: Path,
    artifacts: ArtifactStore,
    output_log_path: Path,
    stderr_log_path: Path,
    timeout_seconds: float | None,
    env: dict[str, str] | None = None,
    stdin_text: str | None = None,
    kill_grace_seconds: float = DEFAULT_KILL_GRACE_SECONDS,
    budget_tracker: LiveBudgetTracker | None = None,
    secrets: tuple[SecretSpec, ...] = (),
    parse_stream_event: Callable[[str], StreamEvent | None] | None = None,
    event_observer: Callable[[StreamEvent], None] | None = None,
    stream_stdout_to_terminal: bool = False,
    stream_stderr_to_terminal: bool = False,
    log_dir: Path | None = None,
    report_watchdog_path: Path | None = None,
    on_process_started: Callable[[int], None] | None = None,
) -> SpawnResult:
    """Spawn one process, stream/capture output, and return mapped exit metadata."""

    if not command:
        raise ValueError("Cannot spawn process: command is empty.")

    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(cwd),
        env=env,
        start_new_session=True,
        stdin=asyncio.subprocess.PIPE if stdin_text is not None else None,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Subprocess did not expose stdout/stderr pipes.")

    budget_breach: BudgetBreach | None = None
    budget_termination_task: asyncio.Task[None] | None = None
    terminated_by_report_watchdog = False

    def _on_stdout_line(chunk: bytes) -> None:
        nonlocal budget_breach, budget_termination_task
        if budget_tracker is None or budget_breach is not None:
            return

        breach = budget_tracker.observe_json_line(chunk)
        if breach is None:
            return

        budget_breach = breach
        if process.returncode is None:
            # Budget breaches are infra-enforced limits; always escalate to SIGKILL
            # if the child ignores SIGTERM.
            budget_termination_task = asyncio.create_task(
                terminate_process(process, grace_seconds=kill_grace_seconds)
            )

    watchdog_task: asyncio.Task[None] | None = None
    stdout_task: asyncio.Task[bytes | None] | None = None
    stderr_task: asyncio.Task[bytes] | None = None
    stdin_task: asyncio.Task[None] | None = None
    received_signal: signal.Signals | None = None
    timed_out = False
    raw_return_code = DEFAULT_INFRA_EXIT_CODE
    with SignalForwarder(process) as forwarder:
        try:
            # Write harness child PID for external cleanup.
            if log_dir is not None:
                atomic_write_text(log_dir / "harness.pid", f"{process.pid}\n")
            if on_process_started is not None:
                try:
                    on_process_started(process.pid)
                except Exception:
                    await terminate_process(process, grace_seconds=kill_grace_seconds)
                    raise

            if report_watchdog_path is not None:

                async def _run_report_watchdog() -> None:
                    nonlocal terminated_by_report_watchdog
                    terminated_by_report_watchdog = await _report_watchdog(
                        report_path=report_watchdog_path,
                        process=process,
                    )

                watchdog_task = asyncio.create_task(_run_report_watchdog())

            stdout_task = asyncio.create_task(
                capture_stdout_stream(
                    process.stdout,
                    output_log_path,
                    secrets=secrets,
                    line_observer=_on_stdout_line,
                    parse_stream_event=parse_stream_event,
                    event_observer=event_observer,
                    stream_to_terminal=stream_stdout_to_terminal,
                )
            )
            stderr_task = asyncio.create_task(
                capture_stderr_stream(
                    process.stderr,
                    stderr_log_path,
                    secrets=secrets,
                    stream_to_terminal=stream_stderr_to_terminal,
                )
            )
            if stdin_text is not None:
                if process.stdin is None:
                    raise RuntimeError("Subprocess did not expose stdin pipe.")

                async def _feed_stdin() -> None:
                    assert process.stdin is not None
                    try:
                        process.stdin.write(stdin_text.encode("utf-8"))
                        await process.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    finally:
                        process.stdin.close()
                        with suppress(BrokenPipeError, ConnectionResetError):
                            await process.stdin.wait_closed()

                stdin_task = asyncio.create_task(_feed_stdin())

            try:
                raw_return_code = await wait_for_process_exit(
                    process,
                    timeout_seconds=timeout_seconds,
                    kill_grace_seconds=kill_grace_seconds,
                )
            except SpawnTimeoutError:
                timed_out = True
                raw_return_code = process.returncode if process.returncode is not None else 1
        except asyncio.CancelledError:
            await _terminate_after_cancellation(process, kill_grace_seconds=kill_grace_seconds)
            raise
        finally:
            if stdin_task is not None:
                await stdin_task
            if budget_termination_task is not None:
                await budget_termination_task
            if watchdog_task is not None:
                if not watchdog_task.done():
                    watchdog_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await watchdog_task
                else:
                    await watchdog_task
            tokens_payload: bytes | None = None

            if stdout_task is not None and stderr_task is not None:
                drain_done, drain_pending = await asyncio.wait(
                    {stdout_task, stderr_task},
                    timeout=POST_EXIT_PIPE_DRAIN_TIMEOUT_SECONDS,
                )
                if stdout_task in drain_done:
                    tokens_payload = await stdout_task
                else:
                    logger.warning(
                        "Timed out draining harness stdout after process exit; "
                        "using captured file contents.",
                        spawn_id=str(spawn_id),
                        timeout_seconds=POST_EXIT_PIPE_DRAIN_TIMEOUT_SECONDS,
                    )
                    stdout_task.cancel()
                if stderr_task in drain_done:
                    await stderr_task
                else:
                    logger.warning(
                        "Timed out draining harness stderr after process exit; "
                        "using captured file contents.",
                        spawn_id=str(spawn_id),
                        timeout_seconds=POST_EXIT_PIPE_DRAIN_TIMEOUT_SECONDS,
                    )
                    stderr_task.cancel()

                if drain_pending:
                    await asyncio.wait(drain_pending)

            _persist_captured_artifacts(
                artifacts=artifacts,
                spawn_id=spawn_id,
                output_log_path=output_log_path,
                stderr_log_path=stderr_log_path,
                tokens_payload=tokens_payload,
            )
            received_signal = forwarder.received_signal

    if budget_breach is not None:
        mapped_exit_code = DEFAULT_INFRA_EXIT_CODE
    elif timed_out:
        mapped_exit_code = 3
    else:
        mapped_exit_code = map_process_exit_code(
            raw_return_code=raw_return_code,
            received_signal=received_signal,
        )

    return SpawnResult(
        exit_code=mapped_exit_code,
        raw_return_code=raw_return_code,
        timed_out=timed_out,
        received_signal=received_signal,
        output_log_path=output_log_path,
        stderr_log_path=stderr_log_path,
        budget_breach=budget_breach,
        terminated_by_report_watchdog=terminated_by_report_watchdog,
    )


def _append_budget_exceeded_event(
    *,
    run: Spawn,
    breach: BudgetBreach,
) -> None:
    logger.warning(
        "Spawn budget exceeded.",
        spawn_id=str(run.spawn_id),
        scope=breach.scope,
        observed_usd=breach.observed_usd,
        limit_usd=breach.limit_usd,
    )


def _guardrail_failure_text(failures: tuple[GuardrailFailure, ...]) -> str:
    lines = ["Guardrail validation failed:"]
    for failure in failures:
        lines.append(
            f"- {failure.script} (exit {failure.exit_code})"
            + (f": {failure.stderr}" if failure.stderr else "")
        )
    return "\n".join(lines)


def _append_text_to_stderr_artifact(
    *,
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    text: str,
    secrets: tuple[SecretSpec, ...],
) -> None:
    key = make_artifact_key(spawn_id, STDERR_FILENAME)
    existing = artifacts.get(key).decode("utf-8", errors="ignore") if artifacts.exists(key) else ""
    prefix = "\n" if existing and not existing.endswith("\n") else ""
    combined = f"{existing}{prefix}{text}\n"
    artifacts.put(key, redact_secret_bytes(combined.encode("utf-8"), secrets))


def _artifact_is_zero_bytes(
    *,
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    filename: str,
) -> bool:
    key = make_artifact_key(spawn_id, filename)
    if not artifacts.exists(key):
        return True
    return len(artifacts.get(key)) == 0


def _write_structured_failure_artifact(
    *,
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    output_log_path: Path,
    exit_code: int,
    failure_reason: str | None,
    timed_out: bool,
) -> None:
    payload = {
        "error_code": "harness_empty_output",
        "failure_reason": failure_reason or "empty_output",
        "exit_code": exit_code,
        "timed_out": timed_out,
    }
    encoded = f"{json.dumps(payload, sort_keys=True)}\n".encode()
    artifacts.put(make_artifact_key(spawn_id, OUTPUT_FILENAME), encoded)
    atomic_write_bytes(output_log_path, encoded)


def _spawn_kind(state_root: Path, spawn_id: SpawnId) -> str:
    row = spawn_store.get_spawn(state_root, spawn_id)
    if row is None:
        return "child"
    normalized = row.kind.strip().lower()
    if normalized in {"primary", "child"}:
        return normalized
    return "child"


async def execute_with_finalization(
    run: Spawn,
    *,
    plan: "PreparedSpawnPlan",
    repo_root: Path,
    state_root: Path,
    artifacts: ArtifactStore,
    registry: HarnessRegistry,
    cwd: Path | None = None,
    env_overrides: dict[str, str] | None = None,
    harness_id: HarnessId | None = None,
    budget: Budget | None = None,
    space_spent_usd: float = 0.0,
    guardrails: tuple[Path, ...] = (),
    guardrail_timeout_seconds: float = DEFAULT_GUARDRAIL_TIMEOUT_SECONDS,
    secrets: tuple[SecretSpec, ...] = (),
    harness_session_id_observer: Callable[[str], None] | None = None,
    event_observer: Callable[[StreamEvent], None] | None = None,
    stream_stdout_to_terminal: bool = False,
    stream_stderr_to_terminal: bool = False,
) -> int:
    """Execute one run and always append a finalize row via try/finally."""

    execution_cwd = (cwd or Path.cwd()).resolve()
    log_dir = resolve_spawn_log_dir(repo_root, run.spawn_id)
    output_log_path = log_dir / OUTPUT_FILENAME
    report_path = log_dir / REPORT_FILENAME

    # Workaround: when running inside Claude Code, a child `claude -p` CLI
    # shares the same CWD-derived task directory and deletes the parent's
    # task output file during its own startup cleanup.  Using a distinct CWD
    # for the child gives it a separate task directory and avoids the
    # collision.  The project root is re-injected via `--add-dir` so the
    # child can still access project files.
    child_cwd = execution_cwd

    resolved_harness_id = harness_id or HarnessId(plan.harness_id)
    harness = registry.get_subprocess_harness(resolved_harness_id)

    timeout_seconds = plan.execution.timeout_secs
    kill_grace_seconds = plan.execution.kill_grace_secs
    max_retries = plan.execution.max_retries
    retry_backoff_seconds = plan.execution.retry_backoff_secs
    resolved_cwd = resolve_child_execution_cwd(
        repo_root=execution_cwd,
        spawn_id=run.spawn_id,
        harness_id=harness.id.value,
    )
    if resolved_cwd != execution_cwd:
        child_cwd = resolved_cwd
        child_cwd.mkdir(parents=True, exist_ok=True)

    try:
        preflight = harness.preflight(
            execution_cwd=execution_cwd,
            child_cwd=child_cwd,
            passthrough_args=plan.passthrough_args,
        )
    except AttributeError:
        preflight = PreflightResult.build(expanded_passthrough_args=plan.passthrough_args)
    run_params = SpawnParams(
        prompt=run.prompt,
        model=run.model if str(run.model).strip() else None,
        effort=plan.effort,
        skills=plan.skills,
        agent=plan.agent_name,
        adhoc_agent_payload=plan.adhoc_agent_payload,
        extra_args=preflight.expanded_passthrough_args,
        repo_root=child_cwd.as_posix(),
        mcp_tools=plan.mcp_tools,
        continue_harness_session_id=plan.session.harness_session_id,
        continue_fork=plan.session.continue_fork,
        report_output_path=report_path.as_posix(),
        appended_system_prompt=plan.appended_system_prompt,
    )
    # Codex fork materialization is resolved during plan construction:
    # - Child spawns: ops/spawn/prepare.py
    # - Primary launches: launch/process.py
    # runner.py executes the prepared plan and must not re-fork.
    prompt_stdin = run.prompt if harness.capabilities.supports_stdin_prompt else None

    resolved_perms = plan.execution.permission_resolver
    resolved_permission_config = plan.execution.permission_config
    runtime_env_overrides = {
        "MERIDIAN_REPO_ROOT": execution_cwd.as_posix(),
        "MERIDIAN_STATE_ROOT": resolve_state_paths(repo_root).root_dir.resolve().as_posix(),
    }
    merged_env_overrides = dict(env_overrides or {})
    merged_env_overrides.update(runtime_env_overrides)
    merged_env_overrides.update(preflight.extra_env)
    spawn_row = spawn_store.get_spawn(state_root, run.spawn_id)
    raw_launch_mode = (
        (spawn_row.launch_mode or "").strip().lower()
        if spawn_row is not None and spawn_row.launch_mode is not None
        else FOREGROUND_LAUNCH_MODE
    )
    resolved_launch_mode: spawn_store.LaunchMode = (
        spawn_store.BACKGROUND_LAUNCH_MODE
        if raw_launch_mode == spawn_store.BACKGROUND_LAUNCH_MODE
        else spawn_store.FOREGROUND_LAUNCH_MODE
    )
    if spawn_row is None:
        spawn_store.start_spawn(
            state_root,
            spawn_id=run.spawn_id,
            chat_id=os.getenv("MERIDIAN_CHAT_ID", "").strip() or "c0",
            model=str(run.model),
            agent=plan.agent_name or "",
            agent_path=plan.agent_path or None,
            skills=plan.skills,
            skill_paths=plan.skill_paths,
            harness=str(harness.id),
            kind="child",
            prompt=run.prompt,
            harness_session_id=plan.session.harness_session_id,
            launch_mode=FOREGROUND_LAUNCH_MODE,
            status="queued",
        )
    materialized_session_id = (run_params.continue_harness_session_id or "").strip()
    if (
        materialized_session_id
        and materialized_session_id != (plan.session.harness_session_id or "")
    ):
        spawn_store.update_spawn(
            state_root,
            run.spawn_id,
            harness_session_id=materialized_session_id,
        )
        if harness_session_id_observer is not None:
            harness_session_id_observer(materialized_session_id)

    # Record the actual execution CWD on the spawn record (authoritative).
    # Mirrors execute.py pre-compute; both sites must stay in sync.
    spawn_store.update_spawn(
        state_root,
        run.spawn_id,
        execution_cwd=str(child_cwd),
    )

    child_env = build_harness_child_env(
        base_env=os.environ,
        adapter=harness,
        run_params=run_params,
        permission_config=resolved_permission_config,
        runtime_env_overrides=merged_env_overrides,
    )

    def _record_worker_started(worker_pid: int) -> None:
        spawn_store.mark_spawn_running(
            state_root,
            run.spawn_id,
            launch_mode=resolved_launch_mode,
            worker_pid=worker_pid,
        )

    budget_tracker = (
        LiveBudgetTracker(budget=budget, space_spent_usd=space_spent_usd)
        if budget is not None
        else None
    )
    preflight_breach = budget_tracker.check() if budget_tracker is not None else None

    started_at = time.monotonic()
    started_at_epoch = time.time()
    exit_code = DEFAULT_INFRA_EXIT_CODE
    extracted: FinalizeExtraction | None = None
    failure_reason: str | None = None
    observed_harness_session_id: str | None = None
    terminated_after_completion = False
    last_raw_return_code = DEFAULT_INFRA_EXIT_CODE
    last_received_signal: signal.Signals | None = None
    last_timed_out = False
    heartbeat_path = log_dir / "heartbeat"

    async with heartbeat_scope(heartbeat_path):
        try:
            command = tuple(harness.build_command(run_params, resolved_perms))

            # Symlink source session into child's project dir so Claude can find it.
            if (
                harness.id == HarnessId.CLAUDE
                and plan.session.harness_session_id
                and plan.session.source_execution_cwd
            ):
                ensure_claude_session_accessible(
                    source_session_id=plan.session.harness_session_id,
                    source_cwd=Path(plan.session.source_execution_cwd),
                    child_cwd=child_cwd,
                )

            retries_attempted = 0

            while True:
                reset_finalize_attempt_artifacts(
                    artifacts=artifacts,
                    spawn_id=run.spawn_id,
                    log_dir=log_dir,
                )

                if preflight_breach is not None:
                    exit_code = DEFAULT_INFRA_EXIT_CODE
                    failure_reason = "budget_exceeded"
                    _append_budget_exceeded_event(run=run, breach=preflight_breach)
                    break

                spawn_result = await spawn_and_stream(
                    spawn_id=run.spawn_id,
                    command=command,
                    cwd=child_cwd,
                    artifacts=artifacts,
                    output_log_path=output_log_path,
                    stderr_log_path=log_dir / STDERR_FILENAME,
                    timeout_seconds=timeout_seconds,
                    env=child_env,
                    stdin_text=prompt_stdin,
                    kill_grace_seconds=kill_grace_seconds,
                    budget_tracker=budget_tracker,
                    secrets=secrets,
                    parse_stream_event=(
                        getattr(harness, "parse_stream_event", None)
                        if harness.capabilities.supports_stream_events
                        else None
                    ),
                    event_observer=event_observer,
                    stream_stdout_to_terminal=stream_stdout_to_terminal,
                    stream_stderr_to_terminal=stream_stderr_to_terminal,
                    log_dir=log_dir,
                    report_watchdog_path=report_path,
                    on_process_started=_record_worker_started,
                )
                exit_code = spawn_result.exit_code
                last_raw_return_code = spawn_result.raw_return_code
                last_received_signal = spawn_result.received_signal
                last_timed_out = spawn_result.timed_out
                terminated_after_completion = spawn_result.terminated_by_report_watchdog
                if spawn_result.timed_out:
                    failure_reason = "timeout"

                if report_path.exists():
                    redacted_report = redact_secret_bytes(report_path.read_bytes(), secrets)
                    atomic_write_bytes(report_path, redacted_report)
                    artifacts.put(
                        make_artifact_key(run.spawn_id, REPORT_FILENAME),
                        redacted_report,
                    )

                extracted = enrich_finalize(
                    artifacts=artifacts,
                    extractor=harness,
                    spawn_id=run.spawn_id,
                    log_dir=log_dir,
                    secrets=secrets,
                )
                extracted_harness_session_id = (
                    extract_latest_session_id(
                        extractor=harness,
                        current_session_id=observed_harness_session_id,
                        artifacts=artifacts,
                        spawn_id=run.spawn_id,
                        repo_root=repo_root,
                        started_at_epoch=started_at_epoch,
                    )
                    or ""
                )
                if (
                    extracted_harness_session_id
                    and extracted_harness_session_id != observed_harness_session_id
                ):
                    try:
                        spawn_store.update_spawn(
                            state_root,
                            run.spawn_id,
                            harness_session_id=extracted_harness_session_id,
                        )
                        if harness_session_id_observer is not None:
                            harness_session_id_observer(extracted_harness_session_id)
                        observed_harness_session_id = extracted_harness_session_id
                    except Exception:
                        logger.warning(
                            "Harness session ID observer failed.",
                            spawn_id=str(run.spawn_id),
                            harness_id=str(harness.id),
                            exc_info=True,
                        )
                if spawn_result.budget_breach is not None:
                    failure_reason = "budget_exceeded"
                    _append_budget_exceeded_event(
                        run=run,
                        breach=spawn_result.budget_breach,
                    )
                    break

                # Some harnesses emit usage only at the end. Recheck post-run with extracted usage.
                if (
                    budget_tracker is not None
                    and extracted.usage.total_cost_usd is not None
                    and budget_tracker.observe_cost(extracted.usage.total_cost_usd) is not None
                ):
                    failure_reason = "budget_exceeded"
                    breach = budget_tracker.check()
                    if breach is not None:
                        _append_budget_exceeded_event(run=run, breach=breach)
                    exit_code = DEFAULT_INFRA_EXIT_CODE
                    break

                if (
                    exit_code == 0
                    and _spawn_kind(state_root, run.spawn_id) == "child"
                    and extracted.report.content is None
                ):
                    # Child spawns must produce a report directly or via fallback extraction.
                    failure_reason = "missing_report"

                if extracted.output_is_empty:
                    if exit_code == 0:
                        # Successful exit with no content is unusable; fail fast
                        # so primary agents can react.
                        exit_code = 1
                        failure_reason = "empty_output"
                        break

                    if _artifact_is_zero_bytes(
                        artifacts=artifacts,
                        spawn_id=run.spawn_id,
                        filename=OUTPUT_FILENAME,
                    ) and _artifact_is_zero_bytes(
                        artifacts=artifacts,
                        spawn_id=run.spawn_id,
                        filename=STDERR_FILENAME,
                    ):
                        _write_structured_failure_artifact(
                            artifacts=artifacts,
                            spawn_id=run.spawn_id,
                            output_log_path=output_log_path,
                            exit_code=exit_code,
                            failure_reason=failure_reason,
                            timed_out=spawn_result.timed_out,
                        )

                if exit_code == 0:
                    guardrail_result = run_guardrails(
                        guardrails,
                        spawn_id=run.spawn_id,
                        cwd=execution_cwd,
                        env=child_env,
                        report_path=extracted.report_path,
                        output_log_path=output_log_path,
                        timeout_seconds=guardrail_timeout_seconds,
                    )
                    if guardrail_result.ok:
                        break

                    failure_reason = "guardrail_failed"
                    guardrail_text = _guardrail_failure_text(guardrail_result.failures)
                    _append_text_to_stderr_artifact(
                        artifacts=artifacts,
                        spawn_id=run.spawn_id,
                        text=guardrail_text,
                        secrets=secrets,
                    )

                    if retries_attempted >= max_retries:
                        exit_code = 1
                        break

                    retries_attempted += 1
                    exit_code = 1
                    logger.warning(
                        "Retrying after guardrail failure.",
                        spawn_id=str(run.spawn_id),
                        harness_id=str(harness.id),
                        retries_attempted=retries_attempted,
                        max_retries=max_retries,
                        guardrail_failures=[
                            f"{item.script}:{item.exit_code}" for item in guardrail_result.failures
                        ],
                    )
                    if retry_backoff_seconds > 0:
                        await asyncio.sleep(retry_backoff_seconds * retries_attempted)
                    continue

                stderr_key = make_artifact_key(run.spawn_id, STDERR_FILENAME)
                stderr_text = (
                    artifacts.get(stderr_key).decode("utf-8", errors="ignore")
                    if artifacts.exists(stderr_key)
                    else ""
                )
                category = classify_error(
                    exit_code,
                    stderr_text,
                    timed_out=spawn_result.timed_out,
                )
                if spawn_result.timed_out:
                    failure_reason = "timeout"
                elif category == ErrorCategory.STRATEGY_CHANGE:
                    failure_reason = "strategy_change"

                if not should_retry(
                    exit_code=exit_code,
                    stderr=stderr_text,
                    timed_out=spawn_result.timed_out,
                    retries_attempted=retries_attempted,
                    max_retries=max_retries,
                ):
                    break

                retries_attempted += 1
                logger.warning(
                    "Retrying failed run attempt.",
                    spawn_id=str(run.spawn_id),
                    harness_id=str(harness.id),
                    exit_code=exit_code,
                    retries_attempted=retries_attempted,
                    max_retries=max_retries,
                    error_category=str(category),
                )
                if retry_backoff_seconds > 0:
                    await asyncio.sleep(retry_backoff_seconds * retries_attempted)
        except asyncio.CancelledError:
            exit_code = 130
            failure_reason = "cancelled"
        except Exception:
            logger.exception(
                "Spawn execution failed with infrastructure error.",
                spawn_id=str(run.spawn_id),
                harness_id=str(harness.id),
            )
            exit_code = DEFAULT_INFRA_EXIT_CODE
        finally:
            duration_seconds = time.monotonic() - started_at
            finalized_usage = extracted.usage if extracted is not None else None
            durable_report_completion = extracted is not None and has_durable_report_completion(
                extracted.report.content
            )
            terminated_after_completion = terminated_after_completion or (
                durable_report_completion
                and not last_timed_out
                and (
                    _raw_return_code_matches_sigterm(last_raw_return_code)
                    or last_received_signal == signal.SIGTERM
                )
            )
            status, exit_code, failure_reason = resolve_execution_terminal_state(
                exit_code=exit_code,
                failure_reason=failure_reason,
                durable_report_completion=durable_report_completion,
                terminated_after_completion=terminated_after_completion,
            )
            with signal_coordinator().mask_sigterm():
                spawn_store.finalize_spawn(
                    state_root,
                    run.spawn_id,
                    status=status,
                    exit_code=exit_code,
                    duration_secs=duration_seconds,
                    total_cost_usd=(
                        finalized_usage.total_cost_usd if finalized_usage is not None else None
                    ),
                    input_tokens=finalized_usage.input_tokens
                    if finalized_usage is not None
                    else None,
                    output_tokens=(
                        finalized_usage.output_tokens if finalized_usage is not None else None
                    ),
                    error=failure_reason,
                )

    return exit_code
