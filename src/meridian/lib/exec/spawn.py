"""Async subprocess execution and finalization guarantees."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import structlog

from meridian.lib.config.settings import MeridianConfig
from meridian.lib.domain import Spawn
from meridian.lib.exec.errors import ErrorCategory, classify_error, should_retry
from meridian.lib.exec.process_groups import signal_process_group
from meridian.lib.exec.signals import SignalForwarder, map_process_exit_code, signal_coordinator
from meridian.lib.exec.timeout import (
    DEFAULT_KILL_GRACE_SECONDS,
    SpawnTimeoutError,
    terminate_process,
    wait_for_process_exit,
)
from meridian.lib.extract.finalize import (
    FinalizeExtraction,
    enrich_finalize,
    reset_finalize_attempt_artifacts,
)
from meridian.lib.harness.adapter import (
    PermissionResolver,
    SpawnParams,
    StreamEvent,
    resolve_mcp_config,
)
from meridian.lib.harness.registry import HarnessRegistry
from meridian.lib.safety.budget import Budget, BudgetBreach, LiveBudgetTracker
from meridian.lib.safety.guardrails import GuardrailFailure, run_guardrails
from meridian.lib.safety.permissions import PermissionConfig
from meridian.lib.safety.redaction import SecretSpec, redact_secret_bytes
from meridian.lib.state.artifact_store import ArtifactStore, make_artifact_key
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_spawn_log_dir, resolve_state_paths
from meridian.lib.types import HarnessId, SpawnId, SpaceId

OUTPUT_FILENAME = "output.jsonl"
STDERR_FILENAME = "stderr.log"
TOKENS_FILENAME = "tokens.json"
REPORT_FILENAME = "report.md"
DEFAULT_INFRA_EXIT_CODE = 2
_DEFAULT_CONFIG = MeridianConfig()
DEFAULT_MAX_RETRIES = _DEFAULT_CONFIG.max_retries
DEFAULT_RETRY_BACKOFF_SECONDS = _DEFAULT_CONFIG.retry_backoff_seconds
DEFAULT_GUARDRAIL_TIMEOUT_SECONDS = _DEFAULT_CONFIG.guardrail_timeout_seconds
logger = structlog.get_logger(__name__)

_CHILD_ENV_ALLOWLIST = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "LANG",
        "TERM",
        "TMPDIR",
        "PYTHONPATH",
        "VIRTUAL_ENV",
    }
)
_CHILD_ENV_ALLOWLIST_PREFIXES = ("LC_", "XDG_", "UV_")
_CHILD_ENV_SECRET_SUFFIXES = ("_TOKEN", "_KEY", "_SECRET")
# Harness CLIs need these credentials to authenticate. Keep this explicit so
# secret-like env vars still default to redacted unless intentionally allowed.
HARNESS_ENV_PASS_THROUGH = frozenset(
    {
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_ORG_ID",
        "OPENAI_PROJECT_ID",
        "OPENAI_BASE_URL",
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GROQ_API_KEY",
        "XAI_API_KEY",
        "MISTRAL_API_KEY",
        "COHERE_API_KEY",
        "DEEPSEEK_API_KEY",
        "TOGETHER_API_KEY",
        "PERPLEXITY_API_KEY",
    }
)


def _is_allowlisted_child_env_var(key: str) -> bool:
    normalized = key.upper()
    if normalized in _CHILD_ENV_ALLOWLIST:
        return True
    return any(normalized.startswith(prefix) for prefix in _CHILD_ENV_ALLOWLIST_PREFIXES)


def _looks_like_secret_env_var(key: str) -> bool:
    normalized = key.upper()
    return any(normalized.endswith(suffix) for suffix in _CHILD_ENV_SECRET_SUFFIXES)


def sanitize_child_env(
    base_env: Mapping[str, str],
    env_overrides: Mapping[str, str] | None,
    pass_through: Collection[str],
) -> dict[str, str]:
    """Return a sanitized child environment with explicit pass-through controls."""

    pass_through_keys = {name.upper() for name in pass_through}
    sanitized: dict[str, str] = {}

    for key, value in base_env.items():
        normalized = key.upper()
        if _looks_like_secret_env_var(normalized) and normalized not in pass_through_keys:
            continue
        if normalized in pass_through_keys or _is_allowlisted_child_env_var(normalized):
            sanitized[key] = value

    if env_overrides is not None:
        sanitized.update(env_overrides)

    return sanitized


class SafeDefaultPermissionResolver(PermissionResolver):
    """Safe default resolver for run execution."""

    def resolve_flags(self, harness_id: HarnessId) -> list[str]:
        _ = harness_id
        return []


@dataclass(frozen=True, slots=True)
class SpawnResult:
    """Result from one spawned harness process."""

    exit_code: int
    raw_return_code: int
    timed_out: bool
    received_signal: signal.Signals | None
    output_log_path: Path
    stderr_log_path: Path
    budget_breach: BudgetBreach | None = None


def run_log_dir(repo_root: Path, spawn_id: SpawnId, space_id: SpaceId | None) -> Path:
    """Resolve run artifact directory from run/space IDs."""

    return resolve_spawn_log_dir(repo_root, spawn_id, space_id)


def _extract_tokens_payload(raw_line: bytes) -> bytes | None:
    try:
        payload_obj = json.loads(raw_line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload_obj, dict):
        return None

    payload = cast("dict[str, object]", payload_obj)
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        return None
    return json.dumps(tokens, sort_keys=True).encode("utf-8")


async def _capture_stdout(
    reader: asyncio.StreamReader,
    output_file: Path,
    *,
    secrets: tuple[SecretSpec, ...],
    line_observer: Callable[[bytes], None] | None,
    parse_stream_event: Callable[[str], StreamEvent | None] | None = None,
    event_observer: Callable[[StreamEvent], None] | None = None,
    stream_to_terminal: bool = False,
) -> tuple[bytes, bytes | None]:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    buffer = bytearray()
    last_tokens_payload: bytes | None = None
    with output_file.open("wb") as handle:
        while True:
            chunk = await reader.readline()
            if not chunk:
                break

            redacted_chunk = redact_secret_bytes(chunk, secrets)
            if line_observer is not None:
                line_observer(redacted_chunk)

            line_text = redacted_chunk.decode("utf-8", errors="replace")
            if parse_stream_event is not None and event_observer is not None:
                try:
                    parsed_event = parse_stream_event(line_text)
                except Exception:
                    logger.warning("Failed to parse harness stream event.", exc_info=True)
                else:
                    if parsed_event is not None:
                        try:
                            event_observer(parsed_event)
                        except Exception:
                            logger.warning("Stream event observer failed.", exc_info=True)

            if stream_to_terminal:
                sys.stderr.write(line_text)
                sys.stderr.flush()

            parsed_tokens = _extract_tokens_payload(chunk)
            if parsed_tokens is not None:
                last_tokens_payload = redact_secret_bytes(parsed_tokens, secrets)

            handle.write(redacted_chunk)
            handle.flush()
            buffer.extend(redacted_chunk)

    return bytes(buffer), last_tokens_payload


async def _capture_stderr(
    reader: asyncio.StreamReader,
    stderr_file: Path,
    *,
    secrets: tuple[SecretSpec, ...],
    stream_to_terminal: bool = False,
) -> bytes:
    stderr_file.parent.mkdir(parents=True, exist_ok=True)
    buffer = bytearray()
    with stderr_file.open("wb") as handle:
        while True:
            chunk = await reader.readline()
            if not chunk:
                break
            redacted_chunk = redact_secret_bytes(chunk, secrets)
            handle.write(redacted_chunk)
            handle.flush()
            buffer.extend(redacted_chunk)
            if stream_to_terminal:
                sys.stderr.write(redacted_chunk.decode("utf-8", errors="replace"))
                sys.stderr.flush()
    return bytes(buffer)


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
        await asyncio.wait_for(process.wait(), timeout=kill_grace_seconds)
    except TimeoutError:
        if process.returncode is None:
            signal_process_group(process, signal.SIGKILL)
            await process.wait()


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

    stdout_task = asyncio.create_task(
        _capture_stdout(
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
        _capture_stderr(
            process.stderr,
            stderr_log_path,
            secrets=secrets,
            stream_to_terminal=stream_stderr_to_terminal,
        )
    )
    stdin_task: asyncio.Task[None] | None = None
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
                try:
                    await process.stdin.wait_closed()
                except (BrokenPipeError, ConnectionResetError):
                    pass

        stdin_task = asyncio.create_task(_feed_stdin())

    received_signal: signal.Signals | None = None
    timed_out = False
    raw_return_code = DEFAULT_INFRA_EXIT_CODE
    try:
        with SignalForwarder(process) as forwarder:
            try:
                raw_return_code = await wait_for_process_exit(
                    process,
                    timeout_seconds=timeout_seconds,
                    kill_grace_seconds=kill_grace_seconds,
                )
            except SpawnTimeoutError:
                timed_out = True
                raw_return_code = process.returncode if process.returncode is not None else 1
            received_signal = forwarder.received_signal
    except asyncio.CancelledError:
        await _terminate_after_cancellation(process, kill_grace_seconds=kill_grace_seconds)
        raise
    finally:
        if stdin_task is not None:
            await stdin_task
        if budget_termination_task is not None:
            await budget_termination_task

        stdout_bytes, tokens_payload = await stdout_task
        stderr_bytes = await stderr_task

        artifacts.put(make_artifact_key(spawn_id, OUTPUT_FILENAME), stdout_bytes)
        artifacts.put(make_artifact_key(spawn_id, STDERR_FILENAME), stderr_bytes)
        if tokens_payload is not None:
            artifacts.put(make_artifact_key(spawn_id, TOKENS_FILENAME), tokens_payload)

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


def _spawn_kind(space_dir: Path, spawn_id: SpawnId) -> str:
    row = spawn_store.get_spawn(space_dir, spawn_id)
    if row is None:
        return "child"
    normalized = row.kind.strip().lower()
    if normalized in {"primary", "child"}:
        return normalized
    return "child"


async def execute_with_finalization(
    run: Spawn,
    *,
    repo_root: Path,
    space_dir: Path,
    artifacts: ArtifactStore,
    registry: HarnessRegistry,
    permission_resolver: PermissionResolver | None = None,
    permission_config: PermissionConfig | None = None,
    cwd: Path | None = None,
    timeout_seconds: float | None = None,
    kill_grace_seconds: float = DEFAULT_KILL_GRACE_SECONDS,
    skills: tuple[str, ...] = (),
    agent: str | None = None,
    mcp_tools: tuple[str, ...] = (),
    extra_args: tuple[str, ...] = (),
    env_overrides: dict[str, str] | None = None,
    harness_id: HarnessId | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
    budget: Budget | None = None,
    space_spent_usd: float = 0.0,
    guardrails: tuple[Path, ...] = (),
    guardrail_timeout_seconds: float = DEFAULT_GUARDRAIL_TIMEOUT_SECONDS,
    secrets: tuple[SecretSpec, ...] = (),
    continue_harness_session_id: str | None = None,
    continue_fork: bool = False,
    harness_session_id_observer: Callable[[str], None] | None = None,
    event_observer: Callable[[StreamEvent], None] | None = None,
    stream_stdout_to_terminal: bool = False,
    stream_stderr_to_terminal: bool = False,
) -> int:
    """Execute one run and always append a finalize row via try/finally."""

    execution_cwd = (cwd or Path.cwd()).resolve()
    log_dir = resolve_spawn_log_dir(repo_root, run.spawn_id, run.space_id)
    output_log_path = log_dir / OUTPUT_FILENAME
    report_path = log_dir / REPORT_FILENAME

    if harness_id is None:
        harness, _warning = registry.route(str(run.model))
    else:
        harness = registry.get(harness_id)

    run_params = SpawnParams(
        prompt=run.prompt,
        model=run.model,
        skills=skills,
        agent=agent,
        extra_args=extra_args,
        repo_root=execution_cwd.as_posix(),
        mcp_tools=mcp_tools,
        continue_harness_session_id=continue_harness_session_id,
        continue_fork=continue_fork,
    )
    prompt_stdin = run.prompt if harness.capabilities.supports_stdin_prompt else None

    resolved_perms = permission_resolver or SafeDefaultPermissionResolver()
    resolved_permission_config = permission_config or PermissionConfig()
    adapter_env_overrides = harness.env_overrides(resolved_permission_config)
    mcp_config = resolve_mcp_config(harness, run_params)
    if mcp_config is not None:
        adapter_env_overrides.update(mcp_config.env_overrides)
    runtime_env_overrides = {
        "MERIDIAN_REPO_ROOT": execution_cwd.as_posix(),
        "MERIDIAN_STATE_ROOT": resolve_state_paths(repo_root).root_dir.resolve().as_posix(),
    }
    merged_env_overrides = dict(env_overrides or {})
    merged_env_overrides.update(runtime_env_overrides)
    merged_env_overrides.update(adapter_env_overrides)
    child_env = sanitize_child_env(
        base_env=os.environ,
        env_overrides=merged_env_overrides,
        pass_through=HARNESS_ENV_PASS_THROUGH,
    )
    if spawn_store.get_spawn(space_dir, run.spawn_id) is None:
        spawn_store.start_spawn(
            space_dir,
            spawn_id=run.spawn_id,
            chat_id=os.getenv("MERIDIAN_CHAT_ID", "").strip() or "c0",
            model=str(run.model),
            agent=agent or "",
            harness=str(harness.id),
            kind="child",
            prompt=run.prompt,
            harness_session_id=continue_harness_session_id,
        )

    budget_tracker = (
        LiveBudgetTracker(budget=budget, space_spent_usd=space_spent_usd)
        if budget is not None
        else None
    )
    preflight_breach = budget_tracker.check() if budget_tracker is not None else None

    started_at = time.monotonic()
    exit_code = DEFAULT_INFRA_EXIT_CODE
    extracted: FinalizeExtraction | None = None
    failure_reason: str | None = None
    observed_harness_session_id: str | None = None

    try:
        command = tuple(harness.build_command(run_params, resolved_perms))
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
                cwd=execution_cwd,
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
                    harness.parse_stream_event
                    if harness.capabilities.supports_stream_events
                    else None
                ),
                event_observer=event_observer,
                stream_stdout_to_terminal=stream_stdout_to_terminal,
                stream_stderr_to_terminal=stream_stderr_to_terminal,
            )
            exit_code = spawn_result.exit_code

            if report_path.exists():
                redacted_report = redact_secret_bytes(report_path.read_bytes(), secrets)
                report_path.write_bytes(redacted_report)
                artifacts.put(
                    make_artifact_key(run.spawn_id, REPORT_FILENAME),
                    redacted_report,
                )

            extracted = enrich_finalize(
                artifacts=artifacts,
                adapter=harness,
                spawn_id=run.spawn_id,
                log_dir=log_dir,
                secrets=secrets,
            )
            extracted_harness_session_id = (
                extracted.harness_session_id.strip()
                if extracted.harness_session_id is not None
                else ""
            )
            if (
                extracted_harness_session_id
                and extracted_harness_session_id != observed_harness_session_id
                and harness_session_id_observer is not None
            ):
                try:
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

            if exit_code == 0 and _spawn_kind(space_dir, run.spawn_id) == "child":
                if extracted.report.content is None:
                    # Child spawns must produce a report directly or via fallback extraction.
                    exit_code = 1
                    failure_reason = "missing_report"
                    break

            if exit_code == 0 and extracted.output_is_empty:
                # Successful exit with no content is unusable; fail fast so primary agents can react.
                exit_code = 1
                failure_reason = "empty_output"
                break

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
            if category == ErrorCategory.STRATEGY_CHANGE:
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
        status = "succeeded" if exit_code == 0 else "failed"
        with signal_coordinator().mask_sigterm():
            spawn_store.finalize_spawn(
                space_dir,
                run.spawn_id,
                status=status,
                exit_code=exit_code,
                duration_secs=duration_seconds,
                total_cost_usd=(
                    finalized_usage.total_cost_usd if finalized_usage is not None else None
                ),
                input_tokens=finalized_usage.input_tokens if finalized_usage is not None else None,
                output_tokens=(
                    finalized_usage.output_tokens if finalized_usage is not None else None
                ),
                error=failure_reason,
            )

    return exit_code
