"""CLI command handlers for run.* operations."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Annotated, Any, cast

from cyclopts import App, Parameter

from meridian.lib.domain import RunStatus
from meridian.lib.ops.registry import get_all_operations
from meridian.lib.ops.run import (
    RunActionOutput,
    RunContinueInput,
    RunCreateInput,
    RunListInput,
    RunShowInput,
    RunStatsInput,
    RunWaitInput,
    run_continue_sync,
    run_create_sync,
    run_list_sync,
    run_show_sync,
    run_stats_sync,
    run_wait_sync,
)

Emitter = Callable[[Any], None]


def _run_create_exit_code(result: RunActionOutput) -> int:
    if result.exit_code is not None:
        return result.exit_code
    if result.status in {"succeeded", "running", "dry-run"}:
        return 0
    return 1


def _run_create(
    emit: Any,
    prompt: Annotated[
        str,
        Parameter(name=["--prompt", "-p"], help="Prompt text for the run."),
    ] = "",
    model: Annotated[
        str,
        Parameter(name=["--model", "-m"], help="Model id or alias to use."),
    ] = "",
    skill_flags: Annotated[
        tuple[str, ...],
        Parameter(
            name=["--skills", "-s"],
            help="Skill names to load (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
    references: Annotated[
        tuple[str, ...],
        Parameter(
            name=["--file", "-f"],
            help="Reference files to include in prompt context (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
    template_vars: Annotated[
        tuple[str, ...],
        Parameter(
            name="--var",
            help="Template variables in KEY=VALUE form (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
    agent: Annotated[
        str | None,
        Parameter(name=["--agent", "-a"], help="Agent profile name to run."),
    ] = None,
    report_path: Annotated[
        str,
        Parameter(name="--report-path", help="Relative path for generated run report."),
    ] = "report.md",
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview without executing harness."),
    ] = False,
    verbose: Annotated[
        bool,
        Parameter(name="--verbose", help="Enable verbose run logging."),
    ] = False,
    quiet: Annotated[
        bool,
        Parameter(name="--quiet", help="Reduce non-essential command output."),
    ] = False,
    stream: Annotated[
        bool,
        Parameter(name="--stream", help="Stream harness output while command runs."),
    ] = False,
    background: Annotated[
        bool,
        Parameter(name="--background", help="Submit run and return immediately with run ID."),
    ] = False,
    space: Annotated[
        str | None,
        Parameter(name=["--space-id", "--space"], help="Space id to run within."),
    ] = None,
    timeout_secs: Annotated[
        float | None,
        Parameter(name="--timeout-secs", help="Maximum runtime before run timeout."),
    ] = None,
    permission_tier: Annotated[
        str | None,
        Parameter(name="--permission", help="Permission tier for harness execution."),
    ] = None,
    unsafe: Annotated[
        bool,
        Parameter(name="--unsafe", help="Allow unsafe execution mode."),
    ] = False,
    budget_per_run_usd: Annotated[
        float | None,
        Parameter(name="--budget-per-run-usd", help="Per-run budget cap in USD."),
    ] = None,
    budget_per_space_usd: Annotated[
        float | None,
        Parameter(name="--budget-per-space-usd", help="Space budget cap in USD."),
    ] = None,
    budget_usd: Annotated[
        float | None,
        Parameter(name="--budget-usd", help="Legacy alias for per-run budget in USD."),
    ] = None,
    guardrails: Annotated[
        tuple[str, ...],
        Parameter(
            name="--guardrail",
            help="Guardrail identifiers to enforce (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
    secrets: Annotated[
        tuple[str, ...],
        Parameter(
            name="--secret",
            help="Secret keys to expose to the harness (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
) -> None:
    resolved_budget_per_run = budget_per_run_usd
    if resolved_budget_per_run is None:
        resolved_budget_per_run = budget_usd
    try:
        result = run_create_sync(
            RunCreateInput(
                prompt=prompt,
                model=model,
                skills=skill_flags,
                files=references,
                template_vars=template_vars,
                agent=agent,
                report_path=report_path,
                dry_run=dry_run,
                verbose=verbose,
                quiet=quiet,
                stream=stream,
                background=background,
                space=space,
                timeout_secs=timeout_secs,
                permission_tier=permission_tier,
                unsafe=unsafe,
                budget_per_run_usd=resolved_budget_per_run,
                budget_per_space_usd=budget_per_space_usd,
                guardrails=guardrails,
                secrets=secrets,
            )
        )
    except KeyError as exc:
        message = str(exc.args[0]) if exc.args else "Unknown skills."
        result = RunActionOutput(
            command="run.spawn",
            status="failed",
            error="unknown_skills",
            message=message,
        )
    emit(result)
    exit_code = _run_create_exit_code(result)
    if exit_code != 0:
        raise SystemExit(exit_code)


def _run_list(
    emit: Any,
    space: Annotated[
        str | None,
        Parameter(name=["--space-id", "--space"], help="Only list runs from this space."),
    ] = None,
    status: Annotated[
        str | None,
        Parameter(
            name="--status",
            help="Filter by status: queued, running, succeeded, failed, cancelled.",
        ),
    ] = None,
    model: Annotated[
        str | None,
        Parameter(name="--model", help="Filter by model id."),
    ] = None,
    limit: Annotated[int, Parameter(name="--limit", help="Maximum number of runs to return.")] = 20,
    no_space: Annotated[
        bool,
        Parameter(name="--no-space", help="Only include runs without a space."),
    ] = False,
    failed: Annotated[
        bool,
        Parameter(name="--failed", help="Shortcut for status=failed."),
    ] = False,
) -> None:
    normalized_status: RunStatus | None = None
    if status is not None and status.strip():
        candidate = status.strip()
        if candidate not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError(f"Unsupported run status '{status}'")
        normalized_status = cast("RunStatus", candidate)

    result = run_list_sync(
        RunListInput(
            space=space,
            status=normalized_status,
            model=model,
            limit=limit,
            no_space=no_space,
            failed=failed,
        )
    )
    emit(result)


def _run_show(
    emit: Any,
    run_id: str,
    report: Annotated[
        bool,
        Parameter(name="--report", help="Include run report content in output."),
    ] = False,
    include_files: Annotated[
        bool,
        Parameter(name="--include-files", help="Include run file metadata in output."),
    ] = False,
) -> None:
    emit(
        run_show_sync(
            RunShowInput(
                run_id=run_id,
                report=report,
                include_files=include_files,
            )
        )
    )


def _run_stats(
    emit: Any,
    session: Annotated[
        str | None,
        Parameter(name="--session", help="Only include runs for this session id."),
    ] = None,
    space: Annotated[
        str | None,
        Parameter(name=["--space-id", "--space"], help="Only include runs from this space."),
    ] = None,
) -> None:
    emit(
        run_stats_sync(
            RunStatsInput(
                session=session,
                space=space,
            )
        )
    )


def _run_continue(
    emit: Any,
    run_id: str,
    prompt: Annotated[
        str,
        Parameter(name=["--prompt", "-p"], help="Follow-up prompt text."),
    ],
    model: Annotated[
        str,
        Parameter(name=["--model", "-m"], help="Override model for continuation."),
    ] = "",
    fork: Annotated[
        bool,
        Parameter(name="--fork", help="Fork a new branch from the source harness session."),
    ] = False,
    timeout_secs: Annotated[
        float | None,
        Parameter(name="--timeout-secs", help="Maximum runtime before timeout."),
    ] = None,
) -> None:
    emit(
        run_continue_sync(
            RunContinueInput(
                run_id=run_id,
                prompt=prompt,
                model=model,
                fork=fork,
                timeout_secs=timeout_secs,
            )
        )
    )


def _run_wait(
    emit: Any,
    run_ids: Annotated[
        tuple[str, ...],
        Parameter(name="run_id", help="Run IDs to wait for."),
    ],
    timeout_secs: Annotated[
        float | None,
        Parameter(name="--timeout-secs", help="Maximum wait time before timing out."),
    ] = None,
    report: Annotated[
        bool,
        Parameter(name="--report", help="Include run report content in output."),
    ] = False,
    include_files: Annotated[
        bool,
        Parameter(name="--include-files", help="Include run file metadata in output."),
    ] = False,
) -> None:
    result = run_wait_sync(
        RunWaitInput(
            run_ids=run_ids,
            timeout_secs=timeout_secs,
            report=report,
            include_files=include_files,
        )
    )
    emit(result)
    if result.any_failed:
        raise SystemExit(1)


def register_run_commands(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    """Register run CLI commands using registry metadata as source of truth."""

    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "run.spawn": lambda: partial(_run_create, emit),
        "run.list": lambda: partial(_run_list, emit),
        "run.stats": lambda: partial(_run_stats, emit),
        "run.show": lambda: partial(_run_show, emit),
        "run.continue": lambda: partial(_run_continue, emit),
        "run.wait": lambda: partial(_run_wait, emit),
    }

    registered: set[str] = set()
    descriptions: dict[str, str] = {}

    for op in get_all_operations():
        if op.cli_group != "run" or op.mcp_only:
            continue
        handler_factory = handlers.get(op.name)
        if handler_factory is None:
            raise ValueError(f"No CLI handler registered for operation '{op.name}'")
        handler = handler_factory()
        handler.__name__ = f"cmd_{op.cli_group}_{op.cli_name}"
        app.command(handler, name=op.cli_name, help=op.description)
        registered.add(f"{op.cli_group}.{op.cli_name}")
        descriptions[op.name] = op.description

    app.default(partial(_run_create, emit))
    return registered, descriptions
