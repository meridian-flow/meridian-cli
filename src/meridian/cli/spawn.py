"""CLI command handlers for spawn.* operations."""


from collections.abc import Callable
from functools import partial
from typing import Annotated, Any, cast

from cyclopts import App, Parameter

from meridian.cli.main import agent_mode_enabled, current_output_sink
from meridian.lib.core.domain import SpawnStatus
from meridian.lib.ops.manifest import get_operations_for_surface
from meridian.lib.ops.spawn.api import (
    SpawnActionOutput,
    SpawnCancelInput,
    SpawnContinueInput,
    SpawnCreateInput,
    SpawnListInput,
    SpawnShowInput,
    SpawnStatsInput,
    SpawnWaitInput,
    spawn_continue_sync,
    spawn_create_sync,
    spawn_cancel_sync,
    spawn_list_sync,
    spawn_show_sync,
    spawn_stats_sync,
    spawn_wait_sync,
)

# In agent mode (MERIDIAN_DEPTH > 0), hide human-only flags from --help.
# Flags still work when passed — show only affects help text.
_HUMAN_ONLY = not agent_mode_enabled()

Emitter = Callable[[Any], None]


def _spawn_create_exit_code(result: SpawnActionOutput) -> int:
    if result.exit_code is not None:
        return result.exit_code
    if result.status in {"succeeded", "running", "dry-run"}:
        return 0
    return 1


def _spawn_create(
    emit: Any,
    prompt: Annotated[
        str,
        Parameter(name=["--prompt", "-p"], help="Prompt text for the spawn."),
    ] = "",
    template_vars: Annotated[
        tuple[str, ...],
        Parameter(
            name="--prompt-var",
            help=(
                "Prompt template variables in KEY=VALUE form (repeatable). "
                "Replaces {{KEY}} during prompt assembly."
            ),
            negative_iterable=(),
        ),
    ] = (),
    model: Annotated[
        str,
        Parameter(name=["--model", "-m"], help="Model id or alias to use."),
    ] = "",
    references: Annotated[
        tuple[str, ...],
        Parameter(
            name=["--file", "-f"],
            help="Reference files to include in prompt context (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
    agent: Annotated[
        str | None,
        Parameter(name=["--agent", "-a"], help="Agent profile name to execute."),
    ] = None,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview without executing harness."),
    ] = False,
    verbose: Annotated[
        bool,
        Parameter(name="--verbose", help="Enable verbose spawn logging.", show=_HUMAN_ONLY),
    ] = False,
    quiet: Annotated[
        bool,
        Parameter(name="--quiet", help="Reduce non-essential command output.", show=_HUMAN_ONLY),
    ] = False,
    stream: Annotated[
        bool,
        Parameter(name="--stream", help="Stream raw harness output to terminal (debug only).", show=False),
    ] = False,
    foreground: Annotated[
        bool,
        Parameter(
            name="--foreground",
            help="Run in foreground and wait for spawn completion.",
        ),
    ] = False,
    timeout: Annotated[
        float | None,
        Parameter(
            name="--timeout",
            help="Maximum runtime in minutes before spawn timeout.",
        ),
    ] = None,
    permission_tier: Annotated[
        str | None,
        Parameter(
            name="--permission",
            help="Tool access tier: read-only, workspace-write, or full-access.",
        ),
    ] = None,
    continue_from: Annotated[
        str | None,
        Parameter(name="--continue", help="Continue from a previous spawn ID."),
    ] = None,
    fork: Annotated[
        bool,
        Parameter(name="--fork", help="Fork a new branch when continuing (use with --continue)."),
    ] = False,
) -> None:
    if continue_from is not None:
        result = spawn_continue_sync(
            SpawnContinueInput(
                spawn_id=continue_from,
                prompt=prompt,
                model=model,
                fork=fork,
                dry_run=dry_run,
                timeout=timeout,
            ),
            sink=current_output_sink(),
        )
    else:
        result = spawn_create_sync(
            SpawnCreateInput(
                prompt=prompt,
                model=model,
                files=references,
                template_vars=template_vars,
                agent=agent,
                dry_run=dry_run,
                verbose=verbose,
                quiet=quiet,
                stream=stream,
                background=not foreground,
                timeout=timeout,
                permission_tier=permission_tier,
            ),
            sink=current_output_sink(),
        )
    emit(result)
    exit_code = _spawn_create_exit_code(result)
    if exit_code != 0:
        raise SystemExit(exit_code)


def _spawn_list(
    emit: Any,
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
    limit: Annotated[int, Parameter(name="--limit", help="Maximum number of spawns to return.")] = 20,
    failed: Annotated[
        bool,
        Parameter(name="--failed", help="Shortcut for status=failed."),
    ] = False,
) -> None:
    normalized_status: SpawnStatus | None = None
    if status is not None and status.strip():
        candidate = status.strip()
        if candidate not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError(f"Unsupported spawn status '{status}'")
        normalized_status = cast("SpawnStatus", candidate)

    result = spawn_list_sync(
        SpawnListInput(
            status=normalized_status,
            model=model,
            limit=limit,
            failed=failed,
        ),
        sink=current_output_sink(),
    )
    emit(result)


def _spawn_show(
    emit: Any,
    spawn_id: str,
    report: Annotated[
        bool,
        Parameter(name="--report", help="Include spawn report content in output."),
    ] = False,
    include_files: Annotated[
        bool,
        Parameter(name="--include-files", help="Include spawn file metadata in output."),
    ] = False,
) -> None:
    emit(
        spawn_show_sync(
            SpawnShowInput(
                spawn_id=spawn_id,
                report=report,
                include_files=include_files,
            ),
            sink=current_output_sink(),
        )
    )


def _spawn_stats(
    emit: Any,
    session: Annotated[
        str | None,
        Parameter(name="--session", help="Only include spawns for this session id."),
    ] = None,
) -> None:
    emit(
        spawn_stats_sync(
            SpawnStatsInput(
                session=session,
            ),
            sink=current_output_sink(),
        )
    )


def _spawn_cancel(
    emit: Any,
    spawn_id: str,
) -> None:
    result = spawn_cancel_sync(
        SpawnCancelInput(
            spawn_id=spawn_id,
        ),
        sink=current_output_sink(),
    )
    emit(result)
    if result.status == "failed":
        raise SystemExit(1)


def _spawn_wait(
    emit: Any,
    spawn_ids: Annotated[
        tuple[str, ...],
        Parameter(name="spawn_id", help="Spawn IDs to wait for."),
    ],
    timeout: Annotated[
        float | None,
        Parameter(
            name="--timeout",
            help="Maximum wait time in minutes before timing out.",
        ),
    ] = None,
    verbose: Annotated[
        bool,
        Parameter(name="--verbose", help="Enable verbose wait status output.", show=_HUMAN_ONLY),
    ] = False,
    quiet: Annotated[
        bool,
        Parameter(name="--quiet", help="Suppress wait heartbeat output.", show=_HUMAN_ONLY),
    ] = False,
    report: Annotated[
        bool,
        Parameter(
            name="--report",
            help="Include spawn report in output (default: on). Use --no-report to omit.",
        ),
    ] = True,
    include_files: Annotated[
        bool,
        Parameter(name="--include-files", help="Include spawn file metadata in output."),
    ] = False,
) -> None:
    result = spawn_wait_sync(
        SpawnWaitInput(
            spawn_ids=spawn_ids,
            timeout=timeout,
            verbose=verbose,
            quiet=quiet,
            report=report,
            include_files=include_files,
        ),
        sink=current_output_sink(),
    )
    emit(result)
    if result.any_failed:
        raise SystemExit(1)


def register_spawn_commands(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    """Register spawn CLI commands using registry metadata as source of truth."""

    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "spawn.list": lambda: partial(_spawn_list, emit),
        "spawn.stats": lambda: partial(_spawn_stats, emit),
        "spawn.show": lambda: partial(_spawn_show, emit),
        "spawn.cancel": lambda: partial(_spawn_cancel, emit),
        "spawn.wait": lambda: partial(_spawn_wait, emit),
    }

    registered: set[str] = set()
    descriptions: dict[str, str] = {}

    for op in get_operations_for_surface("cli"):
        if op.cli_group != "spawn":
            continue
        handler_factory = handlers.get(op.name)
        if handler_factory is None:
            raise ValueError(f"No CLI handler registered for operation '{op.name}'")
        handler = handler_factory()
        handler.__name__ = f"cmd_{op.cli_group}_{op.cli_name}"
        app.command(handler, name=op.cli_name, help=op.description)
        registered.add(f"{op.cli_group}.{op.cli_name}")
        descriptions[op.name] = op.description

    app.default(partial(_spawn_create, emit))
    return registered, descriptions
