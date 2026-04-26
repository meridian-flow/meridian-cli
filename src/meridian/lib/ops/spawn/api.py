"""Spawn operations used by CLI and MCP surfaces."""

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from meridian.lib.config.settings import load_config
from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.depth import max_depth_reached
from meridian.lib.core.domain import SpawnStatus
from meridian.lib.core.lifecycle import create_lifecycle_service
from meridian.lib.core.sink import NullSink, OutputSink
from meridian.lib.core.spawn_lifecycle import ACTIVE_SPAWN_STATUSES, is_active_spawn_status
from meridian.lib.core.spawn_service import (
    SpawnApplicationService,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from meridian.lib.core.types import SpawnId
from meridian.lib.launch.request import SessionRequest
from meridian.lib.ops.reference import ResolvedSessionReference, resolve_session_reference
from meridian.lib.ops.runtime import (
    build_runtime_from_root_and_config,
    resolve_runtime_root,
    resolve_runtime_root_and_config,
    resolve_runtime_root_and_config_for_read,
    resolve_runtime_root_for_read,
    runtime_context,
)
from meridian.lib.ops.work_attachment import ensure_explicit_work_item
from meridian.lib.state import session_store, spawn_store
from meridian.lib.state.liveness import is_process_alive
from meridian.lib.state.managed_primary import terminate_managed_primary_processes
from meridian.lib.state.paths import resolve_project_paths
from meridian.lib.state.primary_meta import (
    PrimaryMetadata,
    read_primary_metadata,
    read_primary_surface_metadata,
)
from meridian.lib.streaming.signal_canceller import CancelOutcome, SignalCanceller
from meridian.lib.utils.time import minutes_to_seconds

from .execute import (
    depth_exceeded_output,
    depth_limits,
    execute_spawn_background,
    execute_spawn_blocking,
)
from .models import (
    ModelStats,
    SpawnActionOutput,
    SpawnCancelAllInput,
    SpawnCancelAllOutput,
    SpawnCancelInput,
    SpawnContinueInput,
    SpawnCreateInput,
    SpawnDetailOutput,
    SpawnListEntry,
    SpawnListInput,
    SpawnListOutput,
    SpawnShowInput,
    SpawnStatsChild,
    SpawnStatsInput,
    SpawnStatsOutput,
    SpawnWaitInput,
    SpawnWaitMultiOutput,
    SpawnWrittenFilesInput,
    SpawnWrittenFilesOutput,
)
from .prepare import build_create_payload, validate_create_input
from .query import (
    detail_from_row,
    read_spawn_row,
    read_written_files,
    resolve_spawn_reference,
    resolve_spawn_references,
)

# Phase 0B: SpawnApplicationService will be wired into CLI/MCP operations in a later subphase.
_WAIT_PROGRESS_INTERVAL_SECS = 5.0


def _build_wait_timeout_message(pending_spawn_ids: set[str], elapsed_secs: float) -> str:
    """Build actionable timeout message for LLM agents."""
    sorted_ids = sorted(pending_spawn_ids)
    ids_str = ", ".join(sorted_ids)
    ids_joined = " ".join(sorted_ids)
    
    lines = [
        f"Wait checkpoint after {elapsed_secs / 60:.0f}m. Still running: {ids_str}",
        "",
        "Check progress:",
    ]
    for spawn_id in sorted_ids[:3]:
        lines.append(f"  meridian session log {spawn_id} --last 5")
    if len(sorted_ids) > 3:
        lines.append(f"  ... (+{len(sorted_ids) - 3} more)")
    
    lines.extend([
        "",
        f"If active, re-wait: meridian spawn wait {ids_joined}",
        f"If stuck, cancel:   meridian spawn cancel {sorted_ids[0]}"
        + (" ..." if len(sorted_ids) > 1 else ""),
    ])
    
    return "\n".join(lines)


def _resolve_project_root_input(project_root: str | None) -> Path:
    resolved_root, _ = resolve_runtime_root_and_config_for_read(project_root)
    return resolved_root


def _surface_primary_activity(status: str, activity: str | None) -> str | None:
    normalized = (activity or "").strip()
    if not normalized:
        return None
    if not is_active_spawn_status(status):
        return None
    return normalized


def _forked_from_output(payload: SpawnCreateInput) -> str | None:
    if not payload.session.continue_fork:
        return None

    source_chat_id = (payload.session.forked_from_chat_id or "").strip()
    if source_chat_id:
        return source_chat_id
    source_ref = (payload.session.continue_source_ref or "").strip()
    if source_ref:
        return source_ref
    return None


def spawn_create_sync(
    payload: SpawnCreateInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    resolved_context = runtime_context(ctx)
    if payload.dry_run:
        resolved_root = _resolve_project_root_input(payload.project_root)
        config = load_config(resolved_root)
    else:
        resolved_root, config = resolve_runtime_root_and_config(payload.project_root)
    payload = payload.model_copy(update={"project_root": resolved_root.as_posix()})
    payload, preflight_warning = validate_create_input(payload)
    if payload.dry_run and payload.work.strip():
        project_local_root = resolve_project_paths(resolved_root).root_dir
        resolved_work_id = ensure_explicit_work_item(project_local_root, payload.work)
        payload = payload.model_copy(update={"work": resolved_work_id})

    runtime = None
    if not payload.dry_run:
        current_depth, max_depth = depth_limits(config.max_depth, ctx=resolved_context)
        if max_depth_reached(current_depth, max_depth):
            return depth_exceeded_output(current_depth, max_depth)
        runtime = build_runtime_from_root_and_config(resolved_root, config, sink=sink)

    prepared = build_create_payload(
        payload,
        runtime=runtime,
        preflight_warning=preflight_warning,
        ctx=resolved_context,
    )
    forked_from = _forked_from_output(payload)
    if payload.dry_run:
        return SpawnActionOutput(
            command="spawn.create",
            status="dry-run",
            model=prepared.model or "",
            harness_id=prepared.harness or "",
            warning=prepared.warning,
            agent=prepared.agent,
            agent_path=prepared.agent_metadata.get("session_agent_path") or None,
            skills=prepared.skills,
            skill_paths=prepared.skill_paths,
            reference_files=prepared.reference_files,
            template_vars=prepared.template_vars,
            context_from_resolved=tuple(prepared.context_from or ()),
            composed_prompt=prepared.prompt,
            cli_command=prepared.cli_command,
            message="Dry run complete.",
            forked_from=forked_from,
        )

    if runtime is None:
        raise RuntimeError("Spawn runtime was not initialized.")
    if payload.background:
        result = execute_spawn_background(
            payload=payload,
            request=prepared,
            runtime=runtime,
            ctx=resolved_context,
        )
    else:
        result = execute_spawn_blocking(
            payload=payload,
            request=prepared,
            runtime=runtime,
            ctx=resolved_context,
        )
    if forked_from is None:
        return result
    return result.model_copy(update={"forked_from": forked_from})


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
    project_root = _resolve_project_root_input(payload.project_root)
    from meridian.lib.state.reaper import reconcile_spawns

    runtime_root = resolve_runtime_root_for_read(project_root)
    spawns = list(reversed(reconcile_spawns(runtime_root, spawn_store.list_spawns(runtime_root))))

    # When statuses is empty tuple, show all statuses but cap intelligently:
    # always include all active spawns, pad with recent non-active up to limit.
    show_all = payload.statuses == ()

    if payload.statuses:
        wanted_statuses = set(payload.statuses)
        spawns = [row for row in spawns if row.status in wanted_statuses]
    elif show_all:
        pass
    elif payload.status is not None:
        spawns = [row for row in spawns if row.status == payload.status]
    else:
        spawns = [row for row in spawns if is_active_spawn_status(row.status)]
    if payload.failed:
        spawns = [row for row in spawns if row.status == "failed"]
    if payload.model is not None and payload.model.strip():
        wanted_model = payload.model.strip()
        spawns = [row for row in spawns if row.model == wanted_model]
    if payload.primary:
        spawns = [row for row in spawns if row.kind == "primary"]

    total_count = len(spawns)
    limit = payload.limit if payload.limit > 0 else 20

    if show_all:
        # Always include all active spawns, fill remaining slots with recent non-active.
        active = [row for row in spawns if is_active_spawn_status(row.status)]
        non_active = [row for row in spawns if not is_active_spawn_status(row.status)]
        effective_limit = max(len(active), limit)
        remaining = effective_limit - len(active)
        selected = active + non_active[:remaining]
    else:
        selected = spawns[:limit]

    truncated = total_count > len(selected)
    entries: list[SpawnListEntry] = []
    for row in selected:
        kind = "primary" if (row.kind or "").strip() == "primary" else None
        managed_backend = False
        activity: str | None = None
        surfaced_activity: str | None = None
        if kind == "primary":
            metadata = read_primary_surface_metadata(runtime_root, row.id)
            managed_backend = metadata.managed_backend
            activity = metadata.activity
            surfaced_activity = _surface_primary_activity(row.status, activity)
        entries.append(
            SpawnListEntry(
                spawn_id=row.id,
                status=row.status,
                status_display=(
                    f"{row.status} ({surfaced_activity})"
                    if surfaced_activity is not None
                    else None
                ),
                model=row.model or "",
                kind=kind,
                activity=surfaced_activity,
                managed_backend=managed_backend,
                duration_secs=row.duration_secs,
                cost_usd=row.total_cost_usd,
            )
        )

    return SpawnListOutput(
        spawns=tuple(entries),
        total_count=total_count if truncated else None,
        truncated=truncated,
    )


async def spawn_list(
    payload: SpawnListInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnListOutput:
    return await asyncio.to_thread(spawn_list_sync, payload, ctx=ctx, sink=sink)


def _collect_descendants(
    root_id: str,
    all_spawns: list[spawn_store.SpawnRecord],
) -> list[spawn_store.SpawnRecord]:
    """Walk the parent→child tree and return root + all descendants."""
    by_parent: dict[str | None, list[spawn_store.SpawnRecord]] = {}
    for s in all_spawns:
        by_parent.setdefault(s.parent_id, []).append(s)

    result: list[spawn_store.SpawnRecord] = []
    # Find the root spawn itself
    for s in all_spawns:
        if s.id == root_id:
            result.append(s)
            break

    queue = [root_id]
    while queue:
        parent = queue.pop()
        for child in by_parent.get(parent, []):
            result.append(child)
            queue.append(child.id)
    return result


def spawn_stats_sync(
    payload: SpawnStatsInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnStatsOutput:
    _ = (ctx, sink)
    project_root = _resolve_project_root_input(payload.project_root)
    from meridian.lib.state.reaper import reconcile_spawns

    runtime_root = resolve_runtime_root_for_read(project_root)
    all_spawns = reconcile_spawns(runtime_root, spawn_store.list_spawns(runtime_root))

    if payload.session is not None and payload.session.strip():
        wanted_session = payload.session.strip()
        all_spawns = [row for row in all_spawns if row.chat_id == wanted_session]

    if payload.spawn_id is not None:
        root_id = payload.spawn_id.strip()
        if payload.flat:
            spawns = [s for s in all_spawns if s.id == root_id]
        else:
            spawns = _collect_descendants(root_id, all_spawns)
    else:
        spawns = all_spawns

    model_accum: dict[str, dict[str, int | float]] = {}
    total_duration_secs = 0.0
    total_cost_usd = 0.0
    succeeded = 0
    failed = 0
    cancelled = 0
    running = 0
    finalizing = 0

    for row in spawns:
        if row.status == "succeeded":
            succeeded += 1
        elif row.status == "failed":
            failed += 1
        elif row.status == "cancelled":
            cancelled += 1
        elif row.status == "running":
            running += 1
        elif row.status == "finalizing":
            finalizing += 1

        model_key = row.model or ""
        acc = model_accum.setdefault(model_key, {
            "total": 0, "succeeded": 0, "failed": 0,
            "cancelled": 0, "running": 0, "finalizing": 0, "cost_usd": 0.0,
        })
        acc["total"] = int(acc["total"]) + 1
        if row.status in ("succeeded", "failed", "cancelled", "running", "finalizing"):
            acc[row.status] = int(acc[row.status]) + 1
        if row.total_cost_usd is not None:
            acc["cost_usd"] = float(acc["cost_usd"]) + row.total_cost_usd

        if row.duration_secs is not None:
            total_duration_secs += row.duration_secs
        if row.total_cost_usd is not None:
            total_cost_usd += row.total_cost_usd

    models: dict[str, ModelStats] = {
        k: ModelStats(
            total=int(v["total"]),
            succeeded=int(v["succeeded"]),
            failed=int(v["failed"]),
            cancelled=int(v["cancelled"]),
            running=int(v["running"]),
            finalizing=int(v["finalizing"]),
            cost_usd=float(v["cost_usd"]),
        )
        for k, v in model_accum.items()
    }

    # Build per-child breakdown when scoped to a specific spawn
    children: tuple[SpawnStatsChild, ...] = ()
    if payload.spawn_id is not None and not payload.flat:
        children = tuple(
            SpawnStatsChild(
                spawn_id=s.id,
                status=s.status,
                model=s.model or "",
                duration_secs=s.duration_secs,
                cost_usd=s.total_cost_usd,
                input_tokens=s.input_tokens,
                output_tokens=s.output_tokens,
            )
            for s in spawns
        )

    return SpawnStatsOutput(
        total_runs=len(spawns),
        succeeded=succeeded,
        failed=failed,
        cancelled=cancelled,
        running=running,
        finalizing=finalizing,
        total_duration_secs=total_duration_secs,
        total_cost_usd=total_cost_usd,
        models=models,
        children=children,
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
    project_root = _resolve_project_root_input(payload.project_root)
    spawn_id = resolve_spawn_reference(project_root, payload.spawn_id)
    row = read_spawn_row(project_root, spawn_id)
    if row is None:
        raise ValueError(f"Spawn '{spawn_id}' not found")
    kind = "primary" if (row.kind or "").strip() == "primary" else None
    managed_backend = False
    activity: str | None = None
    backend_pid: int | None = None
    tui_pid: int | None = None
    backend_port: int | None = None
    harness_session_id: str | None = None
    runtime_root = resolve_runtime_root_for_read(project_root)
    if kind == "primary":
        metadata = read_primary_surface_metadata(runtime_root, spawn_id)
        managed_backend = metadata.managed_backend
        activity = metadata.activity
        backend_pid = metadata.backend_pid
        tui_pid = metadata.tui_pid
        backend_port = metadata.backend_port
        harness_session_id = metadata.harness_session_id

    detail = detail_from_row(
        project_root=project_root,
        row=row,
        include_report_body=payload.include_report_body,
    )
    surfaced_activity = _surface_primary_activity(row.status, activity)
    return detail.model_copy(
        update={
            "kind": kind,
            "activity": surfaced_activity,
            "managed_backend": managed_backend,
            "backend_pid": backend_pid,
            "tui_pid": tui_pid,
            "backend_port": backend_port,
            "harness_session_id": harness_session_id or detail.harness_session_id,
        }
    )


async def spawn_show(
    payload: SpawnShowInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnDetailOutput:
    return await asyncio.to_thread(spawn_show_sync, payload, ctx=ctx, sink=sink)


def spawn_files_sync(
    payload: SpawnWrittenFilesInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnWrittenFilesOutput:
    _ = (ctx, sink)
    project_root = _resolve_project_root_input(payload.project_root)
    spawn_id = resolve_spawn_reference(project_root, payload.spawn_id)
    row = read_spawn_row(project_root, spawn_id)
    if row is None:
        raise ValueError(f"Spawn '{spawn_id}' not found")
    written_files = read_written_files(project_root, spawn_id)
    return SpawnWrittenFilesOutput(
        spawn_id=spawn_id,
        written_files=written_files,
    )


async def spawn_files(
    payload: SpawnWrittenFilesInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnWrittenFilesOutput:
    return await asyncio.to_thread(spawn_files_sync, payload, ctx=ctx, sink=sink)


_MANAGED_CANCEL_GRACE_SECS = 5.0
_MANAGED_CANCEL_FALLBACK_WAIT_SECS = 1.0
_MANAGED_CANCEL_POLL_SECS = 0.1


def _started_at_epoch(started_at: str | None) -> float | None:
    normalized = (started_at or "").strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def _coerce_cancel_status(status: str) -> SpawnStatus:
    if status in {"queued", "running", "finalizing", "succeeded", "failed", "cancelled"}:
        return cast("SpawnStatus", status)
    return "failed"


def _cancel_outcome_from_row(
    row: spawn_store.SpawnRecord,
    *,
    already_terminal: bool = False,
) -> CancelOutcome:
    status = _coerce_cancel_status(row.status)
    return CancelOutcome(
        status=status,
        origin=row.terminal_origin or "cancel",
        exit_code=(
            row.exit_code
            if row.exit_code is not None
            else (143 if status == "cancelled" else 1)
        ),
        already_terminal=already_terminal,
        finalizing=status == "finalizing",
    )


async def _wait_for_terminal_spawn(
    runtime_root: Path,
    spawn_id: str,
    *,
    grace_seconds: float,
) -> spawn_store.SpawnRecord | None:
    deadline = time.monotonic() + max(0.0, grace_seconds)
    while True:
        current = spawn_store.get_spawn(runtime_root, spawn_id)
        if current is not None and _spawn_is_terminal(current.status):
            return current
        now = time.monotonic()
        if now >= deadline:
            return None
        await asyncio.sleep(min(_MANAGED_CANCEL_POLL_SECS, deadline - now))


async def _cancel_managed_primary_spawn(
    runtime_root: Path,
    spawn_id: str,
    row: spawn_store.SpawnRecord,
    primary_metadata: PrimaryMetadata,
) -> tuple[CancelOutcome, spawn_store.SpawnRecord]:
    if _spawn_is_terminal(row.status):
        return _cancel_outcome_from_row(row, already_terminal=True), row

    started_epoch = _started_at_epoch(row.started_at)
    launcher_pid = primary_metadata.launcher_pid
    launcher_alive = (
        launcher_pid is not None
        and is_process_alive(launcher_pid, created_after_epoch=started_epoch)
    )
    if launcher_alive:
        terminate_managed_primary_processes(
            primary_metadata,
            started_epoch=started_epoch,
            include_launcher=True,
            include_runtime_children=False,
        )
    else:
        terminate_managed_primary_processes(
            primary_metadata,
            started_epoch=started_epoch,
            include_launcher=False,
        )

    latest = await _wait_for_terminal_spawn(
        runtime_root,
        spawn_id,
        grace_seconds=_MANAGED_CANCEL_GRACE_SECS,
    )
    if latest is None and launcher_alive:
        terminate_managed_primary_processes(
            primary_metadata,
            started_epoch=started_epoch,
            include_launcher=False,
        )
        latest = await _wait_for_terminal_spawn(
            runtime_root,
            spawn_id,
            grace_seconds=_MANAGED_CANCEL_FALLBACK_WAIT_SECS,
        )

    if latest is None:
        lifecycle = create_lifecycle_service(runtime_root.parent, runtime_root)
        if not lifecycle.mark_finalizing(spawn_id):
            lifecycle.finalize(
                spawn_id,
                "failed",
                1,
                origin="cancel",
                error="cancel_timeout",
            )
        latest = spawn_store.get_spawn(runtime_root, spawn_id) or row

    return _cancel_outcome_from_row(latest), latest


def _spawn_cancel_output_from_outcome(
    *,
    spawn_id: str,
    outcome: CancelOutcome,
    row: spawn_store.SpawnRecord,
) -> SpawnActionOutput:
    if outcome.already_terminal:
        message = f"Spawn '{spawn_id}' is already {outcome.status}."
    elif outcome.finalizing:
        message = (
            "Spawn did not terminate within grace; reaper will reconcile."
            if outcome.status != "cancelled"
            else "Spawn cancelled."
        )
    elif outcome.status == "cancelled":
        message = "Spawn cancelled."
    else:
        message = f"Spawn '{spawn_id}' is {outcome.status}."

    return SpawnActionOutput(
        command="spawn.cancel",
        status=outcome.status,
        spawn_id=spawn_id,
        message=message,
        model=row.model,
        harness_id=row.harness,
        exit_code=outcome.exit_code,
    )


def _normalize_work_filter(work: str | None) -> str | None:
    normalized = (work or "").strip()
    return normalized or None


def _spawn_matches_work_item(
    spawn: spawn_store.SpawnRecord,
    *,
    runtime_root: Path,
    work_id: str,
    active_session_work_ids: dict[str, str] | None = None,
) -> bool:
    normalized_work_id = work_id.strip()
    if not normalized_work_id:
        return False
    if spawn.kind == "primary":
        if active_session_work_ids is None:
            active_session_work_ids = {
                record.chat_id: record.active_work_id
                for record in session_store.list_active_session_records(runtime_root)
                if record.active_work_id is not None and record.active_work_id.strip()
            }
        chat_id = (spawn.chat_id or "").strip()
        return (
            bool(chat_id)
            and is_active_spawn_status(spawn.status)
            and active_session_work_ids.get(chat_id) == normalized_work_id
        )
    return (spawn.work_id or "").strip() == normalized_work_id


async def _spawn_cancel_impl(
    payload: SpawnCancelInput,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    _ = sink
    project_root, _ = resolve_runtime_root_and_config(payload.project_root)
    spawn_id = resolve_spawn_reference(project_root, payload.spawn_id)
    runtime_root = resolve_runtime_root(project_root)
    row = spawn_store.get_spawn(runtime_root, spawn_id)
    if row is None:
        raise ValueError(f"Spawn '{spawn_id}' not found")

    primary_metadata = read_primary_metadata(runtime_root, spawn_id)
    if primary_metadata is not None and primary_metadata.managed_backend:
        managed_outcome, managed_row = await _cancel_managed_primary_spawn(
            runtime_root,
            spawn_id,
            row,
            primary_metadata,
        )
        latest = spawn_store.get_spawn(runtime_root, spawn_id) or managed_row
        return _spawn_cancel_output_from_outcome(
            spawn_id=spawn_id,
            outcome=managed_outcome,
            row=latest,
        )

    canceller = SignalCanceller(runtime_root=runtime_root)
    try:
        outcome = await canceller.cancel(SpawnId(spawn_id))
    except RuntimeError as exc:
        return SpawnActionOutput(
            command="spawn.cancel",
            status="failed",
            spawn_id=spawn_id,
            message=f"Cancel failed: {exc}",
            error=str(exc),
            model=row.model,
            harness_id=row.harness,
            exit_code=1,
        )

    latest = spawn_store.get_spawn(runtime_root, spawn_id) or row
    return _spawn_cancel_output_from_outcome(
        spawn_id=spawn_id,
        outcome=outcome,
        row=latest,
    )


def spawn_cancel_all_sync(
    payload: SpawnCancelAllInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnCancelAllOutput:
    _ = ctx
    project_root, _ = resolve_runtime_root_and_config(payload.project_root)
    runtime_root = resolve_runtime_root(project_root)
    work_id = _normalize_work_filter(payload.work)

    from meridian.lib.state.reaper import reconcile_spawns

    active_rows = reconcile_spawns(runtime_root, spawn_store.list_spawns(runtime_root))
    if work_id is not None:
        active_session_work_ids = {
            record.chat_id: record.active_work_id
            for record in session_store.list_active_session_records(runtime_root)
            if record.active_work_id is not None and record.active_work_id.strip()
        }
    else:
        active_session_work_ids = None

    target_rows = [
        row
        for row in active_rows
        if row.status == "running"
        and (
            work_id is None
            or _spawn_matches_work_item(
                row,
                runtime_root=runtime_root,
                work_id=work_id,
                active_session_work_ids=active_session_work_ids,
            )
        )
    ]

    results: list[SpawnActionOutput] = []
    for row in target_rows:
        try:
            result = spawn_cancel_sync(
                SpawnCancelInput(
                    spawn_id=row.id,
                    project_root=project_root.as_posix(),
                ),
                sink=sink,
            )
        except ValueError as exc:
            result = SpawnActionOutput(
                command="spawn.cancel",
                status="failed",
                spawn_id=row.id,
                message=f"Cancel failed: {exc}",
                error=str(exc),
                model=row.model,
                harness_id=row.harness,
                exit_code=1,
            )
        results.append(result)

    cancelled_count = sum(1 for result in results if result.status == "cancelled")
    failed_count = sum(1 for result in results if result.status == "failed")
    return SpawnCancelAllOutput(
        work=work_id,
        total_running=len(target_rows),
        cancelled_count=cancelled_count,
        failed_count=failed_count,
        results=tuple(results),
    )


async def spawn_cancel_all(
    payload: SpawnCancelAllInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnCancelAllOutput:
    _ = ctx
    return await asyncio.to_thread(spawn_cancel_all_sync, payload, ctx=ctx, sink=sink)


def spawn_cancel_sync(
    payload: SpawnCancelInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    _ = ctx
    return asyncio.run(_spawn_cancel_impl(payload, sink=sink))


async def spawn_cancel(
    payload: SpawnCancelInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    _ = ctx
    return await _spawn_cancel_impl(payload, sink=sink)


def _spawn_is_terminal(status: str) -> bool:
    return status not in ACTIVE_SPAWN_STATUSES


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


def _resolve_wait_progress_mode(
    *, verbose: bool, quiet: bool, config_verbosity: str | None
) -> str:
    if quiet:
        return "quiet"
    if verbose:
        return "verbose"
    preset = (config_verbosity or "").strip().lower()
    if preset in {"quiet", "verbose", "debug"}:
        return preset
    return "quiet"


def _render_wait_progress(pending: set[str], *, elapsed_secs: float, mode: str) -> str | None:
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


def _emit_wait_progress(message: str, *, sink: OutputSink) -> None:
    sink.status(message)


def spawn_wait_sync(
    payload: SpawnWaitInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnWaitMultiOutput:
    active_sink = sink or NullSink()
    project_root, config = resolve_runtime_root_and_config_for_read(payload.project_root)
    spawn_ids = resolve_spawn_references(project_root, _normalize_wait_spawn_ids(payload))
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
    progress_mode = _resolve_wait_progress_mode(
        verbose=payload.verbose,
        quiet=payload.quiet,
        config_verbosity=getattr(getattr(config, "output", None), "verbosity", None),
    )
    progress_interval = max(_WAIT_PROGRESS_INTERVAL_SECS, poll)
    next_progress = started + progress_interval

    while True:
        for spawn_id in tuple(pending):
            row = read_spawn_row(project_root, spawn_id)
            if row is None:
                raise ValueError(f"Spawn '{spawn_id}' not found")

            if _spawn_is_terminal(row.status):
                completed_rows[spawn_id] = row
                pending.remove(spawn_id)

        if not pending:
            details = tuple(
                detail_from_row(
                    project_root=project_root,
                    row=completed_rows[spawn_id],
                    include_report_body=payload.include_report_body,
                )
                for spawn_id in spawn_ids
            )
            return _build_wait_multi_output(details)

        now = time.monotonic()
        if now >= deadline:
            elapsed = now - started
            raise TimeoutError(_build_wait_timeout_message(pending, elapsed))
        if now >= next_progress:
            progress = _render_wait_progress(
                pending,
                elapsed_secs=max(now - started, 0.0),
                mode=progress_mode,
            )
            if progress is not None:
                _emit_wait_progress(progress, sink=active_sink)
            next_progress = now + progress_interval
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
    project_root: Path,
) -> tuple[str, spawn_store.SpawnRecord, ResolvedSessionReference]:
    resolved_spawn_id = resolve_spawn_reference(project_root, payload_spawn_id)
    row = read_spawn_row(project_root, resolved_spawn_id)
    if row is None:
        raise ValueError(f"Spawn '{resolved_spawn_id}' not found")
    resolved_reference = resolve_session_reference(project_root, resolved_spawn_id)
    return resolved_spawn_id, row, resolved_reference


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
    project_root, _ = resolve_runtime_root_and_config(payload.project_root)
    resolved_spawn_id, source_spawn, resolved_reference = _source_spawn_for_follow_up(
        payload.spawn_id, project_root
    )
    if resolved_reference.missing_harness_session_id:
        raise ValueError(
            f"Spawn '{resolved_spawn_id}' has no recorded session — cannot continue/fork."
        )

    requested_harness = (payload.harness or "").strip() or None
    source_harness = (resolved_reference.harness or "").strip() or None
    if (
        requested_harness is not None
        and source_harness is not None
        and requested_harness != source_harness
    ):
        raise ValueError(
            f"Cannot continue spawn '{resolved_spawn_id}' with harness '{requested_harness}'; "
            f"source spawn uses '{source_harness}'."
        )

    derived_prompt = _prompt_for_follow_up(source_spawn, resolved_spawn_id, payload.prompt)
    create_input = SpawnCreateInput(
        prompt=derived_prompt,
        model=_model_for_follow_up(source_spawn, payload.model),
        harness=requested_harness,
        agent=payload.agent,
        skills=payload.skills,
        project_root=payload.project_root,
        dry_run=payload.dry_run,
        timeout=payload.timeout,
        background=payload.background,
        session=SessionRequest(
            requested_harness_session_id=resolved_reference.harness_session_id,
            continue_harness=resolved_reference.harness,
            continue_source_tracked=resolved_reference.tracked,
            continue_source_ref=resolved_spawn_id,
            continue_fork=payload.fork,
            continue_chat_id=resolved_reference.source_chat_id,
            forked_from_chat_id=resolved_reference.source_chat_id if payload.fork else None,
            source_execution_cwd=resolved_reference.source_execution_cwd,
        ),
        passthrough_args=payload.passthrough_args,
        approval=payload.approval,
    )
    return _with_command(spawn_create_sync(create_input, ctx=ctx, sink=sink), "spawn.continue")


async def spawn_continue(
    payload: SpawnContinueInput,
    ctx: RuntimeContext | None = None,
    *,
    sink: OutputSink | None = None,
) -> SpawnActionOutput:
    return await asyncio.to_thread(spawn_continue_sync, payload, ctx=ctx, sink=sink)
