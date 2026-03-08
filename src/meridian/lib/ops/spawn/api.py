"""Spawn operations used by CLI, MCP, and DirectAdapter surfaces."""


import asyncio
import os
import signal
import time
from pathlib import Path

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.sink import NullSink, OutputSink
from meridian.lib.state import spawn_store
from meridian.lib.state.space_store import create_space
from meridian.lib.state.paths import resolve_space_dir

from ..runtime import (
    build_runtime_from_root_and_config,
    require_space_id,
    resolve_runtime_root_and_config,
    resolve_space_id_or_none,
)

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
from .query import (
    detail_from_row,
    read_spawn_row,
    resolve_spawn_reference,
    resolve_spawn_references,
)

_WAIT_HEARTBEAT_INTERVAL_SECS = 5.0


def minutes_to_seconds(timeout_minutes: float | None) -> float | None:
    if timeout_minutes is None:
        return None
    return timeout_minutes * 60.0


def _runtime_context(ctx: RuntimeContext | None) -> RuntimeContext:
    if ctx is not None:
        return ctx
    return RuntimeContext.from_environment()


def _context_space_id(space_id: str | None) -> str | None:
    normalized = (space_id or "").strip()
    return normalized or None


def _resolve_space_dir(
    repo_root: Path,
    space: str | None = None,
    *,
    space_id: str | None = None,
) -> tuple[str, Path]:
    space_id = require_space_id(space, space_id=space_id)
    return str(space_id), resolve_space_dir(repo_root, space_id)


def _resolve_or_create_space(
    explicit: str | None,
    repo_root: Path,
    *,
    space_id: str | None = None,
) -> tuple[str, bool]:
    """Resolve space from explicit value / env, or auto-create one.

    Returns (space_id, auto_created).
    """
    resolved = resolve_space_id_or_none(explicit, space_id=space_id)
    if resolved is not None:
        return resolved, False
    record = create_space(repo_root)
    return record.id, True


def _non_empty_space(space: str | None, *, space_id: str | None = None) -> str | None:
    normalized = (space or "").strip()
    if not normalized:
        normalized = _context_space_id(space_id) or ""
    if not normalized:
        return None
    return normalized


def spawn_create_sync(
    payload: SpawnCreateInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    runtime_context = _runtime_context(ctx)
    payload, preflight_warning = validate_create_input(payload)
    resolved_root, config = resolve_runtime_root_and_config(payload.repo_root)
    space_id_str, auto_created = _resolve_or_create_space(
        payload.space,
        resolved_root,
        space_id=_context_space_id(str(runtime_context.space_id or "")),
    )
    payload = payload.model_copy(update={"space": space_id_str})
    if auto_created:
        auto_warning = (
            f"Auto-created space {space_id_str}. Pass --space {space_id_str} to add more spawns to this space.\n"
            f"hint: export MERIDIAN_SPACE_ID={space_id_str}"
        )
        preflight_warning = f"{preflight_warning}\n{auto_warning}" if preflight_warning else auto_warning

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
    _ = sink
    runtime_context = _runtime_context(ctx)
    if payload.no_space:
        return SpawnListOutput(spawns=())

    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    current_space_id, space_dir = _resolve_space_dir(
        repo_root,
        payload.space,
        space_id=_context_space_id(str(runtime_context.space_id or "")),
    )

    spawns = list(reversed(spawn_store.list_spawns(space_dir)))
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
                space_id=current_space_id,
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
    _ = sink
    runtime_context = _runtime_context(ctx)
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    _, space_dir = _resolve_space_dir(
        repo_root,
        payload.space,
        space_id=_context_space_id(str(runtime_context.space_id or "")),
    )

    spawns = spawn_store.list_spawns(space_dir)
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
    _ = sink
    runtime_context = _runtime_context(ctx)
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = _non_empty_space(
        payload.space,
        space_id=_context_space_id(str(runtime_context.space_id or "")),
    )
    spawn_id = resolve_spawn_reference(repo_root, payload.spawn_id, resolved_space)
    row = read_spawn_row(repo_root, spawn_id, resolved_space)
    if row is None:
        raise ValueError(f"Spawn '{spawn_id}' not found")
    return detail_from_row(
        repo_root=repo_root,
        row=row,
        report=payload.report,
        include_files=payload.include_files,
        space_id=resolved_space,
    )


async def spawn_show(
    payload: SpawnShowInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnDetailOutput:
    return await asyncio.to_thread(spawn_show_sync, payload, ctx=ctx, sink=sink)


def _read_background_pid(space_dir: Path, spawn_id: str) -> int:
    pid_path = space_dir / "spawns" / spawn_id / "background.pid"
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
    _ = sink
    runtime_context = _runtime_context(ctx)
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = _non_empty_space(
        payload.space,
        space_id=_context_space_id(str(runtime_context.space_id or "")),
    )
    spawn_id = resolve_spawn_reference(repo_root, payload.spawn_id, resolved_space)
    current_space_id, space_dir = _resolve_space_dir(
        repo_root,
        resolved_space,
        space_id=_context_space_id(str(runtime_context.space_id or "")),
    )
    row = read_spawn_row(repo_root, spawn_id, current_space_id)
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

    pid = _read_background_pid(space_dir, spawn_id)
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    spawn_store.finalize_spawn(
        space_dir,
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
    runtime_context = _runtime_context(ctx)
    repo_root, config = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = _non_empty_space(
        payload.space,
        space_id=_context_space_id(str(runtime_context.space_id or "")),
    )
    spawn_ids = resolve_spawn_references(repo_root, _normalize_wait_spawn_ids(payload), resolved_space)
    timeout_minutes = (
        payload.timeout if payload.timeout is not None else config.wait_timeout_minutes
    )
    timeout_seconds = minutes_to_seconds(timeout_minutes) or 0.0
    started = time.monotonic()
    deadline = started + max(timeout_seconds, 0.0)
    poll = (
        payload.poll_interval_secs
        if payload.poll_interval_secs is not None
        else config.retry_backoff_seconds
    )
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
            row = read_spawn_row(repo_root, spawn_id, resolved_space)
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
                    space_id=resolved_space,
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
    space: str | None = None,
    *,
    context_space_id: str | None = None,
) -> tuple[str, spawn_store.SpawnRecord]:
    resolved_space = _non_empty_space(space, space_id=context_space_id)
    resolved_spawn_id = resolve_spawn_reference(repo_root, payload_spawn_id, resolved_space)
    row = read_spawn_row(repo_root, resolved_spawn_id, resolved_space)
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
    runtime_context = _runtime_context(ctx)
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = _non_empty_space(
        payload.space,
        space_id=_context_space_id(str(runtime_context.space_id or "")),
    )
    resolved_spawn_id, source_spawn = _source_spawn_for_follow_up(
        payload.spawn_id,
        repo_root,
        resolved_space,
        context_space_id=_context_space_id(str(runtime_context.space_id or "")),
    )
    derived_prompt = _prompt_for_follow_up(source_spawn, resolved_spawn_id, payload.prompt)
    source_harness = (source_spawn.harness or "").strip() or None
    source_session_id = (source_spawn.harness_session_id or "").strip() or None
    create_input = SpawnCreateInput(
        prompt=derived_prompt,
        model=_model_for_follow_up(source_spawn, payload.model),
        repo_root=payload.repo_root,
        dry_run=payload.dry_run,
        timeout=payload.timeout,
        space=resolved_space,
        continue_harness_session_id=source_session_id,
        continue_harness=source_harness,
        continue_fork=payload.fork,
    )
    result = spawn_create_sync(create_input, ctx=runtime_context, sink=sink)
    return _with_command(result, "spawn.continue")


async def spawn_continue(
    payload: SpawnContinueInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    return await asyncio.to_thread(spawn_continue_sync, payload, ctx=ctx, sink=sink)
