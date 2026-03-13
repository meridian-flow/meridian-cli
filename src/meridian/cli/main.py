"""Cyclopts CLI entry point for meridian."""


import logging
import os
import shlex
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
from meridian.lib.core.sink import OutputSink
from meridian.lib.harness.materialize import cleanup_materialized
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.harness.session_detection import infer_harness_from_untracked_session_ref
from meridian.lib.launch import LaunchRequest, cleanup_orphaned_locks, launch_primary
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.spawn.api import SpawnActionOutput
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.session_store import cleanup_stale_sessions, resolve_session_ref
from meridian.server.main import run_server

logger = logging.getLogger(__name__)

_AGENT_ROOT_HELP = """Usage: meridian COMMAND [ARGS]

Multi-agent orchestration across Claude, Codex, and OpenCode.

Quick start:
  meridian spawn -m MODEL -p "prompt"   Create a subagent run
  meridian spawn wait ID                Wait for results
  meridian models list                  See available models

Run 'meridian spawn -h' for full usage.

Commands:
  spawn   Create and manage subagent runs
  report  Manage spawn reports
  work    Work item dashboard and coordination
  models  Model catalog
  skills  Skills catalog

Output:
  Agent mode defaults to JSON. All commands emit structured JSON.
  Use --format text to force human-readable output.
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


class PrimaryLaunchOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str
    exit_code: int
    command: tuple[str, ...] = ()
    lock_path: str
    continue_ref: str | None = None
    resume_command: str | None = None
    warning: str | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines: list[str] = []
        if self.warning:
            lines.append(f"warning: {self.warning}")
        if self.resume_command:
            lines.append("To continue with meridian:")
            lines.append(self.resume_command)
            return "\n".join(lines)
        if self.command:
            lines.append(self.message)
            lines.append(shlex.join(self.command))
            return "\n".join(lines)
        lines.append(self.message)
        return "\n".join(lines)


class _ResolvedContinueTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    harness_session_id: str | None
    chat_id: str | None = None
    harness: str | None
    tracked: bool = False
    warning: str | None = None


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
        emit_output(payload.to_wire(), sink=sink)
    else:
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

    resolved = normalize_output_format(requested=output_format, json_mode=json_mode)
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
    return int(os.getenv("MERIDIAN_DEPTH", "0")) > 0


def _interactive_terminal_attached() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _agent_sink_enabled(*, output_explicit: bool) -> bool:
    if output_explicit or not agent_mode_enabled() or _interactive_terminal_attached():
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
    """Launch or resume the primary harness."""

    if _GLOBAL_OPTIONS.get() is None:
        resolved = normalize_output_format(requested=output_format, json_mode=json_mode)
        _GLOBAL_OPTIONS.set(
            GlobalOptions(
                output=OutputConfig(format=resolved),
                config_file=config_file,
                yes=yes,
                no_input=no_input,
            )
        )

    _run_primary_launch(
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


spawn_app = App(
    name="spawn",
    help=(
        "Run subagents with a model and prompt. Returns immediately with a spawn_id.\n"
        "Spawns run in background by default."
    ),
    help_epilogue=(
        "Examples:\n\n"
        '  meridian spawn -m gpt-5.3-codex -p "Fix the bug in auth.py"\n\n'
        '  meridian spawn -m claude-sonnet-4-6 -p "Review" -f src/main.py\n\n'
        "  meridian spawn wait SPAWN_ID\n"
    ),
    help_formatter="plain",
)
report_app = App(name="report", help="Report management commands", help_formatter="plain")
work_app = App(name="work", help="Work item coordination and dashboard", help_formatter="plain")
agents_app = App(name="agents", help="Agent profile catalog commands", help_formatter="plain")
skills_app = App(name="skills", help="Skills catalog commands", help_formatter="plain")
models_app = App(name="models", help="Model catalog commands", help_formatter="plain")
config_app = App(name="config", help="Repository config commands", help_formatter="plain")
sync_app = App(
    name="sync",
    help="Sync skills and agents from external sources",
    help_formatter="plain",
)
completion_app = App(name="completion", help="Shell completion helpers", help_formatter="plain")


app.command(spawn_app, name="spawn")
app.command(report_app, name="report")
app.command(work_app, name="work")
app.command(agents_app, name="agents")
app.command(skills_app, name="skills")
app.command(models_app, name="models")
app.command(config_app, name="config")
app.command(sync_app, name="sync")
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


def _run_primary_launch(
    *,
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

    repo_root = Path.cwd().resolve()
    harness_registry = get_default_harness_registry()
    normalized_continue_ref = continue_ref.strip() if continue_ref is not None else ""
    resume_target = normalized_continue_ref if normalized_continue_ref else None
    resolved_permission_tier = permission_tier
    resolved_approval = approval
    if yolo:
        resolved_permission_tier = "full-access"
        resolved_approval = "auto"

    continue_harness_session_id: str | None = None
    continue_chat_id: str | None = None
    continue_harness: str | None = None
    continue_warning: str | None = None
    fresh = True
    explicit_harness = harness.strip() if harness is not None and harness.strip() else None
    if resume_target is not None:
        if model.strip():
            raise ValueError("Cannot combine --continue with --model.")
        if agent is not None and agent.strip():
            raise ValueError("Cannot combine --continue with --agent.")
        resolved_continue = _resolve_continue_target(repo_root=repo_root, continue_ref=resume_target)
        continue_harness_session_id = resolved_continue.harness_session_id
        continue_chat_id = resolved_continue.chat_id
        continue_harness = explicit_harness or resolved_continue.harness
        if continue_harness is None:
            raise ValueError(
                f"Session '{resolved_continue.harness_session_id or resume_target}' "
                "not recognized by any harness. "
                "Use --harness to specify which harness owns this session."
            )
        continue_warning = resolved_continue.warning
        fresh = False

    launch_result = launch_primary(
        repo_root=repo_root,
        request=LaunchRequest(
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
            continue_chat_id=continue_chat_id,
        ),
        harness_registry=harness_registry,
    )

    emit(
        PrimaryLaunchOutput(
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
) -> _ResolvedContinueTarget:
    normalized = continue_ref.strip()
    if not normalized:
        raise ValueError("--continue requires a non-empty session reference.")

    state_root = resolve_state_paths(repo_root).root_dir
    registry = get_default_harness_registry()

    # Look up what our session store says (hint, not authority).
    session = resolve_session_ref(state_root, normalized)
    stored_harness_session_id = (
        session.harness_session_id.strip() or None if session is not None else None
    )
    stored_harness = (
        session.harness.strip() or None if session is not None else None
    )
    # The actual session ID to resume — either what the store recorded or the
    # raw ref the user gave us.
    session_id = stored_harness_session_id or normalized

    # Ask adapters who actually owns this session (ground truth).
    verified_harness = infer_harness_from_untracked_session_ref(
        repo_root,
        session_id,
        registry=registry,
    )

    # Resolution order: adapter verification > stored metadata.
    # If nobody recognizes the session, return harness=None and let
    # the caller decide — it may have an explicit --harness override.
    harness = verified_harness or stored_harness

    warning = None if session is not None else (
        f"Session '{normalized}' is not tracked yet; resuming with the provided harness session id."
    )
    return _ResolvedContinueTarget(
        harness_session_id=session_id,
        chat_id=session.chat_id if session is not None else None,
        harness=harness,
        tracked=session is not None,
        warning=warning,
    )



@app.command(name="init")
def init_alias() -> None:
    """Alias for config init."""

    config_app(["init"])


_REGISTERED_CLI_COMMANDS: set[str] = set()
_REGISTERED_CLI_DESCRIPTIONS: dict[str, str] = {}


def _register_group_commands() -> None:
    from meridian.cli.agents_cmd import register_agents_commands
    from meridian.cli.spawn import register_spawn_commands
    from meridian.cli.sync_cmd import register_sync_commands
    from meridian.cli.work_cmd import register_work_commands

    modules = (
        register_spawn_commands(spawn_app, emit),
        register_report_commands(report_app, emit),
        register_work_commands(work_app, emit),
        register_agents_commands(agents_app, emit),
        register_skills_commands(skills_app, emit),
        register_models_commands(models_app, emit),
        register_config_commands(config_app, emit),
        register_doctor_command(app, emit),
    )
    for commands, descriptions in modules:
        _REGISTERED_CLI_COMMANDS.update(commands)
        _REGISTERED_CLI_DESCRIPTIONS.update(descriptions)

    # Sync is CLI-only (not in ops manifest), registered separately.
    register_sync_commands(sync_app, emit)


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
        if index + 1 < len(argv) and not argv[index + 1].startswith("-"):
            index += 2
            continue
        index += 1
    return None


def _top_level_command_names() -> set[str]:
    return {name for name in _COMMAND_TREE_APP.resolved_commands() if not name.startswith("-")}


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

    if not agent_mode_enabled():
        try:
            repo_root = Path.cwd().resolve()
            cleanup_orphaned_locks(repo_root)
            state_root = resolve_state_paths(repo_root).root_dir
            cleanup = cleanup_stale_sessions(state_root)
            for harness_id in cleanup.materialized_scopes:
                cleanup_materialized(harness_id, repo_root)
        except Exception:
            logger.debug("orphaned lock cleanup failed", exc_info=True)

    args, force_human = _extract_human_flag(args)
    cleaned_args, options = _extract_global_options(args)

    agent_mode = agent_mode_enabled() and not force_human and not _interactive_terminal_attached()
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
        os.environ["MERIDIAN_CONFIG"] = options.config_file
    try:
        try:
            app(cleaned_args)
        except SystemExit:
            raise
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
