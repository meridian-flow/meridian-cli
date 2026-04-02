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
from meridian.cli.models_config_cmd import register_models_config_commands
from meridian.cli.output import (
    OutputConfig,
    create_sink,
    flush_sink,
    normalize_output_format,
)
from meridian.cli.output import emit as emit_output
from meridian.cli.report_cmd import register_report_commands
from meridian.cli.session_cmd import register_session_commands
from meridian.cli.utils import missing_fork_session_error
from meridian.lib.core.sink import OutputSink
from meridian.lib.core.util import FormatContext
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch import LaunchRequest, SessionMode, launch_primary
from meridian.lib.ops.reference import resolve_session_reference
from meridian.lib.ops.spawn.api import SpawnActionOutput
from meridian.lib.ops.spawn.plan import SessionContinuation
from meridian.lib.state.paths import resolve_state_paths
from meridian.lib.state.session_store import cleanup_stale_sessions
from meridian.server.main import run_server

logger = logging.getLogger(__name__)

# Curated help for agent mode: only commands useful for subagent callers.
# Not auto-generated — update when adding agent-facing commands.
_AGENT_ROOT_HELP = """Usage: meridian COMMAND [ARGS]

Multi-agent orchestration across Claude, Codex, and OpenCode.

Quick start:
  meridian spawn -m MODEL -p "prompt"   Create a subagent run
  meridian spawn wait ID                Wait for results
  meridian models list                  See available models

Run 'meridian spawn -h' for full usage.

Commands:
  spawn    Create and manage subagent runs (includes report subgroup)
  work     Work item dashboard and coordination
  models   Model catalog

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
    force_human: bool = False
    sink: OutputSink | None = None


_GLOBAL_OPTIONS: ContextVar[GlobalOptions | None] = ContextVar("_GLOBAL_OPTIONS", default=None)


class PrimaryLaunchOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str
    exit_code: int
    command: tuple[str, ...] = ()
    continue_ref: str | None = None
    forked_from: str | None = None
    resume_command: str | None = None
    warning: str | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines: list[str] = []
        if self.warning:
            lines.append(f"warning: {self.warning}")
        if self.command:
            if self.forked_from:
                lines.append(f"{self.message} (from {self.forked_from})")
            else:
                lines.append(self.message)
            lines.append(shlex.join(self.command))
            return "\n".join(lines)
        if self.resume_command:
            if self.forked_from:
                lines.append(f"Session forked from {self.forked_from}.")
            else:
                lines.append(self.message)
            lines.append("To continue with meridian:")
            lines.append(self.resume_command)
            return "\n".join(lines)
        if self.forked_from:
            lines.append(f"{self.message} (from {self.forked_from})")
        else:
            lines.append(self.message)
        return "\n".join(lines)


class _ResolvedSessionTarget(BaseModel):
    model_config = ConfigDict(frozen=True)

    harness_session_id: str | None
    chat_id: str | None = None
    harness: str | None
    source_model: str | None = None
    source_agent: str | None = None
    source_work_id: str | None = None
    source_execution_cwd: str | None = None
    tracked: bool = False
    warning: str | None = None

    @property
    def missing_harness_session_id(self) -> bool:
        return self.tracked and self.harness_session_id is None


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
        if options.output.format == "json" or _agent_sink_enabled(
            output_explicit=options.output_explicit
        ):
            emit_output(payload.to_wire(), sink=sink)
        else:
            emit_output(payload, sink=sink)
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
    force_human = False
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
        if arg == "--human":
            force_human = True
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
        force_human=force_human,
    )


def agent_mode_enabled() -> bool:
    return int(os.getenv("MERIDIAN_DEPTH", "0")) > 0


def _interactive_terminal_attached() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _agent_sink_enabled(*, output_explicit: bool) -> bool:
    return not (output_explicit or not agent_mode_enabled() or _interactive_terminal_attached())


app = App(
    name="meridian",
    help=(
        "Multi-agent orchestration across Claude, Codex, and OpenCode.\n\n"
        "Harness shortcuts: meridian claude, meridian codex, meridian opencode\n\n"
        'Run "meridian spawn -h" for subagent usage.'
    ),
    version=__version__,
    help_formatter="plain",
)


@app.default
def root(
    *passthrough: Annotated[
        str,
        Parameter(
            help="Harness passthrough arguments (after --).",
            show=False,
        ),
    ],
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
    fork_ref: Annotated[
        str | None,
        Parameter(name="--fork", help="Fork from a session or spawn reference."),
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
    work: Annotated[
        str,
        Parameter(name="--work", help="Attach the primary session to a work item id."),
    ] = "",
    yolo: Annotated[
        bool,
        Parameter(
            name="--yolo",
            help="Skip all harness safety prompts and sandboxing.",
        ),
    ] = False,
    autocompact: Annotated[
        int | None,
        Parameter(name="--autocompact", help="Auto-compact threshold in messages."),
    ] = None,
    effort: Annotated[
        str | None,
        Parameter(name="--effort", help="Effort level: low, medium, high, xhigh."),
    ] = None,
    sandbox: Annotated[
        str | None,
        Parameter(
            name="--sandbox",
            help=(
                "Sandbox mode: read-only, workspace-write, full-access,"
                " danger-full-access, unrestricted."
            ),
        ),
    ] = None,
    approval: Annotated[
        str | None,
        Parameter(
            name="--approval",
            help="Approval mode: default, confirm, auto, yolo. Overrides agent profile.",
        ),
    ] = None,
    timeout: Annotated[
        float | None,
        Parameter(name="--timeout", help="Maximum runtime in minutes."),
    ] = None,
    dry_run: Annotated[
        bool,
        Parameter(name="--dry-run", help="Preview launch command without starting harness."),
    ] = False,
) -> None:
    """Launch or resume the primary harness."""

    if yolo and approval is not None:
        raise ValueError("Cannot combine --yolo with --approval.")

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
        fork_ref=fork_ref,
        model=model,
        harness=harness,
        agent=agent,
        work=work,
        yolo=yolo,
        approval=approval,
        autocompact=autocompact,
        effort=effort,
        sandbox=sandbox,
        timeout=timeout,
        dry_run=dry_run,
        passthrough=passthrough,
    )


@app.command(name="serve")
def serve() -> None:
    """Start FastMCP server on stdio."""

    run_server()


spawn_app = App(
    name="spawn",
    help=(
        "Run subagents with a model and prompt.\n"
        "Runs in background by default. Use --foreground to block."
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
session_app = App(name="session", help="Session inspection commands", help_formatter="plain")
work_app = App(
    name="work",
    help=(
        "Active activity grouped by work, plus work item coordination commands. "
        "Unassigned spawns appear under '(no work)'."
    ),
    help_formatter="plain",
)
models_app = App(name="models", help="Model catalog commands", help_formatter="plain")
models_config_app = App(
    name="config",
    help="Model catalog config commands",
    help_formatter="plain",
)
config_app = App(name="config", help="Repository config commands", help_formatter="plain")
completion_app = App(name="completion", help="Shell completion helpers", help_formatter="plain")


app.command(spawn_app, name="spawn")
spawn_app.command(report_app, name="report")
app.command(session_app, name="session")
app.command(work_app, name="work")
app.command(models_app, name="models")
models_app.command(models_config_app, name="config")
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


def _run_primary_launch(
    *,
    continue_ref: str | None,
    fork_ref: str | None,
    model: str,
    harness: str | None,
    agent: str | None,
    work: str,
    yolo: bool,
    approval: str | None,
    autocompact: int | None,
    effort: str | None,
    sandbox: str | None,
    timeout: float | None,
    dry_run: bool,
    passthrough: tuple[str, ...],
) -> None:
    """Shared primary launch flow for root command entry."""

    def _merge_warnings(*warnings: str | None) -> str | None:
        parts = [item.strip() for item in warnings if item and item.strip()]
        if not parts:
            return None
        return "; ".join(parts)

    repo_root = Path.cwd().resolve()
    harness_registry = get_default_harness_registry()
    normalized_continue_ref = continue_ref.strip() if continue_ref is not None else ""
    normalized_fork_ref = fork_ref.strip() if fork_ref is not None else ""
    resume_target = normalized_continue_ref if normalized_continue_ref else None
    fork_target = normalized_fork_ref if normalized_fork_ref else None
    resolved_approval = approval if approval is not None else ("yolo" if yolo else "default")

    if resume_target is not None and fork_target is not None:
        raise ValueError("Cannot combine --fork with --continue.")

    continue_harness_session_id: str | None = None
    continue_chat_id: str | None = None
    continue_harness: str | None = None
    continue_fork = False
    continue_warning: str | None = None
    forked_from_chat_id: str | None = None
    source_execution_cwd: str | None = None
    output_forked_from: str | None = None
    session_mode = SessionMode.FRESH
    explicit_harness = harness.strip() if harness is not None and harness.strip() else None
    requested_model = model
    requested_agent = agent
    requested_work_id = work.strip() or None
    if resume_target is not None:
        if model.strip():
            raise ValueError("Cannot combine --continue with --model.")
        if agent is not None and agent.strip():
            raise ValueError("Cannot combine --continue with --agent.")
        resolved_continue = _resolve_session_target(
            repo_root=repo_root, continue_ref=resume_target
        )
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
        session_mode = SessionMode.RESUME
    elif fork_target is not None:
        resolved_fork = _resolve_session_target(repo_root=repo_root, continue_ref=fork_target)
        if resolved_fork.missing_harness_session_id:
            raise ValueError(missing_fork_session_error(fork_target))

        source_harness = (
            resolved_fork.harness.strip()
            if resolved_fork.harness is not None and resolved_fork.harness.strip()
            else None
        )
        if (
            explicit_harness is not None
            and source_harness is not None
            and explicit_harness != source_harness
        ):
            raise ValueError(
                "Cannot fork across harnesses: "
                f"source is '{source_harness}', target is '{explicit_harness}'."
            )

        continue_harness_session_id = resolved_fork.harness_session_id
        continue_harness = explicit_harness or source_harness
        if continue_harness is None:
            raise ValueError(
                f"Session '{resolved_fork.harness_session_id or fork_target}' "
                "not recognized by any harness. "
                "Use --harness to specify which harness owns this session."
            )
        continue_warning = resolved_fork.warning
        continue_fork = True
        forked_from_chat_id = resolved_fork.chat_id
        source_execution_cwd = resolved_fork.source_execution_cwd
        output_forked_from = resolved_fork.chat_id or fork_target
        session_mode = SessionMode.FORK

        if not model.strip() and resolved_fork.source_model is not None:
            requested_model = resolved_fork.source_model
        if (agent is None or not agent.strip()) and resolved_fork.source_agent is not None:
            requested_agent = resolved_fork.source_agent
        if requested_work_id is None and resolved_fork.source_work_id is not None:
            requested_work_id = resolved_fork.source_work_id

    launch_result = launch_primary(
        repo_root=repo_root,
        request=LaunchRequest(
            model=requested_model,
            harness=(
                continue_harness
                if (resume_target is not None or fork_target is not None)
                else harness
            ),
            agent=requested_agent,
            work_id=requested_work_id,
            autocompact=autocompact,
            passthrough_args=passthrough,
            session_mode=session_mode,
            pinned_context="",
            dry_run=dry_run,
            approval=resolved_approval,
            effort=effort,
            sandbox=sandbox,
            timeout=timeout,
            session=SessionContinuation(
                harness_session_id=continue_harness_session_id,
                continue_harness=continue_harness,
                continue_chat_id=continue_chat_id,
                continue_fork=continue_fork,
                forked_from_chat_id=forked_from_chat_id,
                source_execution_cwd=source_execution_cwd,
            ),
        ),
        harness_registry=harness_registry,
    )

    emit(
        PrimaryLaunchOutput(
            message=(
                "Resume dry-run."
                if dry_run and resume_target is not None
                else (
                    "Fork dry-run."
                    if dry_run and fork_target is not None
                    else (
                        "Launch dry-run."
                        if dry_run
                        else (
                            "Session resumed."
                            if resume_target is not None
                            else (
                                "Session forked."
                                if fork_target is not None
                                else "Session finished."
                            )
                        )
                    )
                )
            ),
            exit_code=launch_result.exit_code,
            command=launch_result.command if dry_run else (),
            continue_ref=launch_result.continue_ref,
            forked_from=output_forked_from,
            resume_command=(
                f"meridian --continue {launch_result.continue_ref}"
                if launch_result.continue_ref is not None
                else None
            ),
            warning=_merge_warnings(continue_warning, launch_result.warning),
        )
    )


def _register_harness_shortcut_command(harness_name: str) -> None:
    """Register a harness shortcut command on the main app."""

    @app.command(name=harness_name)
    def shortcut(
        *passthrough: Annotated[
            str,
            Parameter(
                help="Harness passthrough arguments (after --).",
                show=False,
            ),
        ],
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
        fork_ref: Annotated[
            str | None,
            Parameter(name="--fork", help="Fork from a session or spawn reference."),
        ] = None,
        model: Annotated[
            str,
            Parameter(name="--model", help="Model id or alias for primary harness."),
        ] = "",
        agent: Annotated[
            str | None,
            Parameter(name=["--agent", "-a"], help="Agent profile name for the primary agent."),
        ] = None,
        work: Annotated[
            str,
            Parameter(name="--work", help="Attach the primary session to a work item id."),
        ] = "",
        yolo: Annotated[
            bool,
            Parameter(
                name="--yolo",
                help="Skip all harness safety prompts and sandboxing.",
            ),
        ] = False,
        autocompact: Annotated[
            int | None,
            Parameter(name="--autocompact", help="Auto-compact threshold in messages."),
        ] = None,
        effort: Annotated[
            str | None,
            Parameter(name="--effort", help="Effort level: low, medium, high, xhigh."),
        ] = None,
        sandbox: Annotated[
            str | None,
            Parameter(
                name="--sandbox",
                help=(
                    "Sandbox mode: read-only, workspace-write, full-access,"
                    " danger-full-access, unrestricted."
                ),
            ),
        ] = None,
        approval: Annotated[
            str | None,
            Parameter(
                name="--approval",
                help="Approval mode: default, confirm, auto, yolo. Overrides agent profile.",
            ),
        ] = None,
        timeout: Annotated[
            float | None,
            Parameter(name="--timeout", help="Maximum runtime in minutes."),
        ] = None,
        dry_run: Annotated[
            bool,
            Parameter(name="--dry-run", help="Preview launch command without starting harness."),
        ] = False,
    ) -> None:
        """Launch or resume the primary harness."""

        if yolo and approval is not None:
            raise ValueError("Cannot combine --yolo with --approval.")

        if _GLOBAL_OPTIONS.get() is None:
            _GLOBAL_OPTIONS.set(
                GlobalOptions(
                    output=OutputConfig(format="text"),
                    config_file=None,
                    yes=yes,
                    no_input=no_input,
                )
            )

        _run_primary_launch(
            continue_ref=continue_ref,
            fork_ref=fork_ref,
            model=model,
            harness=harness_name,
            agent=agent,
            work=work,
            yolo=yolo,
            approval=approval,
            autocompact=autocompact,
            effort=effort,
            sandbox=sandbox,
            timeout=timeout,
            dry_run=dry_run,
            passthrough=passthrough,
        )

    shortcut.__doc__ = f"Launch the {harness_name} harness directly."


for _harness_name in ("claude", "codex", "opencode"):
    _register_harness_shortcut_command(_harness_name)

def _resolve_session_target(
    *,
    repo_root: Path,
    continue_ref: str,
) -> _ResolvedSessionTarget:
    normalized = continue_ref.strip()
    if not normalized:
        raise ValueError("--continue requires a non-empty session reference.")

    resolved = resolve_session_reference(repo_root, normalized)
    return _ResolvedSessionTarget(
        harness_session_id=resolved.harness_session_id,
        chat_id=resolved.source_chat_id,
        harness=resolved.harness,
        source_model=resolved.source_model,
        source_agent=resolved.source_agent,
        source_work_id=resolved.source_work_id,
        source_execution_cwd=resolved.source_execution_cwd,
        tracked=resolved.tracked,
        warning=resolved.warning,
    )


@app.command(name="init")
def init_alias() -> None:
    """Alias for config init."""

    config_app(["init"])


def _register_group_commands() -> None:
    from meridian.cli.spawn import register_spawn_commands
    from meridian.cli.work_cmd import register_work_commands

    register_spawn_commands(spawn_app, emit)
    register_report_commands(report_app, emit)
    register_session_commands(session_app, emit)
    register_work_commands(work_app, emit)
    register_models_commands(models_app, emit)
    register_models_config_commands(models_config_app, emit)
    register_config_commands(config_app, emit)
    register_doctor_command(app, emit)


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
        "--fork",
        "--model",
        "--harness",
        "--agent",
        "-a",
        "--work",
        "--autocompact",
        "--effort",
        "--sandbox",
        "--approval",
        "--timeout",
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
    return {name for name in app.resolved_commands() if not name.startswith("-")}


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

    cleaned_args, options = _extract_global_options(args)

    agent_mode = (
        agent_mode_enabled() and not options.force_human and not _interactive_terminal_attached()
    )
    if agent_mode and not options.output_explicit:
        options = options.model_copy(update={"output": OutputConfig(format="json")})

    if agent_mode and (not cleaned_args or _is_root_help_request(cleaned_args)):
        _print_agent_root_help()
        return

    _validate_top_level_command(cleaned_args)

    if not agent_mode_enabled():
        try:
            from meridian.lib.config.settings import resolve_repo_root
            from meridian.lib.ops.config import ensure_state_bootstrap_sync

            repo_root = resolve_repo_root()
            ensure_state_bootstrap_sync(repo_root)
            cleanup_stale_sessions(resolve_state_paths(repo_root).root_dir)
        except Exception:
            logger.debug("startup bootstrap failed", exc_info=True)

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
