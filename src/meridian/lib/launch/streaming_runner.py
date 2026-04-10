"""Bidirectional spawn execution with runner-owned finalization and retries."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

import structlog

from meridian.lib.config.settings import MeridianConfig
from meridian.lib.core.domain import Spawn
from meridian.lib.core.spawn_lifecycle import (
    has_durable_report_completion,
    resolve_execution_terminal_state,
)
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.adapter import SpawnParams, StreamEvent
from meridian.lib.harness.common import parse_json_stream_event, unwrap_event_payload
from meridian.lib.harness.connections.base import ConnectionConfig, HarnessConnection
from meridian.lib.harness.extractor import StreamingExtractor
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.launch.cwd import resolve_child_execution_cwd
from meridian.lib.launch.env import build_harness_child_env
from meridian.lib.launch.errors import ErrorCategory, classify_error, should_retry
from meridian.lib.launch.extract import (
    FinalizeExtraction,
    enrich_finalize,
    reset_finalize_attempt_artifacts,
)
from meridian.lib.launch.heartbeat import heartbeat_scope
from meridian.lib.launch.runner import ensure_claude_session_accessible
from meridian.lib.launch.session_ids import extract_latest_session_id
from meridian.lib.launch.signals import signal_coordinator, signal_to_exit_code
from meridian.lib.ops.spawn.plan import PreparedSpawnPlan
from meridian.lib.safety.budget import Budget, BudgetBreach, LiveBudgetTracker
from meridian.lib.safety.guardrails import GuardrailFailure, run_guardrails
from meridian.lib.safety.redaction import SecretSpec, redact_secret_bytes
from meridian.lib.state import spawn_store
from meridian.lib.state.artifact_store import ArtifactStore, make_artifact_key
from meridian.lib.state.atomic import atomic_write_bytes, atomic_write_text
from meridian.lib.state.paths import resolve_spawn_log_dir, resolve_state_paths
from meridian.lib.state.spawn_store import (
    BACKGROUND_LAUNCH_MODE,
    FOREGROUND_LAUNCH_MODE,
    mark_spawn_running,
)
from meridian.lib.streaming.spawn_manager import DrainOutcome, SpawnManager

if TYPE_CHECKING:
    from meridian.lib.harness.connections.base import HarnessEvent

OUTPUT_FILENAME = "output.jsonl"
STDERR_FILENAME = "stderr.log"
TOKENS_FILENAME = "tokens.json"
REPORT_FILENAME = "report.md"
DEFAULT_INFRA_EXIT_CODE = 2
REPORT_WATCHDOG_POLL_SECONDS = 1.0
REPORT_WATCHDOG_GRACE_SECONDS = 60.0
_DEFAULT_CONFIG = MeridianConfig()
DEFAULT_GUARDRAIL_TIMEOUT_SECONDS = _DEFAULT_CONFIG.guardrail_timeout_minutes * 60.0
logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class _AttemptRuntime:
    connection: HarnessConnection | None
    drain_exit_code: int
    timed_out: bool
    received_signal: signal.Signals | None
    budget_breach: BudgetBreach | None
    terminated_by_report_watchdog: bool
    start_error: str | None = None


def _spawn_kind(state_root: Path, spawn_id: SpawnId) -> str:
    row = spawn_store.get_spawn(state_root, spawn_id)
    if row is None:
        return "child"
    normalized = row.kind.strip().lower()
    if normalized in {"primary", "child"}:
        return normalized
    return "child"


def _dedupe_nonempty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for raw_value in values:
        value = raw_value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _split_csv_entries(value: str) -> list[str]:
    return [entry.strip() for entry in value.split(",") if entry.strip()]


def _read_parent_claude_permissions(execution_cwd: Path) -> tuple[list[str], list[str]]:
    additional_directories: list[str] = []
    allowed_tools: list[str] = []
    settings_dir = execution_cwd / ".claude"
    settings_files = (
        settings_dir / "settings.json",
        settings_dir / "settings.local.json",
    )
    for settings_path in settings_files:
        if not settings_path.exists():
            continue

        try:
            raw_payload = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "Failed to parse parent Claude settings while forwarding child permissions",
                path=str(settings_path),
            )
            continue

        if not isinstance(raw_payload, dict):
            continue
        payload = cast("dict[str, object]", raw_payload)
        raw_permissions = payload.get("permissions")
        if not isinstance(raw_permissions, dict):
            continue
        permissions = cast("dict[str, object]", raw_permissions)

        raw_additional_directories = permissions.get("additionalDirectories")
        if isinstance(raw_additional_directories, list):
            for directory in cast("list[object]", raw_additional_directories):
                if isinstance(directory, str):
                    additional_directories.append(directory)

        raw_allowed_tools = permissions.get("allow")
        if isinstance(raw_allowed_tools, list):
            for tool in cast("list[object]", raw_allowed_tools):
                if isinstance(tool, str):
                    allowed_tools.append(tool)

    return _dedupe_nonempty(additional_directories), _dedupe_nonempty(allowed_tools)


def _merge_allowed_tools_flag(
    command: tuple[str, ...], additional_allowed_tools: list[str]
) -> tuple[str, ...]:
    if not additional_allowed_tools:
        return command

    existing_allowed_tools: list[str] = []
    merged_command: list[str] = []
    index = 0

    while index < len(command):
        arg = command[index]
        if arg == "--allowedTools":
            if index + 1 < len(command):
                existing_allowed_tools.extend(_split_csv_entries(command[index + 1]))
                index += 2
                continue
            index += 1
            continue
        if arg.startswith("--allowedTools="):
            existing_allowed_tools.extend(_split_csv_entries(arg.split("=", 1)[1]))
            index += 1
            continue
        merged_command.append(arg)
        index += 1

    combined_allowed_tools = _dedupe_nonempty(
        existing_allowed_tools + additional_allowed_tools
    )
    if not combined_allowed_tools:
        return tuple(merged_command)
    merged_command.extend(("--allowedTools", ",".join(combined_allowed_tools)))
    return tuple(merged_command)


def _append_budget_exceeded_event(*, run: Spawn, breach: BudgetBreach) -> None:
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


def _install_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    shutdown_event: asyncio.Event,
    received_signal: list[signal.Signals | None],
) -> list[signal.Signals]:
    installed: list[signal.Signals] = []

    def _handle_signal(signum: signal.Signals) -> None:
        if received_signal[0] is None:
            received_signal[0] = signum
        shutdown_event.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(signum, _handle_signal, signum)
            installed.append(signum)
        except (NotImplementedError, RuntimeError):
            continue
    return installed


def _remove_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    installed: Iterable[signal.Signals],
) -> None:
    for signum in installed:
        with suppress(Exception):
            loop.remove_signal_handler(signum)


def _truncate_attempt_logs(log_dir: Path) -> None:
    for name in (
        OUTPUT_FILENAME,
        STDERR_FILENAME,
        TOKENS_FILENAME,
        REPORT_FILENAME,
        "harness.pid",
    ):
        target = log_dir / name
        if target.exists():
            target.unlink()


def _persist_attempt_artifacts(
    *,
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    log_dir: Path,
    secrets: tuple[SecretSpec, ...],
) -> None:
    for name in (OUTPUT_FILENAME, STDERR_FILENAME, TOKENS_FILENAME):
        source = log_dir / name
        if not source.exists():
            continue
        payload = source.read_bytes()
        if name in {OUTPUT_FILENAME, STDERR_FILENAME}:
            payload = redact_secret_bytes(payload, secrets)
        artifacts.put(make_artifact_key(spawn_id, name), payload)


def _line_from_harness_event(event: HarnessEvent) -> str:
    if event.raw_text is not None and event.raw_text.strip():
        return event.raw_text
    payload: dict[str, object] = dict(event.payload)
    payload.setdefault("event", event.event_type)
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _observe_budget_from_event(
    *,
    budget_tracker: LiveBudgetTracker | None,
    event: HarnessEvent,
) -> BudgetBreach | None:
    if budget_tracker is None:
        return None

    payload = unwrap_event_payload(event.payload)
    try:
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return budget_tracker.observe_json_line(encoded)


def _emit_stream_event(
    *,
    line: str,
    event_observer: Callable[[StreamEvent], None] | None,
    stream_stdout_to_terminal: bool,
) -> None:
    parsed = parse_json_stream_event(line)
    if parsed is None:
        return

    if event_observer is not None:
        try:
            event_observer(parsed)
        except Exception:
            logger.warning("Stream event observer failed.", exc_info=True)

    if not stream_stdout_to_terminal:
        return

    rendered = parsed.text.strip() if parsed.text is not None else parsed.raw_line.strip()
    if not rendered:
        return
    sys.stderr.write(f"{rendered}\n")
    sys.stderr.flush()


async def _consume_subscriber_events(
    *,
    subscriber: asyncio.Queue[HarnessEvent | None],
    budget_tracker: LiveBudgetTracker | None,
    budget_signal: asyncio.Event,
    budget_breach_holder: list[BudgetBreach | None],
    event_observer: Callable[[StreamEvent], None] | None,
    stream_stdout_to_terminal: bool,
) -> None:
    while True:
        event = await subscriber.get()
        if event is None:
            return

        if budget_breach_holder[0] is None:
            breach = _observe_budget_from_event(
                budget_tracker=budget_tracker,
                event=event,
            )
            if breach is not None:
                budget_breach_holder[0] = breach
                budget_signal.set()

        if event_observer is not None or stream_stdout_to_terminal:
            line = _line_from_harness_event(event)
            _emit_stream_event(
                line=line,
                event_observer=event_observer,
                stream_stdout_to_terminal=stream_stdout_to_terminal,
            )


async def _report_watchdog(
    *,
    report_path: Path,
    completion_event: asyncio.Event,
    manager: SpawnManager,
    spawn_id: SpawnId,
    grace_seconds: float = REPORT_WATCHDOG_GRACE_SECONDS,
) -> bool:
    while not report_path.exists():
        if completion_event.is_set():
            return False
        await asyncio.sleep(REPORT_WATCHDOG_POLL_SECONDS)

    deadline = asyncio.get_running_loop().time() + grace_seconds
    while asyncio.get_running_loop().time() < deadline:
        if completion_event.is_set():
            return False
        await asyncio.sleep(REPORT_WATCHDOG_POLL_SECONDS)

    if completion_event.is_set():
        return False

    await manager.stop_spawn(spawn_id, status="cancelled", exit_code=1, error="report_watchdog")
    logger.info(
        "Report watchdog stopped active streaming connection after grace timeout.",
        spawn_id=str(spawn_id),
        grace_seconds=grace_seconds,
    )
    return True


async def run_streaming_spawn(
    *,
    config: ConnectionConfig,
    params: SpawnParams,
    state_root: Path,
    repo_root: Path,
    spawn_id: SpawnId,
    stream_to_terminal: bool = False,
) -> DrainOutcome:
    """Run one streaming spawn to completion without spawn-store finalization."""

    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    heartbeat_path = state_root / "spawns" / str(spawn_id) / "heartbeat"

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    received_signal: list[signal.Signals | None] = [None]
    installed_signals = _install_signal_handlers(loop, shutdown_event, received_signal)

    completion_task: asyncio.Task[DrainOutcome | None] | None = None
    signal_task: asyncio.Task[bool] | None = None
    consume_task: asyncio.Task[None] | None = None
    subscriber: asyncio.Queue[HarnessEvent | None] | None = None
    try:
        async with heartbeat_scope(heartbeat_path):
            connection = await manager.start_spawn(config, params)
            if connection.subprocess_pid is not None:
                atomic_write_text(
                    state_root / "spawns" / str(spawn_id) / "harness.pid",
                    f"{connection.subprocess_pid}\n",
                )

            subscriber = manager.subscribe(spawn_id)
            if subscriber is None:
                raise RuntimeError("failed to subscribe to spawn stream")

            completion_task = asyncio.create_task(manager.wait_for_completion(spawn_id))
            consume_task = asyncio.create_task(
                _consume_subscriber_events(
                    subscriber=subscriber,
                    budget_tracker=None,
                    budget_signal=asyncio.Event(),
                    budget_breach_holder=[None],
                    event_observer=None,
                    stream_stdout_to_terminal=stream_to_terminal,
                )
            )
            signal_task = asyncio.create_task(shutdown_event.wait())

            done, _ = await asyncio.wait(
                {
                    cast("asyncio.Task[object]", completion_task),
                    cast("asyncio.Task[object]", signal_task),
                },
                return_when=asyncio.FIRST_COMPLETED,
            )
            if signal_task in done and shutdown_event.is_set():
                signal_exit = signal_to_exit_code(received_signal[0]) or 130
                await manager.stop_spawn(
                    spawn_id,
                    status="cancelled",
                    exit_code=signal_exit,
                    error="cancelled",
                )

            outcome = await completion_task
            if outcome is None:
                raise RuntimeError("streaming spawn completed without drain outcome")
            return outcome
    finally:
        if subscriber is not None:
            manager.unsubscribe(spawn_id)
        for task in (completion_task, signal_task, consume_task):
            if task is not None and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        _remove_signal_handlers(loop, installed_signals)
        with suppress(Exception):
            await manager.shutdown(status="cancelled", exit_code=1, error="shutdown")


async def _run_streaming_attempt(
    *,
    run: Spawn,
    state_root: Path,
    launch_mode: spawn_store.LaunchMode,
    log_dir: Path,
    manager: SpawnManager,
    config: ConnectionConfig,
    run_params: SpawnParams,
    budget_tracker: LiveBudgetTracker | None,
    signal_event: asyncio.Event,
    received_signal: list[signal.Signals | None],
    timeout_seconds: float | None,
    event_observer: Callable[[StreamEvent], None] | None,
    stream_stdout_to_terminal: bool,
) -> _AttemptRuntime:
    completion_task: asyncio.Task[DrainOutcome | None] | None = None
    timeout_task: asyncio.Task[None] | None = None
    signal_task: asyncio.Task[bool] | None = None
    budget_task: asyncio.Task[bool] | None = None
    watchdog_task: asyncio.Task[bool] | None = None
    consume_task: asyncio.Task[None] | None = None
    completion_event = asyncio.Event()
    budget_signal = asyncio.Event()
    budget_breach_holder: list[BudgetBreach | None] = [None]
    subscriber: asyncio.Queue[HarnessEvent | None] | None = None
    connection: HarnessConnection | None = None
    drain_exit_code = DEFAULT_INFRA_EXIT_CODE
    timed_out = False
    terminated_by_report_watchdog = False

    try:
        connection = await manager.start_spawn(config, run_params)
        if connection.subprocess_pid is not None:
            atomic_write_text(log_dir / "harness.pid", f"{connection.subprocess_pid}\n")
        mark_spawn_running(
            state_root,
            run.spawn_id,
            launch_mode=launch_mode,
            worker_pid=connection.subprocess_pid,
        )

        subscriber = manager.subscribe(run.spawn_id)
        if subscriber is None:
            raise RuntimeError("failed to subscribe to spawn stream")

        completion_task = asyncio.create_task(manager.wait_for_completion(run.spawn_id))
        completion_task.add_done_callback(lambda _: completion_event.set())
        consume_task = asyncio.create_task(
            _consume_subscriber_events(
                subscriber=subscriber,
                budget_tracker=budget_tracker,
                budget_signal=budget_signal,
                budget_breach_holder=budget_breach_holder,
                event_observer=event_observer,
                stream_stdout_to_terminal=stream_stdout_to_terminal,
            )
        )
        signal_task = asyncio.create_task(signal_event.wait())
        if budget_tracker is not None:
            budget_task = asyncio.create_task(budget_signal.wait())
        if timeout_seconds is not None and timeout_seconds > 0:
            timeout_task = asyncio.create_task(asyncio.sleep(timeout_seconds))
        watchdog_task = asyncio.create_task(
            _report_watchdog(
                report_path=log_dir / REPORT_FILENAME,
                completion_event=completion_event,
                manager=manager,
                spawn_id=run.spawn_id,
            )
        )

        wait_tasks: set[asyncio.Task[object]] = {
            cast("asyncio.Task[object]", completion_task),
            cast("asyncio.Task[object]", signal_task),
            cast("asyncio.Task[object]", watchdog_task),
        }
        if budget_task is not None:
            wait_tasks.add(cast("asyncio.Task[object]", budget_task))
        if timeout_task is not None:
            wait_tasks.add(cast("asyncio.Task[object]", timeout_task))

        done, _ = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)
        if signal_task in done and signal_event.is_set():
            signal_exit = signal_to_exit_code(received_signal[0]) or 130
            await manager.stop_spawn(
                run.spawn_id,
                status="cancelled",
                exit_code=signal_exit,
                error="cancelled",
            )
            drain_exit_code = signal_exit
        elif budget_task is not None and budget_task in done and budget_signal.is_set():
            await manager.stop_spawn(
                run.spawn_id,
                status="failed",
                exit_code=DEFAULT_INFRA_EXIT_CODE,
                error="budget_exceeded",
            )
            drain_exit_code = DEFAULT_INFRA_EXIT_CODE
        elif timeout_task is not None and timeout_task in done:
            timed_out = True
            await manager.stop_spawn(
                run.spawn_id,
                status="failed",
                exit_code=3,
                error="timeout",
            )
            drain_exit_code = 3
        elif watchdog_task in done:
            terminated_by_report_watchdog = bool(watchdog_task.result())

        drain_outcome = await completion_task
        if drain_outcome is not None:
            drain_exit_code = drain_outcome.exit_code
    except Exception as exc:
        return _AttemptRuntime(
            connection=connection,
            drain_exit_code=DEFAULT_INFRA_EXIT_CODE,
            timed_out=False,
            received_signal=received_signal[0],
            budget_breach=budget_breach_holder[0],
            terminated_by_report_watchdog=terminated_by_report_watchdog,
            start_error=str(exc),
        )
    finally:
        if subscriber is not None:
            manager.unsubscribe(run.spawn_id)
        for task in (timeout_task, signal_task, budget_task, watchdog_task, consume_task):
            if task is not None and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        if manager.get_connection(run.spawn_id) is not None:
            with suppress(Exception):
                await manager.stop_spawn(run.spawn_id)

    return _AttemptRuntime(
        connection=connection,
        drain_exit_code=drain_exit_code,
        timed_out=timed_out,
        received_signal=received_signal[0],
        budget_breach=budget_breach_holder[0],
        terminated_by_report_watchdog=terminated_by_report_watchdog,
    )


async def execute_with_streaming(
    run: Spawn,
    *,
    plan: PreparedSpawnPlan,
    repo_root: Path,
    state_root: Path,
    artifacts: ArtifactStore,
    registry: HarnessRegistry,
    cwd: Path | None = None,
    env_overrides: dict[str, str] | None = None,
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
    """Execute one streaming spawn and always finalize the spawn row."""

    _ = stream_stderr_to_terminal
    execution_cwd = (cwd or Path.cwd()).resolve()
    log_dir = resolve_spawn_log_dir(repo_root, run.spawn_id)
    output_log_path = log_dir / OUTPUT_FILENAME
    report_path = log_dir / REPORT_FILENAME
    heartbeat_path = log_dir / "heartbeat"

    resolved_harness_id = HarnessId(plan.harness_id)
    harness = registry.get_subprocess_harness(resolved_harness_id)

    timeout_seconds = plan.execution.timeout_secs
    max_retries = plan.execution.max_retries
    retry_backoff_seconds = plan.execution.retry_backoff_secs

    child_cwd = execution_cwd
    passthrough_args = tuple(plan.passthrough_args)
    resolved_cwd = resolve_child_execution_cwd(
        repo_root=execution_cwd,
        spawn_id=run.spawn_id,
        harness_id=harness.id.value,
    )
    if resolved_cwd != execution_cwd:
        child_cwd = resolved_cwd
        child_cwd.mkdir(parents=True, exist_ok=True)
        if harness.id == HarnessId.CLAUDE:
            expanded_args = [*passthrough_args, "--add-dir", str(execution_cwd)]
            parent_additional_directories, parent_allowed_tools = (
                _read_parent_claude_permissions(execution_cwd)
            )
            for additional_directory in parent_additional_directories:
                expanded_args.extend(("--add-dir", additional_directory))
            passthrough_args = _merge_allowed_tools_flag(
                tuple(expanded_args), parent_allowed_tools
            )

    spawn_store.update_spawn(
        state_root,
        run.spawn_id,
        execution_cwd=str(child_cwd),
    )

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

    run_params = SpawnParams(
        prompt=run.prompt,
        model=run.model if str(run.model).strip() else None,
        skills=plan.skills,
        agent=plan.agent_name,
        adhoc_agent_payload=plan.adhoc_agent_payload,
        extra_args=passthrough_args,
        repo_root=child_cwd.as_posix(),
        mcp_tools=plan.mcp_tools,
        continue_harness_session_id=plan.session.harness_session_id,
        continue_fork=plan.session.continue_fork,
        report_output_path=report_path.as_posix(),
        appended_system_prompt=plan.appended_system_prompt,
    )

    runtime_env_overrides = {
        "MERIDIAN_REPO_ROOT": execution_cwd.as_posix(),
        "MERIDIAN_STATE_ROOT": resolve_state_paths(repo_root).root_dir.resolve().as_posix(),
    }
    merged_env_overrides = dict(env_overrides or {})
    merged_env_overrides.update(runtime_env_overrides)
    child_env = build_harness_child_env(
        base_env=os.environ,
        adapter=harness,
        run_params=run_params,
        permission_config=plan.execution.permission_config,
        runtime_env_overrides=merged_env_overrides,
    )
    config = ConnectionConfig(
        spawn_id=run.spawn_id,
        harness_id=resolved_harness_id,
        model=(str(run.model).strip() or None),
        prompt=run.prompt,
        repo_root=child_cwd,
        env_overrides=child_env,
        timeout_seconds=timeout_seconds,
    )

    spawn_row = spawn_store.get_spawn(state_root, run.spawn_id)
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
        spawn_row = spawn_store.get_spawn(state_root, run.spawn_id)
    raw_launch_mode = (
        (spawn_row.launch_mode or "").strip().lower()
        if spawn_row is not None and spawn_row.launch_mode is not None
        else FOREGROUND_LAUNCH_MODE
    )
    resolved_launch_mode: spawn_store.LaunchMode = (
        BACKGROUND_LAUNCH_MODE
        if raw_launch_mode == BACKGROUND_LAUNCH_MODE
        else FOREGROUND_LAUNCH_MODE
    )

    materialized_session_id = (run_params.continue_harness_session_id or "").strip()
    observed_harness_session_id: str | None = None
    if (
        materialized_session_id
        and materialized_session_id != (plan.session.harness_session_id or "")
    ):
        spawn_store.update_spawn(
            state_root,
            run.spawn_id,
            harness_session_id=materialized_session_id,
        )
        observed_harness_session_id = materialized_session_id
        if harness_session_id_observer is not None:
            harness_session_id_observer(materialized_session_id)

    budget_tracker = (
        LiveBudgetTracker(budget=budget, space_spent_usd=space_spent_usd)
        if budget is not None
        else None
    )
    preflight_breach = budget_tracker.check() if budget_tracker is not None else None
    manager = SpawnManager(state_root=state_root, repo_root=repo_root)
    retries_attempted = 0
    started_at = time.monotonic()
    started_at_epoch = time.time()
    exit_code = DEFAULT_INFRA_EXIT_CODE
    extracted: FinalizeExtraction | None = None
    failure_reason: str | None = None
    terminated_after_completion = False

    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()
    received_signal: list[signal.Signals | None] = [None]
    installed_signals = _install_signal_handlers(loop, shutdown_event, received_signal)

    async with heartbeat_scope(heartbeat_path):
        try:
            while True:
                reset_finalize_attempt_artifacts(
                    artifacts=artifacts,
                    spawn_id=run.spawn_id,
                    log_dir=log_dir,
                )
                _truncate_attempt_logs(log_dir)

                if preflight_breach is not None:
                    exit_code = DEFAULT_INFRA_EXIT_CODE
                    failure_reason = "budget_exceeded"
                    _append_budget_exceeded_event(run=run, breach=preflight_breach)
                    break

                attempt = await _run_streaming_attempt(
                    run=run,
                    state_root=state_root,
                    launch_mode=resolved_launch_mode,
                    log_dir=log_dir,
                    manager=manager,
                    config=config,
                    run_params=run_params,
                    budget_tracker=budget_tracker,
                    signal_event=shutdown_event,
                    received_signal=received_signal,
                    timeout_seconds=timeout_seconds,
                    event_observer=event_observer,
                    stream_stdout_to_terminal=stream_stdout_to_terminal,
                )
                exit_code = attempt.drain_exit_code
                terminated_after_completion = (
                    terminated_after_completion or attempt.terminated_by_report_watchdog
                )
                if attempt.start_error is not None:
                    logger.warning(
                        "Failed to execute streaming spawn attempt.",
                        spawn_id=str(run.spawn_id),
                        harness_id=str(harness.id),
                        error=attempt.start_error,
                    )
                    failure_reason = "infrastructure_error"
                    _append_text_to_stderr_artifact(
                        artifacts=artifacts,
                        spawn_id=run.spawn_id,
                        text=attempt.start_error,
                        secrets=secrets,
                    )
                if attempt.timed_out:
                    failure_reason = "timeout"
                if attempt.received_signal == signal.SIGINT:
                    failure_reason = "cancelled"
                elif attempt.received_signal == signal.SIGTERM and failure_reason is None:
                    failure_reason = "terminated"

                _persist_attempt_artifacts(
                    artifacts=artifacts,
                    spawn_id=run.spawn_id,
                    log_dir=log_dir,
                    secrets=secrets,
                )
                if report_path.exists():
                    redacted_report = redact_secret_bytes(report_path.read_bytes(), secrets)
                    atomic_write_bytes(report_path, redacted_report)
                    artifacts.put(make_artifact_key(run.spawn_id, REPORT_FILENAME), redacted_report)

                streaming_extractor = StreamingExtractor(
                    connection=attempt.connection,
                    harness_id=resolved_harness_id,
                )
                extracted = enrich_finalize(
                    artifacts=artifacts,
                    extractor=streaming_extractor,
                    spawn_id=run.spawn_id,
                    log_dir=log_dir,
                    secrets=secrets,
                )

                extracted_harness_session_id = (
                    extract_latest_session_id(
                        extractor=streaming_extractor,
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
                        observed_harness_session_id = extracted_harness_session_id
                        if harness_session_id_observer is not None:
                            harness_session_id_observer(extracted_harness_session_id)
                    except Exception:
                        logger.warning(
                            "Harness session ID observer failed.",
                            spawn_id=str(run.spawn_id),
                            harness_id=str(harness.id),
                            exc_info=True,
                        )

                if attempt.budget_breach is not None:
                    failure_reason = "budget_exceeded"
                    exit_code = DEFAULT_INFRA_EXIT_CODE
                    _append_budget_exceeded_event(run=run, breach=attempt.budget_breach)
                    break

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
                    failure_reason = "missing_report"

                if extracted.output_is_empty:
                    if exit_code == 0:
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
                            timed_out=attempt.timed_out,
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
                    timed_out=attempt.timed_out,
                )
                if attempt.timed_out:
                    failure_reason = "timeout"
                elif category == ErrorCategory.STRATEGY_CHANGE:
                    failure_reason = "strategy_change"

                if not should_retry(
                    exit_code=exit_code,
                    stderr=stderr_text,
                    timed_out=attempt.timed_out,
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
                "Streaming spawn execution failed with infrastructure error.",
                spawn_id=str(run.spawn_id),
                harness_id=str(harness.id),
            )
            exit_code = DEFAULT_INFRA_EXIT_CODE
            failure_reason = "infrastructure_error"
        finally:
            _remove_signal_handlers(loop, installed_signals)
            with suppress(Exception):
                await manager.shutdown(status="cancelled", exit_code=1, error="shutdown")
            duration_seconds = time.monotonic() - started_at
            finalized_usage = extracted.usage if extracted is not None else None
            durable_report_completion = extracted is not None and has_durable_report_completion(
                extracted.report.content
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


__all__ = [
    "DEFAULT_GUARDRAIL_TIMEOUT_SECONDS",
    "execute_with_streaming",
    "run_streaming_spawn",
]
