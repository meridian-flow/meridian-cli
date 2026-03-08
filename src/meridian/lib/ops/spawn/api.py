"""Spawn operations used by CLI, MCP, and DirectAdapter surfaces."""


import asyncio
import os
import signal
import time
from pathlib import Path

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.sink import NullSink, OutputSink
from meridian.lib.ops.runtime import build_runtime_from_root_and_config, resolve_runtime_root_and_config
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_state_paths

from .execute import (
    depth_exceeded_output,
    depth_limits,
    execute_spawn_background,
    execute_spawn_blocking,
)
from .models import (
    SpawnActionOutput,
    SpawnCancelInput,
    SpawnContinueInput,
    SpawnCreateInput,
    SpawnDetailOutput,
    SpawnListEntry,
    SpawnListInput,
    SpawnListOutput,
    SpawnShowInput,
    SpawnStatsInput,
    SpawnStatsOutput,
    SpawnWaitInput,
    SpawnWaitMultiOutput,
)
from .prepare import build_create_payload, validate_create_input
from .query import detail_from_row, read_spawn_row, resolve_spawn_reference, resolve_spawn_references

_WAIT_HEARTBEAT_INTERVAL_SECS = 5.0


def minutes_to_seconds(timeout_minutes: float | None) -> float | None:
    if timeout_minutes is None:
        return None
    return timeout_minutes * 60.0


def _runtime_context(ctx: RuntimeContext | None) -> RuntimeContext:
    if ctx is not None:
        return ctx
    return RuntimeContext.from_environment()


def _state_root(repo_root: Path) -> Path:
    return resolve_state_paths(repo_root).root_dir


def spawn_create_sync(
    payload: SpawnCreateInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    runtime_context = _runtime_context(ctx)
    payload, preflight_warning = validate_create_input(payload)
    resolved_root, config = resolve_runtime_root_and_config(payload.repo_root)

    runtime = None
    if not payload.dry_run:
        current_depth, max_depth = depth_limits(config.max_depth, ctx=runtime_context)
        if current_depth >= max_depth:
            return depth_exceeded_output(current_depth, max_depth)
        runtime = build_runtime_from_root_and_config(resolved_root, config, sink=sink)

    prepared = build_create_payload(payload, runtime=runtime, preflight_warning=preflight_warning)
    if payload.dry_run:
        return SpawnActionOutput(
            command="spawn.create",
            status="dry-run",
            model=prepared.model,
            harness_id=prepared.harness_id,
            warning=prepared.warning,
            agent=prepared.agent_name,
            reference_files=prepared.reference_files,
            template_vars=prepared.template_vars,
            composed_prompt=prepared.composed_prompt,
            cli_command=prepared.cli_command,
            message="Dry run complete.",
        )

    if runtime is None:
        raise RuntimeError("Spawn runtime was not initialized.")
    if payload.background:
        return execute_spawn_background(
            payload=payload,
            prepared=prepared,
            runtime=runtime,
            ctx=runtime_context,
        )
    return execute_spawn_blocking(
        payload=payload,
        prepared=prepared,
        runtime=runtime,
        ctx=runtime_context,
    )


async def spawn_create(
    payload: SpawnCreateInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    return await asyncio.to_thread(spawn_create_sync, payload, ctx=ctx, sink=sink)


def spawn_list_sync(
    payload: SpawnListInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnListOutput:
    _ = (ctx, sink)
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    spawns = list(reversed(spawn_store.list_spawns(_state_root(repo_root))))
    if payload.status is not None:
        spawns = [row for row in spawns if row.status == payload.status]
    if payload.failed:
        spawns = [row for row in spawns if row.status == "failed"]
    if payload.model is not None and payload.model.strip():
        wanted_model = payload.model.strip()
        spawns = [row for row in spawns if row.model == wanted_model]

    limit = payload.limit if payload.limit > 0 else 20
    return SpawnListOutput(
        spawns=tuple(
            SpawnListEntry(
                spawn_id=row.id,
                status=row.status,
                model=row.model or "",
                duration_secs=row.duration_secs,
                cost_usd=row.total_cost_usd,
            )
            for row in spawns[:limit]
        )
    )


async def spawn_list(
    payload: SpawnListInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnListOutput:
    return await asyncio.to_thread(spawn_list_sync, payload, ctx=ctx, sink=sink)


def spawn_stats_sync(
    payload: SpawnStatsInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnStatsOutput:
    _ = (ctx, sink)
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    spawns = spawn_store.list_spawns(_state_root(repo_root))
    if payload.session is not None and payload.session.strip():
        wanted_session = payload.session.strip()
        spawns = [row for row in spawns if row.chat_id == wanted_session]

    models: dict[str, int] = {}
    total_duration_secs = 0.0
    total_cost_usd = 0.0
    succeeded = 0
    failed = 0
    cancelled = 0
    running = 0

    for row in spawns:
        if row.status == "succeeded":
            succeeded += 1
        elif row.status == "failed":
            failed += 1
        elif row.status == "cancelled":
            cancelled += 1
        elif row.status == "running":
            running += 1

        if row.model is not None:
            models[row.model] = models.get(row.model, 0) + 1
        if row.duration_secs is not None:
            total_duration_secs += row.duration_secs
        if row.total_cost_usd is not None:
            total_cost_usd += row.total_cost_usd

    return SpawnStatsOutput(
        total_runs=len(spawns),
        succeeded=succeeded,
        failed=failed,
        cancelled=cancelled,
        running=running,
        total_duration_secs=total_duration_secs,
        total_cost_usd=total_cost_usd,
        models=models,
    )


async def spawn_stats(
    payload: SpawnStatsInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnStatsOutput:
    return await asyncio.to_thread(spawn_stats_sync, payload, ctx=ctx, sink=sink)


def spawn_show_sync(
    payload: SpawnShowInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnDetailOutput:
    _ = (ctx, sink)
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    spawn_id = resolve_spawn_reference(repo_root, payload.spawn_id)
    row = read_spawn_row(repo_root, spawn_id)
    if row is None:
        raise ValueError(f"Spawn '{spawn_id}' not found")
    return detail_from_row(
        repo_root=repo_root,
        row=row,
        report=payload.report,
        include_files=payload.include_files,
    )


async def spawn_show(
    payload: SpawnShowInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnDetailOutput:
    return await asyncio.to_thread(spawn_show_sync, payload, ctx=ctx, sink=sink)


def _read_background_pid(state_root: Path, spawn_id: str) -> int:
    pid_path = state_root / "spawns" / spawn_id / "background.pid"
    if not pid_path.is_file():
        raise ValueError(f"Spawn '{spawn_id}' has no background worker PID.")
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError as exc:
        raise ValueError(f"Spawn '{spawn_id}' has invalid background PID.") from exc
    if pid <= 0:
        raise ValueError(f"Spawn '{spawn_id}' has invalid background PID.")
    return pid


def spawn_cancel_sync(
    payload: SpawnCancelInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    _ = (ctx, sink)
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    spawn_id = resolve_spawn_reference(repo_root, payload.spawn_id)
    state_root = _state_root(repo_root)
    row = read_spawn_row(repo_root, spawn_id)
    if row is None:
        raise ValueError(f"Spawn '{spawn_id}' not found")

    if _spawn_is_terminal(row.status):
        return SpawnActionOutput(
            command="spawn.cancel",
            status=row.status,
            spawn_id=spawn_id,
            message=f"Spawn '{spawn_id}' is already {row.status}.",
            model=row.model,
            harness_id=row.harness,
        )

    pid = _read_background_pid(state_root, spawn_id)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    spawn_store.finalize_spawn(
        state_root,
        spawn_id,
        status="cancelled",
        exit_code=130,
        error="cancelled",
    )
    return SpawnActionOutput(
        command="spawn.cancel",
        status="cancelled",
        spawn_id=spawn_id,
        message="Spawn cancelled.",
        model=row.model,
        harness_id=row.harness,
    )


async def spawn_cancel(
    payload: SpawnCancelInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    return await asyncio.to_thread(spawn_cancel_sync, payload, ctx=ctx, sink=sink)


def _spawn_is_terminal(status: str) -> bool:
    return status not in {"queued", "running"}


def _normalize_wait_spawn_ids(payload: SpawnWaitInput) -> tuple[str, ...]:
    candidates: list[str] = []
    for spawn_id in payload.spawn_ids:
        normalized = spawn_id.strip()
        if normalized:
            candidates.append(normalized)

    if payload.spawn_id is not None and payload.spawn_id.strip():
        candidates.append(payload.spawn_id.strip())

    deduped = tuple(dict.fromkeys(candidates))
    if not deduped:
        raise ValueError("At least one spawn_id is required")
    return deduped


def _build_wait_multi_output(results: tuple[SpawnDetailOutput, ...]) -> SpawnWaitMultiOutput:
    total_runs = len(results)
    succeeded_runs = sum(1 for run in results if run.status == "succeeded")
    failed_runs = sum(1 for run in results if run.status == "failed")
    cancelled_runs = sum(1 for run in results if run.status == "cancelled")
    any_failed = any(run.status in {"failed", "cancelled"} for run in results)

    spawn_id: str | None = None
    status: str | None = None
    exit_code: int | None = None
    if total_runs == 1:
        spawn_id = results[0].spawn_id
        status = results[0].status
        exit_code = results[0].exit_code

    return SpawnWaitMultiOutput(
        spawns=results,
        total_runs=total_runs,
        succeeded_runs=succeeded_runs,
        failed_runs=failed_runs,
        cancelled_runs=cancelled_runs,
        any_failed=any_failed,
        spawn_id=spawn_id,
        status=status,
        exit_code=exit_code,
    )


def _resolve_wait_heartbeat_mode(*, verbose: bool, quiet: bool, config_verbosity: str | None) -> str:
    if quiet:
        return "quiet"
    if verbose:
        return "verbose"
    preset = (config_verbosity or "").strip().lower()
    if preset in {"quiet", "verbose", "debug"}:
        return preset
    return "quiet"


def _render_wait_heartbeat(pending: set[str], *, elapsed_secs: float, mode: str) -> str | None:
    if not pending or mode == "quiet":
        return None
    pending_count = len(pending)
    if mode in {"verbose", "debug"}:
        ordered = sorted(pending)
        preview = ", ".join(ordered[:5])
        if len(ordered) > 5:
            preview = f"{preview}, +{len(ordered) - 5} more"
        return f"waiting {elapsed_secs:.1f}s; pending spawns ({pending_count}): {preview}"
    return f"waiting for {pending_count} spawn(s) to finish..."


def _emit_wait_heartbeat(message: str, *, sink: OutputSink) -> None:
    sink.heartbeat(message)


def spawn_wait_sync(
    payload: SpawnWaitInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnWaitMultiOutput:
    active_sink = sink or NullSink()
    repo_root, config = resolve_runtime_root_and_config(payload.repo_root)
    spawn_ids = resolve_spawn_references(repo_root, _normalize_wait_spawn_ids(payload))
    timeout_minutes = payload.timeout if payload.timeout is not None else config.wait_timeout_minutes
    timeout_seconds = minutes_to_seconds(timeout_minutes) or 0.0
    started = time.monotonic()
    deadline = started + max(timeout_seconds, 0.0)
    poll = payload.poll_interval_secs if payload.poll_interval_secs is not None else config.retry_backoff_seconds
    if poll <= 0:
        poll = config.retry_backoff_seconds

    completed_rows: dict[str, spawn_store.SpawnRecord] = {}
    pending: set[str] = set(spawn_ids)
    heartbeat_mode = _resolve_wait_heartbeat_mode(
        verbose=payload.verbose,
        quiet=payload.quiet,
        config_verbosity=getattr(getattr(config, "output", None), "verbosity", None),
    )
    heartbeat_interval = max(_WAIT_HEARTBEAT_INTERVAL_SECS, poll)
    next_heartbeat = started + heartbeat_interval

    while True:
        for spawn_id in tuple(pending):
            row = read_spawn_row(repo_root, spawn_id)
            if row is None:
                raise ValueError(f"Spawn '{spawn_id}' not found")

            if _spawn_is_terminal(row.status):
                completed_rows[spawn_id] = row
                pending.remove(spawn_id)

        if not pending:
            details = tuple(
                detail_from_row(
                    repo_root=repo_root,
                    row=completed_rows[spawn_id],
                    report=payload.report,
                    include_files=payload.include_files,
                )
                for spawn_id in spawn_ids
            )
            return _build_wait_multi_output(details)

        now = time.monotonic()
        if now >= deadline:
            timed_out = "', '".join(sorted(pending))
            raise TimeoutError(f"Timed out waiting for spawn(s) '{timed_out}'")
        if now >= next_heartbeat:
            heartbeat = _render_wait_heartbeat(
                pending,
                elapsed_secs=max(now - started, 0.0),
                mode=heartbeat_mode,
            )
            if heartbeat is not None:
                _emit_wait_heartbeat(heartbeat, sink=active_sink)
            next_heartbeat = now + heartbeat_interval
        time.sleep(poll)


async def spawn_wait(
    payload: SpawnWaitInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnWaitMultiOutput:
    return await asyncio.to_thread(spawn_wait_sync, payload, ctx=ctx, sink=sink)


def _source_spawn_for_follow_up(
    payload_spawn_id: str,
    repo_root: Path,
) -> tuple[str, spawn_store.SpawnRecord]:
    resolved_spawn_id = resolve_spawn_reference(repo_root, payload_spawn_id)
    row = read_spawn_row(repo_root, resolved_spawn_id)
    if row is None:
        raise ValueError(f"Spawn '{resolved_spawn_id}' not found")
    return resolved_spawn_id, row


def _prompt_for_follow_up(
    source_spawn: spawn_store.SpawnRecord, payload_spawn_id: str, prompt: str | None
) -> str:
    if prompt is not None and prompt.strip():
        return prompt

    existing_prompt = (source_spawn.prompt or "").strip()
    if not existing_prompt:
        raise ValueError(f"Spawn '{payload_spawn_id}' has no stored prompt")
    return existing_prompt


def _model_for_follow_up(source_spawn: spawn_store.SpawnRecord, override_model: str) -> str:
    if override_model.strip():
        return override_model
    return (source_spawn.model or "").strip()


def _with_command(result: SpawnActionOutput, command: str) -> SpawnActionOutput:
    return result.model_copy(update={"command": command})


def spawn_continue_sync(
    payload: SpawnContinueInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    _ = ctx
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_spawn_id, source_spawn = _source_spawn_for_follow_up(payload.spawn_id, repo_root)
    derived_prompt = _prompt_for_follow_up(source_spawn, resolved_spawn_id, payload.prompt)
    source_harness = (source_spawn.harness or "").strip() or None
    source_session_id = (source_spawn.harness_session_id or "").strip() or None
    create_input = SpawnCreateInput(
        prompt=derived_prompt,
        model=_model_for_follow_up(source_spawn, payload.model),
        repo_root=payload.repo_root,
        dry_run=payload.dry_run,
        timeout=payload.timeout,
        continue_harness_session_id=source_session_id,
        continue_harness=source_harness,
        continue_fork=payload.fork,
    )
    return _with_command(spawn_create_sync(create_input, sink=sink), "spawn.continue")


async def spawn_continue(
    payload: SpawnContinueInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    return await asyncio.to_thread(spawn_continue_sync, payload, ctx=ctx, sink=sink)
