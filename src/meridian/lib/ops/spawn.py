"""Spawn operations used by CLI, MCP, and DirectAdapter surfaces."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from pathlib import Path

from meridian.lib.exec.spawn import execute_with_finalization
from meridian.lib.ops._runtime import (
    SPACE_REQUIRED_ERROR,
    build_runtime_from_root_and_config,
    resolve_runtime_root_and_config,
    resolve_space_id,
)
from meridian.lib.ops.registry import OperationSpec, operation
from meridian.lib.safety.permissions import (
    build_permission_config,
    validate_permission_config_for_harness,
)
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir

from . import _spawn_execute as _spawn_execute_module
from . import _spawn_prepare as _spawn_prepare_module
from ._spawn_execute import (
    _depth_exceeded_output,
    _depth_limits,
    _execute_spawn_background,
    _execute_spawn_blocking,
    logger,
)
from ._spawn_models import (
    SpawnActionOutput,
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
from ._spawn_prepare import _build_create_payload, _validate_create_input
from ._spawn_query import (
    _detail_from_row,
    _read_spawn_row,
    _resolve_space_id,
    resolve_spawn_reference,
    resolve_spawn_references,
)


def _resolve_space_dir(repo_root: Path, space: str | None = None) -> tuple[str, Path]:
    space_id = _resolve_space_id(space)
    return space_id, resolve_space_dir(repo_root, space_id)


def _merge_warnings(*warnings: str | None) -> str | None:
    parts = [item.strip() for item in warnings if item and item.strip()]
    if not parts:
        return None
    return "; ".join(parts)


def _non_empty_space(space: str | None) -> str | None:
    if space is None:
        return None
    normalized = space.strip()
    if not normalized:
        return None
    return normalized


def spawn_create_sync(payload: SpawnCreateInput) -> SpawnActionOutput:
    _spawn_prepare_module.build_permission_config = build_permission_config
    _spawn_prepare_module.validate_permission_config_for_harness = (
        validate_permission_config_for_harness
    )
    _spawn_prepare_module.logger = logger
    _spawn_execute_module.execute_with_finalization = execute_with_finalization
    _spawn_execute_module.logger = logger

    payload, preflight_warning = _validate_create_input(payload)
    resolved_space_id = resolve_space_id(payload.space)
    if resolved_space_id is None:
        raise ValueError(SPACE_REQUIRED_ERROR)
    payload = replace(payload, space=str(resolved_space_id))

    runtime = None
    if not payload.dry_run:
        resolved_root, config = resolve_runtime_root_and_config(payload.repo_root)
        current_depth, max_depth = _depth_limits(config.max_depth)
        if current_depth >= max_depth:
            return _depth_exceeded_output(current_depth, max_depth)
        runtime = build_runtime_from_root_and_config(resolved_root, config)

    prepared = _build_create_payload(payload, runtime=runtime, preflight_warning=preflight_warning)
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
            report_path=prepared.report_path,
            composed_prompt=prepared.composed_prompt,
            cli_command=prepared.cli_command,
            message="Dry run complete.",
        )

    if runtime is None:
        raise RuntimeError("Spawn runtime was not initialized.")
    if payload.background:
        return _execute_spawn_background(payload=payload, prepared=prepared, runtime=runtime)
    return _execute_spawn_blocking(payload=payload, prepared=prepared, runtime=runtime)


async def spawn_create(payload: SpawnCreateInput) -> SpawnActionOutput:
    return await asyncio.to_thread(spawn_create_sync, payload)


def spawn_list_sync(payload: SpawnListInput) -> SpawnListOutput:
    if payload.no_space:
        return SpawnListOutput(spawns=())

    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    current_space_id, space_dir = _resolve_space_dir(repo_root, payload.space)

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


async def spawn_list(payload: SpawnListInput) -> SpawnListOutput:
    return await asyncio.to_thread(spawn_list_sync, payload)


def spawn_stats_sync(payload: SpawnStatsInput) -> SpawnStatsOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    current_space_id, space_dir = _resolve_space_dir(repo_root, payload.space)

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


async def spawn_stats(payload: SpawnStatsInput) -> SpawnStatsOutput:
    return await asyncio.to_thread(spawn_stats_sync, payload)


def spawn_show_sync(payload: SpawnShowInput) -> SpawnDetailOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = _non_empty_space(payload.space)
    spawn_id = resolve_spawn_reference(repo_root, payload.spawn_id, resolved_space)
    row = _read_spawn_row(repo_root, spawn_id, resolved_space)
    if row is None:
        raise ValueError(f"Spawn '{spawn_id}' not found")
    return _detail_from_row(
        repo_root=repo_root,
        row=row,
        report=payload.report,
        include_files=payload.include_files,
        space_id=resolved_space,
    )


async def spawn_show(payload: SpawnShowInput) -> SpawnDetailOutput:
    return await asyncio.to_thread(spawn_show_sync, payload)


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


def spawn_wait_sync(payload: SpawnWaitInput) -> SpawnWaitMultiOutput:
    repo_root, config = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = _non_empty_space(payload.space)
    spawn_ids = resolve_spawn_references(repo_root, _normalize_wait_spawn_ids(payload), resolved_space)
    timeout_secs = (
        payload.timeout_secs if payload.timeout_secs is not None else config.wait_timeout_seconds
    )
    deadline = time.monotonic() + max(timeout_secs, 0.0)
    poll = (
        payload.poll_interval_secs
        if payload.poll_interval_secs is not None
        else config.retry_backoff_seconds
    )
    if poll <= 0:
        poll = config.retry_backoff_seconds

    completed_rows: dict[str, spawn_store.SpawnRecord] = {}
    pending: set[str] = set(spawn_ids)

    while True:
        for spawn_id in tuple(pending):
            row = _read_spawn_row(repo_root, spawn_id, resolved_space)
            if row is None:
                raise ValueError(f"Spawn '{spawn_id}' not found")

            if _spawn_is_terminal(row.status):
                completed_rows[spawn_id] = row
                pending.remove(spawn_id)

        if not pending:
            details = tuple(
                _detail_from_row(
                    repo_root=repo_root,
                    row=completed_rows[spawn_id],
                    report=payload.report,
                    include_files=payload.include_files,
                    space_id=resolved_space,
                )
                for spawn_id in spawn_ids
            )
            return _build_wait_multi_output(details)

        if time.monotonic() >= deadline:
            timed_out = "', '".join(sorted(pending))
            raise TimeoutError(f"Timed out waiting for spawn(s) '{timed_out}'")
        time.sleep(poll)


async def spawn_wait(payload: SpawnWaitInput) -> SpawnWaitMultiOutput:
    return await asyncio.to_thread(spawn_wait_sync, payload)


def _source_spawn_for_follow_up(
    payload_spawn_id: str,
    repo_root: Path,
    space: str | None = None,
) -> tuple[str, spawn_store.SpawnRecord]:
    resolved_space = _non_empty_space(space)
    resolved_spawn_id = resolve_spawn_reference(repo_root, payload_spawn_id, resolved_space)
    row = _read_spawn_row(repo_root, resolved_spawn_id, resolved_space)
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
    return replace(result, command=command)


def spawn_continue_sync(payload: SpawnContinueInput) -> SpawnActionOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_spawn_id, source_spawn = _source_spawn_for_follow_up(
        payload.spawn_id,
        repo_root,
        payload.space,
    )
    derived_prompt = _prompt_for_follow_up(source_spawn, resolved_spawn_id, payload.prompt)
    source_harness = (source_spawn.harness or "").strip() or None
    source_session_id = (source_spawn.harness_session_id or "").strip() or None
    create_input = SpawnCreateInput(
        prompt=derived_prompt,
        model=_model_for_follow_up(source_spawn, payload.model),
        repo_root=payload.repo_root,
        timeout_secs=payload.timeout_secs,
        space=payload.space,
        continue_harness_session_id=source_session_id,
        continue_harness=source_harness,
        continue_fork=payload.fork,
    )
    result = spawn_create_sync(create_input)
    return _with_command(result, "spawn.continue")


async def spawn_continue(payload: SpawnContinueInput) -> SpawnActionOutput:
    return await asyncio.to_thread(spawn_continue_sync, payload)


operation(
    OperationSpec[SpawnCreateInput, SpawnActionOutput](
        name="spawn.create",
        handler=spawn_create,
        sync_handler=spawn_create_sync,
        input_type=SpawnCreateInput,
        output_type=SpawnActionOutput,
        cli_group="spawn",
        cli_name="create",
        mcp_name="spawn_create",
        description="Create and start a spawn.",
    )
)

operation(
    OperationSpec[SpawnListInput, SpawnListOutput](
        name="spawn.list",
        handler=spawn_list,
        sync_handler=spawn_list_sync,
        input_type=SpawnListInput,
        output_type=SpawnListOutput,
        cli_group="spawn",
        cli_name="list",
        mcp_name="spawn_list",
        description="List spawns with optional filters.",
    )
)

operation(
    OperationSpec[SpawnStatsInput, SpawnStatsOutput](
        name="spawn.stats",
        handler=spawn_stats,
        sync_handler=spawn_stats_sync,
        input_type=SpawnStatsInput,
        output_type=SpawnStatsOutput,
        cli_group="spawn",
        cli_name="stats",
        mcp_name="spawn_stats",
        description="Show aggregate spawn statistics with optional filters.",
    )
)

operation(
    OperationSpec[SpawnShowInput, SpawnDetailOutput](
        name="spawn.show",
        handler=spawn_show,
        sync_handler=spawn_show_sync,
        input_type=SpawnShowInput,
        output_type=SpawnDetailOutput,
        cli_group="spawn",
        cli_name="show",
        mcp_name="spawn_show",
        description="Show spawn details.",
    )
)

operation(
    OperationSpec[SpawnContinueInput, SpawnActionOutput](
        name="spawn.continue",
        handler=spawn_continue,
        sync_handler=spawn_continue_sync,
        input_type=SpawnContinueInput,
        output_type=SpawnActionOutput,
        cli_group="spawn",
        cli_name="continue",
        mcp_name="spawn_continue",
        description="Continue a previous spawn.",
    )
)

operation(
    OperationSpec[SpawnWaitInput, SpawnWaitMultiOutput](
        name="spawn.wait",
        handler=spawn_wait,
        sync_handler=spawn_wait_sync,
        input_type=SpawnWaitInput,
        output_type=SpawnWaitMultiOutput,
        cli_group="spawn",
        cli_name="wait",
        mcp_name="spawn_wait",
        description="Wait until a spawn reaches terminal status.",
    )
)
