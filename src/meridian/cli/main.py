"""Cyclopts CLI entry point for meridian."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Sequence
from contextvars import ContextVar
from pathlib import Path
from typing import Annotated, Literal, cast

from cyclopts import App, Parameter
from pydantic import BaseModel, ConfigDict

from meridian import __version__
from meridian.cli.config_cmd import register_config_commands
from meridian.cli.doctor_cmd import register_doctor_command
from meridian.cli.models_cmd import register_models_commands
from meridian.cli.output import (
    OutputConfig,
    create_sink,
    flush_sink,
    normalize_output_format,
)
from meridian.cli.output import emit as emit_output
from meridian.cli.report_cmd import register_report_commands
from meridian.cli.skills_cmd import register_skills_commands
from meridian.cli.space import register_space_commands
from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.harness.materialize import cleanup_materialized
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.harness.session_detection import infer_harness_from_untracked_session_ref
from meridian.lib.ops.spawn.api import SpawnActionOutput
from meridian.lib.core.sink import OutputSink
from meridian.lib.ops.space import SpaceActionOutput
from meridian.lib.space.launch import SpaceLaunchRequest, cleanup_orphaned_locks, launch_primary
from meridian.lib.state.session_store import (
    cleanup_stale_sessions,
    get_last_session,
    resolve_session_ref,
)
from meridian.lib.state.space_store import (
    SpaceRecord,
    create_space as create_space_record,
    get_space as get_space_record,
    list_spaces as list_space_records,
)
from meridian.lib.space.summary import generate_space_summary
from meridian.lib.state.paths import resolve_all_spaces_dir, resolve_space_dir
from meridian.lib.core.types import SpaceId
from meridian.server.main import run_server

logger = logging.getLogger(__name__)

_AGENT_ROOT_HELP = """Usage: meridian COMMAND [ARGS]

Multi-agent orchestration across Claude, Codex, and OpenCode.

Quick start:
  meridian spawn -m MODEL -p "prompt"   Create a subagent run
  meridian spawn wait ID                  Wait for results
  meridian models list                   See available models

Run 'meridian spawn -h' for full usage.

Commands:
  spawn   Create and manage subagent runs
  report  Manage spawn reports
  models  Model catalog
  skills  Skills catalog
"""


class GlobalOptions(BaseModel):
    """Top-level options that apply to all commands."""
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    output: OutputConfig
    config_file: str | None = None
    yes: bool = False
    no_input: bool = False
    output_explicit: bool = False
    sink: OutputSink | None = None


_GLOBAL_OPTIONS: ContextVar[GlobalOptions | None] = ContextVar("_GLOBAL_OPTIONS", default=None)


class _ResolvedContinueTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    space: SpaceRecord
    harness_session_id: str | None
    harness: str | None
    warning: str | None = None


def _space_sort_key(record: SpaceRecord) -> tuple[str, int, str]:
    suffix = record.id[1:] if record.id.startswith("s") else ""
    numeric_id = int(suffix) if suffix.isdigit() else -1
    return (record.created_at, numeric_id, record.id)


def get_global_options() -> GlobalOptions:
    """Return parsed global options for current command."""

    default = GlobalOptions(output=OutputConfig(format="text"))
    return _GLOBAL_OPTIONS.get() or default


def _resolve_sink(opts: GlobalOptions | None) -> tuple[OutputSink, bool]:
    if opts is not None and opts.sink is not None:
        return opts.sink, False
    if opts is None:
        return create_sink(OutputConfig(format="text")), True
    return create_sink(
        opts.output,
        agent_mode=_agent_sink_enabled(output_explicit=opts.output_explicit),
    ), True


def current_output_sink() -> OutputSink:
    sink, _ = _resolve_sink(_GLOBAL_OPTIONS.get())
    return sink


def emit(payload: object) -> None:
    """Write command output using current output format settings."""
    options = get_global_options()
    sink, flush_after = _resolve_sink(options)
    if isinstance(payload, SpawnActionOutput):
        wire = payload.to_wire()
        emit_output(wire, sink=sink)
        if flush_after:
            flush_sink(sink)
        return
    emit_output(payload, sink=sink)
    if flush_after:
        flush_sink(sink)


def _extract_global_options(argv: Sequence[str]) -> tuple[list[str], GlobalOptions]:
    json_mode = False
    output_format: str | None = None
    config_file: str | None = None
    yes = False
    no_input = False
    output_explicit = False
    cleaned: list[str] = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            json_mode = True
            output_explicit = True
            i += 1
            continue
        if arg == "--no-json":
            output_explicit = True
            i += 1
            continue
        if arg == "--format":
            if i + 1 >= len(argv):
                raise SystemExit("--format requires a value")
            output_format = argv[i + 1]
            output_explicit = True
            i += 2
            continue
        if arg.startswith("--format="):
            output_format = arg.partition("=")[2]
            output_explicit = True
            i += 1
            continue
        if arg == "--config":
            if i + 1 >= len(argv):
                raise SystemExit("--config requires a value")
            config_file = argv[i + 1].strip()
            if not config_file:
                raise SystemExit("--config requires a non-empty value")
            i += 2
            continue
        if arg.startswith("--config="):
            config_file = arg.partition("=")[2].strip()
            if not config_file:
                raise SystemExit("--config requires a non-empty value")
            i += 1
            continue
        if arg == "--yes":
            yes = True
            i += 1
            continue
        if arg == "--no-yes":
            i += 1
            continue
        if arg == "--no-input":
            no_input = True
            i += 1
            continue
        if arg == "--no-no-input":
            i += 1
            continue

        cleaned.append(arg)
        i += 1

    resolved = normalize_output_format(
        requested=output_format,
        json_mode=json_mode,
    )
    return cleaned, GlobalOptions(
        output=OutputConfig(format=resolved),
        config_file=config_file,
        yes=yes,
        no_input=no_input,
        output_explicit=output_explicit,
    )


def _extract_human_flag(argv: Sequence[str]) -> tuple[list[str], bool]:
    force_human = False
    cleaned: list[str] = []
    for arg in argv:
        if arg == "--human":
            force_human = True
            continue
        cleaned.append(arg)
    return cleaned, force_human


def agent_mode_enabled() -> bool:
    return bool(os.getenv("MERIDIAN_SPACE_ID", "").strip())


def _agent_sink_enabled(*, output_explicit: bool) -> bool:
    if output_explicit or not agent_mode_enabled():
        return False
    raw_depth = os.getenv("MERIDIAN_DEPTH", "").strip()
    if not raw_depth:
        return False
    try:
        return int(raw_depth) > 0
    except ValueError:
        return False


app = App(
    name="meridian",
    help=(
        "Multi-agent orchestration across Claude, Codex, and OpenCode.\n\n"
        'Run "meridian spawn -h" for subagent usage.'
    ),
    version=__version__,
    help_formatter="plain",
)
_COMMAND_TREE_APP = app


@app.default
def root(
    json_mode: Annotated[
        bool,
        Parameter(name="--json", help="Emit command output as JSON.", show=False),
    ] = False,
    output_format: Annotated[
        str | None,
        Parameter(name="--format", help="Set output format: text or json."),
    ] = None,
    config_file: Annotated[
        str | None,
        Parameter(name="--config", help="Path to a user config TOML overlay."),
    ] = None,
    yes: Annotated[
        bool,
        Parameter(name="--yes", help="Auto-approve prompts when supported.", show=False),
    ] = False,
    no_input: Annotated[
        bool,
        Parameter(
            name="--no-input",
            help="Disable interactive prompts and fail if input is needed.",
            show=False,
        ),
    ] = False,
    new: Annotated[
        bool,
        Parameter(name="--new", help="Force create a new space before launch."),
    ] = False,
    space: Annotated[
        str | None,
        Parameter(name="--space", help="Use an explicit existing space id."),
    ] = None,
    continue_ref: Annotated[
        str | None,
        Parameter(name="--continue", help="Continue a previous session reference."),
    ] = None,
    model: Annotated[
        str,
        Parameter(name="--model", help="Model id or alias for primary harness."),
    ] = "",
    harness: Annotated[
        str | None,
        Parameter(name="--harness", help="Force harness id (claude, codex, or opencode)."),
    ] = None,
    agent: Annotated[
        str | None,
        Parameter(name=["--agent", "-a"], help="Agent profile name for the primary agent."),
    ] = None,
    permission_tier: Annotated[
        str | None,
        Parameter(
            name="--permission",
            help="Tool access tier: read-only, workspace-write, or full-access.",
        ),
    ] = None,
    approval: Annotated[
        Literal["confirm", "auto"],
        Parameter(
            name="--approval",
            help="Approval mode: confirm (ask before acting) or auto (auto-approve all).",
        ),
    ] = "confirm",
    yolo: Annotated[
        bool,
        Parameter(
            name="--yolo",
            help="Shortcut for --permission full-access --approval auto.",
        ),
    ] = False,
    autocompact: Annotated[
        int | None,
        Parameter(name="--autocompact", help="Auto-compact threshold in messages."),
    ] = None,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview launch command without starting harness."),
    ] = False,
    harness_args: Annotated[
        tuple[str, ...],
        Parameter(
            name="--harness-arg",
            help="Additional harness arguments (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
) -> None:
    """Resolve/start a space and launch the primary harness."""

    if _GLOBAL_OPTIONS.get() is None:
        resolved = normalize_output_format(
            requested=output_format,
            json_mode=json_mode,
        )
        _GLOBAL_OPTIONS.set(
            GlobalOptions(
                output=OutputConfig(format=resolved),
                config_file=config_file,
                yes=yes,
                no_input=no_input,
            )
        )

    _run_primary_launch(
        new=new,
        space=space,
        continue_ref=continue_ref,
        model=model,
        harness=harness,
        agent=agent,
        permission_tier=permission_tier,
        approval=approval,
        yolo=yolo,
        autocompact=autocompact,
        dry_run=dry_run,
        harness_args=harness_args,
    )


@app.command(name="serve")
def serve() -> None:
    """Start FastMCP server on stdio."""

    run_server()


space_app = App(name="space", help="Space lifecycle commands", help_formatter="plain")
spawn_app = App(
    name="spawn",
    help=(
        "Run subagents with a model and prompt. Returns immediately with a spawn_id.\n"
        "Spawns run in background by default."
    ),
    help_epilogue=(
        "Examples:\n"
        '  meridian spawn -m gpt-5.3-codex -p "Fix the bug in auth.py"\n'
        '  meridian spawn -m claude-sonnet-4-6 -p "Review" -f src/main.py\n'
        "  meridian spawn wait SPAWN_ID\n"
    ),
    help_formatter="plain",
)
report_app = App(name="report", help="Report management commands", help_formatter="plain")
skills_app = App(name="skills", help="Skills catalog commands", help_formatter="plain")
models_app = App(name="models", help="Model catalog commands", help_formatter="plain")
config_app = App(name="config", help="Repository config commands", help_formatter="plain")

completion_app = App(name="completion", help="Shell completion helpers", help_formatter="plain")


app.command(space_app, name="space")
app.command(spawn_app, name="spawn")
app.command(report_app, name="report")
app.command(skills_app, name="skills")
app.command(models_app, name="models")
app.command(config_app, name="config")
app.command(completion_app, name="completion")


def _emit_completion(shell: str) -> None:
    normalized = _normalize_completion_shell(shell)
    print(app.generate_completion(shell=normalized))


def _normalize_completion_shell(shell: str) -> Literal["bash", "zsh", "fish"]:
    normalized = shell.strip().lower()
    if normalized not in {"bash", "zsh", "fish"}:
        raise ValueError("Unsupported shell. Expected one of: bash, zsh, fish.")
    return cast("Literal['bash', 'zsh', 'fish']", normalized)


@completion_app.command(name="bash")
def completion_bash() -> None:
    _emit_completion("bash")


@completion_app.command(name="zsh")
def completion_zsh() -> None:
    _emit_completion("zsh")


@completion_app.command(name="fish")
def completion_fish() -> None:
    _emit_completion("fish")


@completion_app.command(name="install")
def completion_install(
    shell: Annotated[
        str,
        Parameter(name="--shell", help="Shell to generate completion for (bash, zsh, or fish)."),
    ] = "bash",
    output: Annotated[
        str | None,
        Parameter(name="--output", help="Optional file path where completion script is written."),
    ] = None,
    add_to_startup: Annotated[
        bool,
        Parameter(name="--add-to-startup", help="Append completion setup to shell startup files."),
    ] = False,
) -> None:
    normalized_shell = _normalize_completion_shell(shell)
    destination = app.install_completion(
        shell=normalized_shell,
        output=Path(output).expanduser() if output is not None else None,
        add_to_startup=add_to_startup,
    )
    emit({"shell": normalized_shell, "path": destination.as_posix()})


def _start_space_record(
    *,
    repo_root: Path,
    force_new: bool,
    explicit_space: str | None,
) -> SpaceRecord:
    if force_new and explicit_space is not None:
        raise ValueError("Cannot combine --new with --space.")

    if explicit_space is not None:
        record = get_space_record(repo_root, explicit_space)
        if record is None:
            raise ValueError(f"Space '{explicit_space}' not found")
        return record

    if force_new:
        return create_space_record(repo_root)

    spaces = list_space_records(repo_root)
    if spaces:
        return max(spaces, key=_space_sort_key)
    return create_space_record(repo_root)


def _run_primary_launch(
    *,
    new: bool,
    space: str | None,
    continue_ref: str | None,
    model: str,
    harness: str | None,
    agent: str | None,
    permission_tier: str | None,
    approval: str,
    yolo: bool,
    autocompact: int | None,
    dry_run: bool,
    harness_args: tuple[str, ...],
) -> None:
    """Shared primary launch flow for root command entry."""

    repo_root = resolve_repo_root()
    explicit_space = space.strip() if space is not None and space.strip() else None
    normalized_continue_ref = continue_ref.strip() if continue_ref is not None else ""
    resume_target = normalized_continue_ref if normalized_continue_ref else None
    resolved_permission_tier = permission_tier
    resolved_approval = approval
    if yolo:
        resolved_permission_tier = "full-access"
        resolved_approval = "auto"

    selected: SpaceRecord
    continue_harness_session_id: str | None = None
    continue_harness: str | None = None
    continue_warning: str | None = None
    fresh = True
    if resume_target is not None:
        if new:
            raise ValueError("Cannot combine --continue with --new.")
        if model.strip():
            raise ValueError("Cannot combine --continue with --model.")
        if harness is not None and harness.strip():
            raise ValueError("Cannot combine --continue with --harness.")
        if agent is not None and agent.strip():
            raise ValueError("Cannot combine --continue with --agent.")
        resolved_continue = _resolve_continue_target(
            repo_root=repo_root,
            continue_ref=resume_target,
            explicit_space=explicit_space,
        )
        selected = resolved_continue.space
        continue_harness_session_id = resolved_continue.harness_session_id
        continue_harness = resolved_continue.harness
        continue_warning = resolved_continue.warning
        fresh = False
    else:
        selected = _start_space_record(
            repo_root=repo_root,
            force_new=new,
            explicit_space=explicit_space,
        )
    summary_path = generate_space_summary(
        repo_root=repo_root,
        space_id=SpaceId(selected.id),
    )

    launch_result = launch_primary(
        repo_root=repo_root,
        request=SpaceLaunchRequest(
            space_id=SpaceId(selected.id),
            model=model,
            harness=continue_harness if resume_target is not None else harness,
            agent=agent,
            autocompact=autocompact,
            passthrough_args=harness_args,
            fresh=fresh,
            pinned_context="",
            dry_run=dry_run,
            permission_tier=resolved_permission_tier,
            approval=resolved_approval,
            continue_harness_session_id=continue_harness_session_id,
        ),
        harness_registry=get_default_harness_registry(),
    )

    emit(
        SpaceActionOutput(
            space_id=selected.id,
            message=(
                "Resume dry-run."
                if dry_run and resume_target is not None
                else (
                    "Launch dry-run."
                    if dry_run
                    else ("Session resumed." if resume_target is not None else "Session finished.")
                )
            ),
            exit_code=launch_result.exit_code,
            command=launch_result.command if dry_run else (),
            lock_path=launch_result.lock_path.as_posix(),
            summary_path=summary_path.as_posix(),
            continue_ref=launch_result.continue_ref,
            resume_command=(
                f"meridian --continue {launch_result.continue_ref}"
                if launch_result.continue_ref is not None
                else None
            ),
            warning=continue_warning,
        )
    )


def _resolve_continue_target(
    *,
    repo_root: Path,
    continue_ref: str,
    explicit_space: str | None,
) -> _ResolvedContinueTarget:
    normalized = continue_ref.strip()
    if not normalized:
        raise ValueError("--continue requires a non-empty session reference.")
    inferred_harness = infer_harness_from_untracked_session_ref(repo_root, normalized)

    all_spaces = list_space_records(repo_root)
    matches: list[tuple[SpaceRecord, str | None, str | None]] = []
    for record in all_spaces:
        space_dir = resolve_space_dir(repo_root, record.id)
        session = resolve_session_ref(space_dir, normalized)
        if session is None:
            continue
        harness_session_id = session.harness_session_id.strip() or None
        harness = inferred_harness or (session.harness.strip() or None)
        matches.append((record, harness_session_id, harness))

    def _last_space_harness(space_id: str) -> str | None:
        record = get_last_session(resolve_space_dir(repo_root, space_id))
        if record is None:
            return None
        normalized_harness = record.harness.strip()
        return normalized_harness or None

    if explicit_space is not None:
        selected = get_space_record(repo_root, explicit_space)
        if selected is None:
            raise ValueError(f"Space '{explicit_space}' not found")

        explicit_match = next((item for item in matches if item[0].id == selected.id), None)
        if explicit_match is not None:
            return _ResolvedContinueTarget(
                space=selected,
                harness_session_id=explicit_match[1],
                harness=explicit_match[2],
            )

        if matches:
            if len(matches) > 1:
                spaces = ", ".join(sorted(record.id for record, _, _ in matches))
                raise ValueError(
                    f"Session '{normalized}' is ambiguous across spaces ({spaces}). "
                    "Use a more specific session id."
                )
            resolved_space, harness_session_id, harness_id = matches[0]
            return _ResolvedContinueTarget(
                space=resolved_space,
                harness_session_id=harness_session_id,
                harness=harness_id,
                warning=(
                    f"Session '{normalized}' belongs to space '{resolved_space.id}'; "
                    f"ignoring --space '{selected.id}'."
                ),
            )

        if _looks_like_chat_alias(normalized):
            raise ValueError(
                f"Session '{normalized}' not found in space '{selected.id}'."
            )
        return _ResolvedContinueTarget(
            space=selected,
            harness_session_id=normalized,
            harness=(
                inferred_harness
                or _last_space_harness(selected.id)
            ),
            warning=(
                f"Session '{normalized}' is not tracked yet; binding it to space "
                f"'{selected.id}' for this run."
            ),
        )

    if not matches:
        if _looks_like_chat_alias(normalized):
            raise ValueError(f"Session '{normalized}' not found.")
        selected = _start_space_record(
            repo_root=repo_root,
            force_new=False,
            explicit_space=None,
        )
        return _ResolvedContinueTarget(
            space=selected,
            harness_session_id=normalized,
            harness=(
                inferred_harness
                or _last_space_harness(selected.id)
            ),
            warning=(
                f"Session '{normalized}' is not tracked yet; binding it to space "
                f"'{selected.id}' for this run."
            ),
        )
    if len(matches) > 1:
        spaces = ", ".join(sorted(record.id for record, _, _ in matches))
        raise ValueError(
            f"Session '{normalized}' is ambiguous across spaces ({spaces}). "
            "Use --space to disambiguate."
        )
    resolved_space, harness_session_id, harness_id = matches[0]
    return _ResolvedContinueTarget(
        space=resolved_space,
        harness_session_id=harness_session_id,
        harness=harness_id,
    )


def _looks_like_chat_alias(value: str) -> bool:
    return value.startswith("c") and value[1:].isdigit()


@app.command(name="init")
def init_alias() -> None:
    """Alias for config init."""

    config_app(["init"])


_REGISTERED_CLI_COMMANDS: set[str] = set()
_REGISTERED_CLI_DESCRIPTIONS: dict[str, str] = {}


def _register_group_commands() -> None:
    # Import lazily to avoid a circular import with meridian.cli.spawn, which
    # reads agent-mode state from this module during import.
    from meridian.cli.spawn import register_spawn_commands

    modules = (
        register_space_commands(space_app, emit),
        register_spawn_commands(spawn_app, emit),
        register_report_commands(report_app, emit),
        register_skills_commands(skills_app, emit),
        register_models_commands(models_app, emit),
        register_config_commands(config_app, emit),
        register_doctor_command(app, emit),
    )
    for commands, descriptions in modules:
        _REGISTERED_CLI_COMMANDS.update(commands)
        _REGISTERED_CLI_DESCRIPTIONS.update(descriptions)


def get_registered_cli_commands() -> set[str]:
    """Expose CLI operation command names for parity tests."""

    return set(_REGISTERED_CLI_COMMANDS)


def get_registered_cli_descriptions() -> dict[str, str]:
    """Expose CLI descriptions for parity tests."""

    return dict(_REGISTERED_CLI_DESCRIPTIONS)


def _operation_error_message(exc: Exception) -> str:
    if isinstance(exc, KeyError) and exc.args:
        return str(exc.args[0])
    message = str(exc).strip()
    if message:
        return message
    return exc.__class__.__name__



def _emit_error(message: str, *, exit_code: int = 1) -> None:
    """Emit an error via the active sink and exit."""
    sink, flush_after = _resolve_sink(_GLOBAL_OPTIONS.get())
    sink.error(message, exit_code=exit_code)
    if flush_after:
        flush_sink(sink)
    raise SystemExit(exit_code)

_TOP_LEVEL_VALUE_FLAGS = frozenset(
    {
        "--format",
        "--config",
        "--space",
        "--continue",
        "--model",
        "--harness",
        "--agent",
        "-a",
        "--permission",
        "--approval",
        "--autocompact",
        "--harness-arg",
    }
)
_TOP_LEVEL_BOOL_FLAGS = frozenset(
    {
        "--help",
        "-h",
        "--version",
        "--json",
        "--no-json",
        "--yes",
        "--no-yes",
        "--no-input",
        "--no-no-input",
        "--human",
        "--new",
        "--no-new",
        "--yolo",
        "--no-yolo",
        "--dry-run",
        "--no-dry-run",
    }
)


def _first_positional_token(argv: Sequence[str]) -> str | None:
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            return None
        if not token.startswith("-"):
            return token
        if "=" in token:
            index += 1
            continue
        if token in _TOP_LEVEL_BOOL_FLAGS:
            index += 1
            continue
        if token in _TOP_LEVEL_VALUE_FLAGS:
            index += 2
            continue
        # Unknown option: best effort treat following non-flag as its value
        # to avoid misclassifying that token as an unknown command.
        if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
            index += 2
            continue
        index += 1
    return None


def _top_level_command_names() -> set[str]:
    return {
        name for name in _COMMAND_TREE_APP.resolved_commands() if not name.startswith("-")
    }


def _validate_top_level_command(argv: Sequence[str]) -> None:
    candidate = _first_positional_token(argv)
    if candidate is None:
        return
    if candidate in _top_level_command_names():
        return
    print(f"error: Unknown command: {candidate}", file=sys.stderr)
    raise SystemExit(1)


def _is_root_help_request(argv: Sequence[str]) -> bool:
    if not any(token in {"--help", "-h"} for token in argv):
        return False
    return _first_positional_token(argv) is None


def _print_agent_root_help() -> None:
    print(_AGENT_ROOT_HELP, end="")


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point used by `meridian` and `python -m meridian`."""

    from meridian.lib.core.logging import configure_logging

    args = list(sys.argv[1:] if argv is None else argv)

    # Configure logging early so structlog warnings go to stderr, not stdout.
    # Check if structured output is requested. Only JSON format suppresses
    # human-readable log formatting; "--format text" should not switch logging
    # to JSON mode.
    json_mode = "--json" in args
    if not json_mode and "--format" in args:
        try:
            fmt_idx = args.index("--format")
            fmt_val = args[fmt_idx + 1] if fmt_idx + 1 < len(args) else ""
            json_mode = fmt_val.lower() == "json"
        except (IndexError, ValueError):
            pass
    verbose_count = args.count("--verbose") + args.count("-v")
    configure_logging(json_mode=json_mode, verbosity=verbose_count)

    # Skip orphan cleanup when running as a subagent (MERIDIAN_SPACE_ID set).
    # Subagents should never clean up their parent space's state — doing so
    # can mark concurrent spawns as failed and close the parent space.
    if not os.environ.get("MERIDIAN_SPACE_ID"):
        try:
            repo_root = resolve_repo_root()
            # Cleanup is best-effort and should never block CLI usage.
            cleanup_orphaned_locks(repo_root)
            spaces_dir = resolve_all_spaces_dir(repo_root)
            if spaces_dir.is_dir():
                for space_dir in sorted(spaces_dir.iterdir()):
                    if not space_dir.is_dir():
                        continue
                    cleanup = cleanup_stale_sessions(space_dir)
                    for harness_id, chat_id in cleanup.materialized_scopes:
                        cleanup_materialized(harness_id, repo_root, chat_id)
        except Exception:
            logger.debug("orphaned lock cleanup failed", exc_info=True)

    args, force_human = _extract_human_flag(args)
    cleaned_args, options = _extract_global_options(args)

    agent_mode = agent_mode_enabled() and not force_human
    if agent_mode and not options.output_explicit:
        options = options.model_copy(update={"output": OutputConfig(format="json")})

    if agent_mode and (not cleaned_args or _is_root_help_request(cleaned_args)):
        _print_agent_root_help()
        return

    _validate_top_level_command(cleaned_args)

    active_sink = create_sink(
        options.output,
        agent_mode=_agent_sink_enabled(output_explicit=options.output_explicit),
    )
    options = options.model_copy(update={"sink": active_sink})
    token = _GLOBAL_OPTIONS.set(options)
    prior_user_config = os.environ.get("MERIDIAN_CONFIG")
    if options.config_file is not None:
        # Set process env so all downstream load_config() calls see --config without plumbing args everywhere.
        os.environ["MERIDIAN_CONFIG"] = options.config_file
    try:
        try:
            app(cleaned_args)
        except TimeoutError as exc:
            _emit_error(_operation_error_message(exc), exit_code=124)
        except (KeyError, ValueError, FileNotFoundError, OSError) as exc:
            _emit_error(_operation_error_message(exc))
    finally:
        flush_sink(active_sink)
        _GLOBAL_OPTIONS.reset(token)
        if options.config_file is not None:
            if prior_user_config is None:
                os.environ.pop("MERIDIAN_CONFIG", None)
            else:
                os.environ["MERIDIAN_CONFIG"] = prior_user_config


_register_group_commands()
