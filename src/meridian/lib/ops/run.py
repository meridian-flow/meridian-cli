"""Run operations used by CLI, MCP, and DirectAdapter surfaces."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from pathlib import Path

from meridian.lib.exec.spawn import execute_with_finalization
from meridian.lib.ops._runtime import (
    build_runtime_from_root_and_config,
    resolve_runtime_root_and_config,
    resolve_space_id,
)
from meridian.lib.ops.registry import OperationSpec, operation
from meridian.lib.safety.permissions import (
    build_permission_config,
    validate_permission_config_for_harness,
)
from meridian.lib.state import run_store
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.space import space_file

from . import _run_execute as _run_execute_module
from . import _run_prepare as _run_prepare_module
from ._run_execute import (
    _depth_exceeded_output,
    _depth_limits,
    _execute_run_background,
    _execute_run_blocking,
    logger,
)
from ._run_models import (
    RunActionOutput,
    RunContinueInput,
    RunCreateInput,
    RunDetailOutput,
    RunListEntry,
    RunListInput,
    RunListOutput,
    RunShowInput,
    RunStatsInput,
    RunStatsOutput,
    RunWaitInput,
    RunWaitMultiOutput,
)
from ._run_prepare import _build_create_payload, _validate_create_input
from ._run_query import (
    _detail_from_row,
    _read_run_row,
    _resolve_space_id,
    resolve_run_reference,
    resolve_run_references,
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


def _ensure_space_for_spawn(payload: RunCreateInput) -> tuple[RunCreateInput, str | None]:
    if resolve_space_id(payload.space) is not None:
        return payload, None

    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    created_space = space_file.create_space(repo_root)
    warning = (
        "WARNING [SPACE_AUTO_CREATED]: No MERIDIAN_SPACE_ID set. "
        f"Created space {created_space.id}. Next: set MERIDIAN_SPACE_ID={created_space.id} "
        "for subsequent commands."
    )
    return replace(payload, space=created_space.id), warning


def run_create_sync(payload: RunCreateInput) -> RunActionOutput:
    _run_prepare_module.build_permission_config = build_permission_config
    _run_prepare_module.validate_permission_config_for_harness = (
        validate_permission_config_for_harness
    )
    _run_prepare_module.logger = logger
    _run_execute_module.execute_with_finalization = execute_with_finalization
    _run_execute_module.logger = logger

    payload, preflight_warning = _validate_create_input(payload)

    runtime = None
    if not payload.dry_run:
        resolved_root, config = resolve_runtime_root_and_config(payload.repo_root)
        current_depth, max_depth = _depth_limits(config.max_depth)
        if current_depth >= max_depth:
            return _depth_exceeded_output(current_depth, max_depth)
        runtime = build_runtime_from_root_and_config(resolved_root, config)

    payload, auto_space_warning = _ensure_space_for_spawn(payload)
    combined_warning = _merge_warnings(preflight_warning, auto_space_warning)
    prepared = _build_create_payload(payload, runtime=runtime, preflight_warning=combined_warning)
    if payload.dry_run:
        return RunActionOutput(
            command="run.spawn",
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
        raise RuntimeError("Run runtime was not initialized.")
    if payload.background:
        return _execute_run_background(payload=payload, prepared=prepared, runtime=runtime)
    return _execute_run_blocking(payload=payload, prepared=prepared, runtime=runtime)


async def run_create(payload: RunCreateInput) -> RunActionOutput:
    return await asyncio.to_thread(run_create_sync, payload)


def run_list_sync(payload: RunListInput) -> RunListOutput:
    if payload.no_space:
        return RunListOutput(runs=())

    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    current_space_id, space_dir = _resolve_space_dir(repo_root, payload.space)

    runs = list(reversed(run_store.list_runs(space_dir)))
    if payload.status is not None:
        runs = [row for row in runs if row.status == payload.status]
    if payload.failed:
        runs = [row for row in runs if row.status == "failed"]
    if payload.model is not None and payload.model.strip():
        wanted_model = payload.model.strip()
        runs = [row for row in runs if row.model == wanted_model]

    limit = payload.limit if payload.limit > 0 else 20
    return RunListOutput(
        runs=tuple(
            RunListEntry(
                run_id=row.id,
                status=row.status,
                model=row.model or "",
                space_id=current_space_id,
                duration_secs=row.duration_secs,
                cost_usd=row.total_cost_usd,
            )
            for row in runs[:limit]
        )
    )


async def run_list(payload: RunListInput) -> RunListOutput:
    return await asyncio.to_thread(run_list_sync, payload)


def run_stats_sync(payload: RunStatsInput) -> RunStatsOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    current_space_id, space_dir = _resolve_space_dir(repo_root, payload.space)

    runs = run_store.list_runs(space_dir)
    if payload.session is not None and payload.session.strip():
        wanted_session = payload.session.strip()
        runs = [row for row in runs if row.chat_id == wanted_session]

    models: dict[str, int] = {}
    total_duration_secs = 0.0
    total_cost_usd = 0.0
    succeeded = 0
    failed = 0
    cancelled = 0
    running = 0

    for row in runs:
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

    return RunStatsOutput(
        total_runs=len(runs),
        succeeded=succeeded,
        failed=failed,
        cancelled=cancelled,
        running=running,
        total_duration_secs=total_duration_secs,
        total_cost_usd=total_cost_usd,
        models=models,
    )


async def run_stats(payload: RunStatsInput) -> RunStatsOutput:
    return await asyncio.to_thread(run_stats_sync, payload)


def run_show_sync(payload: RunShowInput) -> RunDetailOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = _non_empty_space(payload.space)
    run_id = resolve_run_reference(repo_root, payload.run_id, resolved_space)
    row = _read_run_row(repo_root, run_id, resolved_space)
    if row is None:
        raise ValueError(f"Run '{run_id}' not found")
    return _detail_from_row(
        repo_root=repo_root,
        row=row,
        report=payload.report,
        include_files=payload.include_files,
        space_id=resolved_space,
    )


async def run_show(payload: RunShowInput) -> RunDetailOutput:
    return await asyncio.to_thread(run_show_sync, payload)


def _run_is_terminal(status: str) -> bool:
    return status not in {"queued", "running"}


def _normalize_wait_run_ids(payload: RunWaitInput) -> tuple[str, ...]:
    candidates: list[str] = []
    for run_id in payload.run_ids:
        normalized = run_id.strip()
        if normalized:
            candidates.append(normalized)

    if payload.run_id is not None and payload.run_id.strip():
        candidates.append(payload.run_id.strip())

    deduped = tuple(dict.fromkeys(candidates))
    if not deduped:
        raise ValueError("At least one run_id is required")
    return deduped


def _build_wait_multi_output(results: tuple[RunDetailOutput, ...]) -> RunWaitMultiOutput:
    total_runs = len(results)
    succeeded_runs = sum(1 for run in results if run.status == "succeeded")
    failed_runs = sum(1 for run in results if run.status == "failed")
    cancelled_runs = sum(1 for run in results if run.status == "cancelled")
    any_failed = any(run.status in {"failed", "cancelled"} for run in results)

    run_id: str | None = None
    status: str | None = None
    exit_code: int | None = None
    if total_runs == 1:
        run_id = results[0].run_id
        status = results[0].status
        exit_code = results[0].exit_code

    return RunWaitMultiOutput(
        runs=results,
        total_runs=total_runs,
        succeeded_runs=succeeded_runs,
        failed_runs=failed_runs,
        cancelled_runs=cancelled_runs,
        any_failed=any_failed,
        run_id=run_id,
        status=status,
        exit_code=exit_code,
    )


def run_wait_sync(payload: RunWaitInput) -> RunWaitMultiOutput:
    repo_root, config = resolve_runtime_root_and_config(payload.repo_root)
    resolved_space = _non_empty_space(payload.space)
    run_ids = resolve_run_references(repo_root, _normalize_wait_run_ids(payload), resolved_space)
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

    completed_rows: dict[str, run_store.RunRecord] = {}
    pending: set[str] = set(run_ids)

    while True:
        for run_id in tuple(pending):
            row = _read_run_row(repo_root, run_id, resolved_space)
            if row is None:
                raise ValueError(f"Run '{run_id}' not found")

            if _run_is_terminal(row.status):
                completed_rows[run_id] = row
                pending.remove(run_id)

        if not pending:
            details = tuple(
                _detail_from_row(
                    repo_root=repo_root,
                    row=completed_rows[run_id],
                    report=payload.report,
                    include_files=payload.include_files,
                    space_id=resolved_space,
                )
                for run_id in run_ids
            )
            return _build_wait_multi_output(details)

        if time.monotonic() >= deadline:
            timed_out = "', '".join(sorted(pending))
            raise TimeoutError(f"Timed out waiting for run(s) '{timed_out}'")
        time.sleep(poll)


async def run_wait(payload: RunWaitInput) -> RunWaitMultiOutput:
    return await asyncio.to_thread(run_wait_sync, payload)


def _source_run_for_follow_up(
    payload_run_id: str,
    repo_root: Path,
    space: str | None = None,
) -> tuple[str, run_store.RunRecord]:
    resolved_space = _non_empty_space(space)
    resolved_run_id = resolve_run_reference(repo_root, payload_run_id, resolved_space)
    row = _read_run_row(repo_root, resolved_run_id, resolved_space)
    if row is None:
        raise ValueError(f"Run '{resolved_run_id}' not found")
    return resolved_run_id, row


def _prompt_for_follow_up(source_run: run_store.RunRecord, payload_run_id: str, prompt: str | None) -> str:
    if prompt is not None and prompt.strip():
        return prompt

    existing_prompt = (source_run.prompt or "").strip()
    if not existing_prompt:
        raise ValueError(f"Run '{payload_run_id}' has no stored prompt")
    return existing_prompt


def _model_for_follow_up(source_run: run_store.RunRecord, override_model: str) -> str:
    if override_model.strip():
        return override_model
    return (source_run.model or "").strip()


def _with_command(result: RunActionOutput, command: str) -> RunActionOutput:
    return replace(result, command=command)


def run_continue_sync(payload: RunContinueInput) -> RunActionOutput:
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    resolved_run_id, source_run = _source_run_for_follow_up(
        payload.run_id,
        repo_root,
        payload.space,
    )
    derived_prompt = _prompt_for_follow_up(source_run, resolved_run_id, payload.prompt)
    source_harness = (source_run.harness or "").strip() or None
    source_session_id = (source_run.harness_session_id or "").strip() or None
    create_input = RunCreateInput(
        prompt=derived_prompt,
        model=_model_for_follow_up(source_run, payload.model),
        repo_root=payload.repo_root,
        timeout_secs=payload.timeout_secs,
        space=payload.space,
        continue_harness_session_id=source_session_id,
        continue_harness=source_harness,
        continue_fork=payload.fork,
    )
    result = run_create_sync(create_input)
    return _with_command(result, "run.continue")


async def run_continue(payload: RunContinueInput) -> RunActionOutput:
    return await asyncio.to_thread(run_continue_sync, payload)


operation(
    OperationSpec[RunCreateInput, RunActionOutput](
        name="run.spawn",
        handler=run_create,
        sync_handler=run_create_sync,
        input_type=RunCreateInput,
        output_type=RunActionOutput,
        cli_group="run",
        cli_name="spawn",
        mcp_name="run_spawn",
        description="Create and start a run.",
    )
)

operation(
    OperationSpec[RunListInput, RunListOutput](
        name="run.list",
        handler=run_list,
        sync_handler=run_list_sync,
        input_type=RunListInput,
        output_type=RunListOutput,
        cli_group="run",
        cli_name="list",
        mcp_name="run_list",
        description="List runs with optional filters.",
    )
)

operation(
    OperationSpec[RunStatsInput, RunStatsOutput](
        name="run.stats",
        handler=run_stats,
        sync_handler=run_stats_sync,
        input_type=RunStatsInput,
        output_type=RunStatsOutput,
        cli_group="run",
        cli_name="stats",
        mcp_name="run_stats",
        description="Show aggregate run statistics with optional filters.",
    )
)

operation(
    OperationSpec[RunShowInput, RunDetailOutput](
        name="run.show",
        handler=run_show,
        sync_handler=run_show_sync,
        input_type=RunShowInput,
        output_type=RunDetailOutput,
        cli_group="run",
        cli_name="show",
        mcp_name="run_show",
        description="Show run details.",
    )
)

operation(
    OperationSpec[RunContinueInput, RunActionOutput](
        name="run.continue",
        handler=run_continue,
        sync_handler=run_continue_sync,
        input_type=RunContinueInput,
        output_type=RunActionOutput,
        cli_group="run",
        cli_name="continue",
        mcp_name="run_continue",
        description="Continue a previous run.",
    )
)

operation(
    OperationSpec[RunWaitInput, RunWaitMultiOutput](
        name="run.wait",
        handler=run_wait,
        sync_handler=run_wait_sync,
        input_type=RunWaitInput,
        output_type=RunWaitMultiOutput,
        cli_group="run",
        cli_name="wait",
        mcp_name="run_wait",
        description="Wait until a run reaches terminal status.",
    )
)
