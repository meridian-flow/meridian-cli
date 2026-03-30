"""CLI command handlers for spawn.* operations."""

from collections.abc import Callable
from functools import partial
from typing import Annotated, Any, cast

from cyclopts import App, Parameter

from meridian.cli.main import agent_mode_enabled, current_output_sink, get_global_options
from meridian.cli.registration import register_manifest_cli_group
from meridian.lib.core.domain import SpawnStatus
from meridian.lib.ops.reference import resolve_session_reference
from meridian.lib.ops.runtime import resolve_runtime_root_and_config
from meridian.lib.ops.spawn.api import (
    SpawnActionOutput,
    SpawnCancelInput,
    SpawnContinueInput,
    SpawnCreateInput,
    SpawnListInput,
    SpawnShowInput,
    SpawnStatsInput,
    SpawnWaitInput,
    SpawnWrittenFilesInput,
    spawn_cancel_sync,
    spawn_continue_sync,
    spawn_create_sync,
    spawn_files_sync,
    spawn_list_sync,
    spawn_show_sync,
    spawn_stats_sync,
    spawn_wait_sync,
)
from meridian.lib.ops.spawn.log import SpawnLogInput, spawn_log_sync
from meridian.lib.ops.spawn.plan import SessionContinuation

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


def _parse_csv_list(raw: str | None, *, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    trimmed = raw.strip()
    if not trimmed:
        return ()

    parts = [part.strip() for part in trimmed.split(",")]
    if any(not part for part in parts):
        raise ValueError(
            f"Invalid value for '{field_name}': expected comma-separated non-empty names."
        )
    return tuple(parts)


def _missing_fork_session_error(source_ref: str) -> str:
    if source_ref.startswith("p") and source_ref[1:].isdigit():
        return f"Spawn '{source_ref}' has no recorded session — cannot continue/fork."
    return f"Session '{source_ref}' has no recorded harness session — cannot continue/fork."


def _spawn_create(
    emit: Any,
    prompt: Annotated[
        str,
        Parameter(name=["--prompt", "-p"], help="Prompt text for the spawn."),
    ] = "",
    *passthrough: Annotated[
        str,
        Parameter(
            help=(
                "Extra arguments passed directly to the harness (place after --). "
                "Known limitation: meridian still consumes "
                "--json/--format/--config/--yes/--no-input/--human even after --."
            ),
        ),
    ],
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
        Parameter(
            name=["--model", "-m"],
            help="Model id or alias. Overrides agent profile and config defaults.",
        ),
    ] = "",
    references: Annotated[
        tuple[str, ...],
        Parameter(
            name=["--file", "-f"],
            help="Reference files to include in prompt context (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
    context_from: Annotated[
        tuple[str, ...],
        Parameter(
            name=["--from"],
            help="Include context (report, files) from a prior spawn or session (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
    agent: Annotated[
        str | None,
        Parameter(name=["--agent", "-a"], help="Agent profile name to execute."),
    ] = None,
    skills: Annotated[
        str | None,
        Parameter(
            name=["--skills", "-s"],
            help="Comma-separated ad-hoc skills to load. Merged with agent profile skills.",
        ),
    ] = None,
    desc: Annotated[
        str,
        Parameter(name="--desc", help="Short description for the spawn."),
    ] = "",
    work: Annotated[
        str,
        Parameter(name="--work", help="Associate the spawn with a work item id."),
    ] = "",
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
        Parameter(
            name="--stream", help="Stream raw harness output to terminal (debug only).", show=False
        ),
    ] = False,
    background: Annotated[
        bool,
        Parameter(
            name="--background",
            help="Run in background and return immediately with spawn ID.",
        ),
    ] = False,
    timeout: Annotated[
        float | None,
        Parameter(
            name="--timeout",
            help="Maximum runtime in minutes before spawn timeout.",
        ),
    ] = None,
    approval: Annotated[
        str | None,
        Parameter(
            name="--approval",
            help="Approval mode: default, confirm, auto, yolo. Overrides agent profile.",
        ),
    ] = None,
    autocompact: Annotated[
        int | None,
        Parameter(
            name="--autocompact",
            help="Autocompact threshold percentage (1-100). Overrides agent profile.",
        ),
    ] = None,
    thinking: Annotated[
        str | None,
        Parameter(
            name="--thinking",
            help="Thinking budget: low, medium, high, xhigh. Overrides agent profile.",
        ),
    ] = None,
    sandbox: Annotated[
        str | None,
        Parameter(
            name="--sandbox",
            help=(
                "Sandbox mode: read-only, workspace-write, full-access, "
                "danger-full-access, unrestricted. Overrides agent profile."
            ),
        ),
    ] = None,
    harness: Annotated[
        str | None,
        Parameter(
            name="--harness",
            help="Harness id to use. Overrides agent profile.",
        ),
    ] = None,
    yolo: Annotated[
        bool,
        Parameter(
            name="--yolo",
            help="Skip all harness safety prompts and sandboxing.",
        ),
    ] = False,
    continue_from: Annotated[
        str | None,
        Parameter(name="--continue", help="Continue from a previous spawn ID."),
    ] = None,
    fork_from: Annotated[
        str | None,
        Parameter(name="--fork", help="Fork from a session or spawn reference."),
    ] = None,
) -> None:
    # Resolve --yolo / --approval interaction.
    if yolo and approval is not None:
        raise ValueError(
            "Cannot use --yolo with --approval (--yolo is shorthand for --approval yolo)."
        )
    resolved_approval = approval if approval is not None else ("yolo" if yolo else None)
    parsed_skills = _parse_csv_list(skills, field_name="skills")
    resolved_continue_from = (continue_from or "").strip() or None
    resolved_fork_from = (fork_from or "").strip() or None

    if resolved_fork_from is not None and resolved_continue_from is not None:
        raise ValueError("Cannot combine --fork with --continue.")

    if resolved_fork_from is not None:
        if context_from:
            raise ValueError("Cannot combine --fork with --from (MVP limitation).")

        repo_root, _ = resolve_runtime_root_and_config(None)
        resolved_reference = resolve_session_reference(repo_root, resolved_fork_from)
        if resolved_reference.missing_harness_session_id:
            raise ValueError(_missing_fork_session_error(resolved_fork_from))

        requested_harness = (harness or "").strip() or None
        source_harness = (resolved_reference.harness or "").strip() or None
        if (
            requested_harness is not None
            and source_harness is not None
            and requested_harness != source_harness
        ):
            raise ValueError(
                "Cannot fork across harnesses: "
                f"source is '{source_harness}', target is '{requested_harness}'."
            )

        requested_model = model.strip()
        requested_agent = (agent or "").strip() or None
        requested_work = work.strip()

        inherited_skills = (
            resolved_reference.source_skills
            if skills is None and requested_agent is None
            else parsed_skills
        )

        result = spawn_create_sync(
            SpawnCreateInput(
                prompt=prompt,
                model=requested_model or (resolved_reference.source_model or ""),
                files=references,
                template_vars=template_vars,
                agent=requested_agent or resolved_reference.source_agent,
                skills=inherited_skills,
                desc=desc,
                work=requested_work or (resolved_reference.source_work_id or ""),
                dry_run=dry_run,
                verbose=verbose,
                quiet=quiet,
                stream=stream,
                background=background,
                timeout=timeout,
                approval=resolved_approval,
                autocompact=autocompact,
                thinking=thinking,
                sandbox=sandbox,
                harness=requested_harness or resolved_reference.harness,
                passthrough_args=passthrough,
                session=SessionContinuation(
                    harness_session_id=resolved_reference.harness_session_id,
                    continue_fork=True,
                    forked_from_chat_id=resolved_reference.source_chat_id,
                    source_execution_cwd=resolved_reference.source_execution_cwd,
                ),
                continue_harness_session_id=resolved_reference.harness_session_id,
                continue_harness=resolved_reference.harness,
                continue_source_tracked=resolved_reference.tracked,
                continue_source_ref=resolved_fork_from,
                continue_fork=True,
                forked_from_chat_id=resolved_reference.source_chat_id,
            ),
            sink=current_output_sink(),
        )
    elif resolved_continue_from is not None:
        if context_from:
            raise ValueError("Cannot use --from with --continue")
        result = spawn_continue_sync(
            SpawnContinueInput(
                spawn_id=resolved_continue_from,
                prompt=prompt,
                model=model,
                agent=agent,
                skills=parsed_skills,
                dry_run=dry_run,
                timeout=timeout,
                passthrough_args=passthrough,
                approval=resolved_approval,
            ),
            sink=current_output_sink(),
        )
    else:
        result = spawn_create_sync(
            SpawnCreateInput(
                prompt=prompt,
                model=model,
                files=references,
                context_from=context_from,
                template_vars=template_vars,
                agent=agent,
                skills=parsed_skills,
                desc=desc,
                work=work,
                dry_run=dry_run,
                verbose=verbose,
                quiet=quiet,
                stream=stream,
                background=background,
                timeout=timeout,
                approval=resolved_approval,
                autocompact=autocompact,
                thinking=thinking,
                sandbox=sandbox,
                harness=harness,
                passthrough_args=passthrough,
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
    view: Annotated[
        str,
        Parameter(
            name="--view",
            help=(
                "Preset list view: active, all, running, queued, completed, failed, cancelled. "
                "Default: active."
            ),
        ),
    ] = "active",
    all_spawns: Annotated[
        bool,
        Parameter(name="--all", help="Shortcut for --view all."),
    ] = False,
    model: Annotated[
        str | None,
        Parameter(name="--model", help="Filter by model id."),
    ] = None,
    limit: Annotated[
        int, Parameter(name="--limit", help="Maximum number of spawns to return.")
    ] = 20,
    failed: Annotated[
        bool,
        Parameter(name="--failed", help="Shortcut for status=failed."),
    ] = False,
) -> None:
    normalized_status: SpawnStatus | None = None
    normalized_statuses: tuple[SpawnStatus, ...] | None = None
    normalized_view = view.strip().lower() if view.strip() else "active"
    if all_spawns:
        normalized_view = "all"
        if limit == 20:  # user didn't override the default
            limit = 5
    view_map: dict[str, tuple[SpawnStatus, ...]] = {
        "active": ("queued", "running"),
        "all": (),
        "running": ("running",),
        "queued": ("queued",),
        "completed": ("succeeded",),
        "failed": ("failed",),
        "cancelled": ("cancelled",),
    }
    if normalized_view not in view_map:
        supported = ", ".join(view_map)
        raise ValueError(f"Unsupported spawn view '{view}'. Supported views: {supported}")

    if status is not None and status.strip():
        candidate = status.strip()
        if candidate not in {"queued", "running", "succeeded", "failed", "cancelled"}:
            raise ValueError(f"Unsupported spawn status '{status}'")
        normalized_status = cast("SpawnStatus", candidate)
    elif failed:
        normalized_statuses = ("failed",)
    else:
        mapped_statuses = view_map[normalized_view]
        normalized_statuses = mapped_statuses

    result = spawn_list_sync(
        SpawnListInput(
            status=normalized_status,
            statuses=normalized_statuses,
            model=model,
            limit=limit,
            failed=False,
        ),
        sink=current_output_sink(),
    )
    emit(result)


def _spawn_show(
    emit: Any,
    spawn_ids: Annotated[
        tuple[str, ...],
        Parameter(name="spawn_id", help="One or more spawn IDs to show."),
    ],
    report: Annotated[
        bool,
        Parameter(
            name="--report",
            help=(
                "Include full spawn report body in output (default: enabled). "
                "Use --no-report to omit."
            ),
        ),
    ] = True,
) -> None:
    sink = current_output_sink()
    results = tuple(
        spawn_show_sync(
            SpawnShowInput(
                spawn_id=spawn_id,
                include_report_body=report,
            ),
            sink=sink,
        )
        for spawn_id in spawn_ids
    )

    if len(results) == 1:
        emit(results[0])
        return

    if get_global_options().output.format == "json":
        emit(list(results))
        return

    emit("\n\n".join(result.format_text() for result in results))


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
) -> None:
    result = spawn_wait_sync(
        SpawnWaitInput(
            spawn_ids=spawn_ids,
            timeout=timeout,
            verbose=verbose,
            quiet=quiet,
            include_report_body=False,
        ),
        sink=current_output_sink(),
    )
    emit(result)
    if result.any_failed:
        raise SystemExit(1)


def _spawn_files(
    emit: Any,
    spawn_id: str,
    null: Annotated[
        bool,
        Parameter(name=["-0", "--null"], help="Null-delimited output for xargs -0."),
    ] = False,
) -> None:
    result = spawn_files_sync(
        SpawnWrittenFilesInput(spawn_id=spawn_id),
        sink=current_output_sink(),
    )
    if null and result.written_files:
        import sys

        sys.stdout.write("\0".join(result.written_files))
        sys.stdout.flush()
    else:
        emit(result)


def _spawn_log(
    emit: Any,
    spawn_id: Annotated[
        str,
        Parameter(help="Spawn id or reference (e.g. @latest, @last-failed)."),
    ],
    last_n: Annotated[
        int,
        Parameter(name=["--last", "-n"], help="Number of assistant messages to show."),
    ] = 3,
    offset: Annotated[
        int,
        Parameter(
            name="--offset",
            help="Skip this many assistant messages from the end.",
        ),
    ] = 0,
) -> None:
    emit(
        spawn_log_sync(
            SpawnLogInput(
                spawn_id=spawn_id,
                last_n=last_n,
                offset=offset,
            )
        )
    )


def register_spawn_commands(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    """Register spawn CLI commands using registry metadata as source of truth."""

    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "spawn.files": lambda: partial(_spawn_files, emit),
        "spawn.log": lambda: partial(_spawn_log, emit),
        "spawn.list": lambda: partial(_spawn_list, emit),
        "spawn.stats": lambda: partial(_spawn_stats, emit),
        "spawn.show": lambda: partial(_spawn_show, emit),
        "spawn.cancel": lambda: partial(_spawn_cancel, emit),
        "spawn.wait": lambda: partial(_spawn_wait, emit),
    }
    return register_manifest_cli_group(
        app,
        group="spawn",
        handlers=handlers,
        emit=emit,
        default_handler=partial(_spawn_create, emit),
    )
