"""Cyclopts CLI entry point for meridian."""

import asyncio
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass
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
from meridian.cli.session_cmd import register_session_commands
from meridian.cli.streaming_serve import streaming_serve
from meridian.cli.utils import missing_fork_session_error
from meridian.cli.workspace_cmd import register_workspace_commands
from meridian.lib.core.sink import OutputSink
from meridian.lib.core.util import FormatContext
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.launch import LaunchRequest, SessionMode, launch_primary
from meridian.lib.launch.request import SessionRequest
from meridian.lib.ops.mars import (
    UpgradeAvailability,
    check_upgrade_availability,
    format_upgrade_availability,
    resolve_mars_executable,
)
from meridian.lib.ops.reference import resolve_session_reference
from meridian.lib.ops.spawn.api import SpawnActionOutput
from meridian.server.main import run_server

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
  init     Initialize repo config; optional --link wiring for tool directories
  mars     Forward arguments to bundled mars CLI
  spawn    Create and manage subagent runs (includes report subgroup)
  session  Read and search harness session transcripts
  work     Work item dashboard and coordination
  models   Model catalog
  config   Repository config inspection and overrides
  workspace  Local workspace topology setup
  doctor   Health check and orphan reconciliation

Output:
  Agent mode defaults to JSON. All commands emit structured JSON.
  Use --format text to force human-readable output.
"""


class GlobalOptions(BaseModel):
    """Top-level options that apply to all commands."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    output: OutputConfig
    config_file: str | None = None
    harness: str | None = None
    yes: bool = False
    no_input: bool = False
    output_explicit: bool = False
    force_human: bool = False
    passthrough_args: tuple[str, ...] = ()
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
    harness: str | None = None
    yes = False
    no_input = False
    output_explicit = False
    force_human = False
    cleaned: list[str] = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--":
            cleaned.extend(argv[i:])
            break
        if arg == "mars":
            cleaned.extend(argv[i:])
            break
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
        if arg == "--harness":
            if i + 1 >= len(argv):
                raise SystemExit("--harness requires a value")
            requested_harness = argv[i + 1].strip()
            if not requested_harness:
                raise SystemExit("--harness requires a non-empty value")
            if harness is not None and harness != requested_harness:
                raise SystemExit(
                    f"Conflicting harness selections: '{harness}' and '{requested_harness}'."
                )
            harness = requested_harness
            i += 2
            continue
        if arg.startswith("--harness="):
            requested_harness = arg.partition("=")[2].strip()
            if not requested_harness:
                raise SystemExit("--harness requires a non-empty value")
            if harness is not None and harness != requested_harness:
                raise SystemExit(
                    f"Conflicting harness selections: '{harness}' and '{requested_harness}'."
                )
            harness = requested_harness
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

    shortcut = _first_positional_token_with_index(cleaned)
    if shortcut is not None:
        shortcut_index, shortcut_value = shortcut
        if shortcut_value in _HARNESS_SHORTCUT_NAMES:
            if harness is not None and harness != shortcut_value:
                raise SystemExit(
                    "Conflicting harness selections: "
                    f"'{harness}' and '{shortcut_value}'."
                )
            harness = shortcut_value
            del cleaned[shortcut_index]

    resolved = normalize_output_format(requested=output_format, json_mode=json_mode)
    return cleaned, GlobalOptions(
        output=OutputConfig(format=resolved),
        config_file=config_file,
        harness=harness,
        yes=yes,
        no_input=no_input,
        output_explicit=output_explicit,
        force_human=force_human,
    )


def _split_passthrough_args(argv: Sequence[str]) -> tuple[list[str], tuple[str, ...]]:
    """Split args at ``--`` so cyclopts never sees passthrough tokens.

    Workaround for a cyclopts bug: tokens after ``--`` are supposed to be
    positional-only, but cyclopts still assigns them to unfilled named
    parameters (e.g. ``--prompt`` absorbs ``--add-dir``).  We strip ``--``
    and everything after it before cyclopts parses, stash the passthrough
    tokens on ``GlobalOptions.passthrough_args``, and have handlers read
    them from there instead of from a ``*passthrough`` function parameter.
    """

    if "--" not in argv:
        return list(argv), ()
    sep_idx = list(argv).index("--")
    return list(argv[:sep_idx]), tuple(argv[sep_idx + 1 :])


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
        "Global harness selection: --harness (or prefix with claude/codex/opencode)\n"
        "Bundled package manager: meridian mars <args>\n\n"
        'Run "meridian spawn -h" for subagent usage.'
    ),
    version=__version__,
    help_formatter="plain",
)


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
    fork_ref: Annotated[
        str | None,
        Parameter(name="--fork", help="Fork from a session or spawn reference."),
    ] = None,
    model: Annotated[
        str,
        Parameter(name=["--model", "-m"], help="Model id or alias for primary harness."),
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
                "Sandbox mode: default, read-only, workspace-write, "
                "danger-full-access."
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
                harness=harness,
                yes=yes,
                no_input=no_input,
            )
        )

    global_harness = get_global_options().harness
    explicit_harness = harness.strip() if harness is not None and harness.strip() else None
    if global_harness and explicit_harness and global_harness != explicit_harness:
        raise ValueError(
            f"Conflicting harness selections: '{global_harness}' and '{explicit_harness}'."
        )

    _run_primary_launch(
        continue_ref=continue_ref,
        fork_ref=fork_ref,
        model=model,
        harness=global_harness or explicit_harness,
        agent=agent,
        work=work,
        yolo=yolo,
        approval=approval,
        autocompact=autocompact,
        effort=effort,
        sandbox=sandbox,
        timeout=timeout,
        dry_run=dry_run,
        # See _split_passthrough_args() for why this reads from GlobalOptions.
        passthrough=get_global_options().passthrough_args,
    )


@app.command(name="serve")
def serve() -> None:
    """Start FastMCP server on stdio."""

    run_server()


@app.command(name="app")
def app_command(
    uds: Annotated[
        str | None,
        Parameter(
            name="--uds",
            help="Unix domain socket path for the app server (default: .meridian/app.sock).",
        ),
    ] = None,
    proxy: Annotated[
        str | None,
        Parameter(
            name="--proxy",
            help="Optional browser-facing proxy URL that forwards HTTP traffic to --uds.",
        ),
    ] = None,
    debug: Annotated[
        bool,
        Parameter(name="--debug", help="Enable wire-level debug tracing."),
    ] = False,
    allow_unsafe_no_permissions: Annotated[
        bool,
        Parameter(
            name="--allow-unsafe-no-permissions",
            help=(
                "Allow /api/spawns requests with missing permissions metadata by "
                "using UnsafeNoOpPermissionResolver."
            ),
        ),
    ] = False,
) -> None:
    """Start the Meridian app web UI server."""

    from meridian.cli.app_cmd import run_app

    run_app(
        uds=uds,
        proxy=proxy,
        debug=debug,
        allow_unsafe_no_permissions=allow_unsafe_no_permissions,
    )


def _resolve_mars_executable() -> str | None:
    """Prefer the mars binary from the current install environment over PATH."""

    return resolve_mars_executable()


def _mars_requested_json(args: Sequence[str]) -> bool:
    return any(token == "--json" for token in args)


def _mars_requested_root(args: Sequence[str]) -> Path | None:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--root":
            next_value = args[index + 1].strip() if index + 1 < len(args) else ""
            if next_value:
                return Path(next_value)
            index += 2
            continue
        if token.startswith("--root="):
            candidate = token.partition("=")[2].strip()
            if candidate:
                return Path(candidate)
        index += 1
    return None


def _mars_subcommand(args: Sequence[str]) -> str | None:
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            return None
        if token == "--root":
            index += 2
            continue
        if token.startswith("--root="):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return None


def _inject_upgrade_hint_into_sync_json(
    raw_stdout: str,
    *,
    within_constraint: tuple[str, ...],
    beyond_constraint: tuple[str, ...],
) -> str:
    stripped = raw_stdout.strip()
    if not stripped:
        return raw_stdout
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return raw_stdout
    if not isinstance(parsed, dict):
        return raw_stdout
    parsed["upgrade_hint"] = {
        "within_constraint": list(within_constraint),
        "beyond_constraint": list(beyond_constraint),
    }
    rendered = json.dumps(parsed)
    if raw_stdout.endswith("\n"):
        rendered += "\n"
    return rendered


def _decode_json_values(raw_stdout: str) -> list[object] | None:
    decoder = json.JSONDecoder()
    parsed_values: list[object] = []
    index = 0
    while index < len(raw_stdout):
        while index < len(raw_stdout) and raw_stdout[index].isspace():
            index += 1
        if index >= len(raw_stdout):
            return parsed_values
        try:
            parsed, index = decoder.raw_decode(raw_stdout, index)
        except json.JSONDecodeError:
            return None
        parsed_values.append(parsed)
    return parsed_values


@dataclass(frozen=True)
class _MarsPassthroughRequest:
    command: tuple[str, ...]
    mars_args: tuple[str, ...]
    is_sync: bool
    wants_json: bool
    root_override: Path | None


@dataclass(frozen=True)
class _MarsPassthroughResult:
    request: _MarsPassthroughRequest
    returncode: int
    stdout_text: str = ""
    stderr_text: str = ""


def _parse_mars_passthrough(
    args: Sequence[str],
    *,
    output_format: str | None = None,
    executable: str,
) -> _MarsPassthroughRequest:
    """Build an executable Mars passthrough request without side effects."""

    mars_args = list(args)
    is_sync = _mars_subcommand(mars_args) == "sync"
    wants_json = _mars_requested_json(mars_args) or output_format == "json"
    if wants_json and not _mars_requested_json(mars_args):
        mars_args = ["--json", *mars_args]
    return _MarsPassthroughRequest(
        command=(executable, *mars_args),
        mars_args=tuple(mars_args),
        is_sync=is_sync,
        wants_json=wants_json,
        root_override=_mars_requested_root(mars_args),
    )


def _execute_mars_passthrough(request: _MarsPassthroughRequest) -> _MarsPassthroughResult:
    """Execute a prepared Mars passthrough request."""

    try:
        if request.wants_json:
            result = subprocess.run(
                list(request.command),
                check=False,
                capture_output=True,
                text=True,
            )
            return _MarsPassthroughResult(
                request=request,
                returncode=result.returncode,
                stdout_text=result.stdout or "",
                stderr_text=result.stderr or "",
            )

        result = subprocess.run(list(request.command), check=False)
        return _MarsPassthroughResult(request=request, returncode=result.returncode)
    except FileNotFoundError:
        print(
            "error: Failed to execute 'mars'. Install meridian with dependencies and retry.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None


def _augment_sync_result(
    result: _MarsPassthroughResult,
    *,
    output_format: str | None = None,
) -> None:
    """Add sync-specific upgrade availability output to passthrough results."""

    _ = output_format
    if not result.request.is_sync:
        return

    upgrades: UpgradeAvailability | None = None
    if result.returncode in {0, 1}:
        upgrades = check_upgrade_availability(result.request.root_override)

    if result.request.wants_json:
        stdout_text = result.stdout_text
        if upgrades is not None and upgrades.count > 0 and stdout_text.strip():
            stdout_text = _inject_upgrade_hint_into_sync_json(
                stdout_text,
                within_constraint=upgrades.within_constraint,
                beyond_constraint=upgrades.beyond_constraint,
            )
        if stdout_text:
            sys.stdout.write(stdout_text)
        if result.stderr_text:
            sys.stderr.write(result.stderr_text)
        return

    if upgrades is not None and upgrades.count > 0:
        for line in format_upgrade_availability(upgrades, style="hint"):
            print(line)


def _run_mars_passthrough(
    args: Sequence[str],
    *,
    output_format: str | None = None,
) -> None:
    executable = _resolve_mars_executable()
    if executable is None:
        print(
            "error: Failed to execute 'mars'. Install meridian with dependencies and retry.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    request = _parse_mars_passthrough(
        args,
        output_format=output_format,
        executable=executable,
    )
    result = _execute_mars_passthrough(request)
    if not request.is_sync:
        if request.wants_json:
            if result.stdout_text:
                sys.stdout.write(result.stdout_text)
            if result.stderr_text:
                sys.stderr.write(result.stderr_text)
        raise SystemExit(result.returncode)

    _augment_sync_result(result, output_format=output_format)
    raise SystemExit(result.returncode)


@app.command(name="mars")
def mars(
    *args: Annotated[
        str,
        Parameter(
            help="Arguments forwarded to mars.",
            show=False,
        ),
    ],
) -> None:
    """Forward all arguments to the bundled mars CLI."""

    _run_mars_passthrough(args, output_format=get_global_options().output.format)


spawn_app = App(
    name="spawn",
    help=(
        "Run subagents with a model and prompt.\n"
        "Runs in foreground by default; returns when the spawn reaches a terminal state. "
        "Use --background to return immediately with the spawn ID."
    ),
    help_epilogue=(
        "Examples:\n\n"
        '  meridian spawn -m gpt-5.3-codex -p "Fix the bug in auth.py"\n\n'
        '  meridian spawn -m claude-sonnet-4-6 -p "Review" -f src/main.py\n\n'
        "  meridian spawn wait SPAWN_ID\n"
    ),
    help_formatter="plain",
)
report_app = App(
    name="report",
    help="Report management commands.",
    help_epilogue=(
        "Examples:\n\n"
        "  meridian spawn report show p107\n\n"
        '  meridian spawn report search "auth bug"\n'
    ),
    help_formatter="plain",
)
session_app = App(
    name="session",
    help=(
        "Inspect harness session transcripts.\n\n"
        "Session refs accept three forms: chat ids (c123), spawn ids (p123),\n"
        "or raw harness session ids. By default, commands operate on\n"
        "$MERIDIAN_CHAT_ID -- inherited from the spawning session -- so a\n"
        "subagent reads its parent's transcript, not its own."
    ),
    help_formatter="plain",
)
work_app = App(
    name="work",
    help=(
        "Active activity grouped by work, plus work item coordination commands. "
        "Unassigned spawns appear under '(no work)'."
    ),
    help_formatter="plain",
)
models_app = App(name="models", help="Model catalog commands", help_formatter="plain")
streaming_app = App(name="streaming", help="Streaming layer commands", help_formatter="plain")
config_app = App(
    name="config",
    help=(
        "Repository-level config (meridian.toml) for default\n"
        "agent, model, harness, timeouts, and output verbosity.\n\n"
        "Resolved values are evaluated independently per field -- a CLI\n"
        "override on one field does not pull other fields from the same\n"
        "source. Use `meridian config show` to see each value with its\n"
        "source annotation."
    ),
    help_formatter="plain",
)
workspace_app = App(
    name="workspace",
    help=(
        "Local workspace topology commands.\n\n"
        "Workspace topology is stored in workspace.local.toml next to the active .meridian/ "
        "directory and is intentionally local-only."
    ),
    help_formatter="plain",
)
completion_app = App(name="completion", help="Shell completion helpers", help_formatter="plain")


app.command(spawn_app, name="spawn")
spawn_app.command(report_app, name="report")
app.command(session_app, name="session")
app.command(work_app, name="work")
app.command(models_app, name="models")
app.command(streaming_app, name="streaming")
app.command(config_app, name="config")
app.command(workspace_app, name="workspace")
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


@streaming_app.command(name="serve")
def streaming_serve_cmd(
    prompt: Annotated[
        str,
        Parameter(name=["--prompt", "-p"], help="Initial prompt for the streaming run."),
    ] = "",
    harness: Annotated[
        str | None,
        Parameter(name="--harness", help="Harness id: claude, codex, or opencode."),
    ] = None,
    model: Annotated[
        str | None,
        Parameter(name=["--model", "-m"], help="Optional model override."),
    ] = None,
    agent: Annotated[
        str | None,
        Parameter(name=["--agent", "-a"], help="Optional agent profile."),
    ] = None,
    debug: Annotated[
        bool,
        Parameter(name="--debug", help="Enable wire-level debug tracing."),
    ] = False,
) -> None:
    resolved_harness = (harness or get_global_options().harness or "").strip()
    if not resolved_harness:
        raise ValueError("harness required: pass --harness")
    if not prompt.strip():
        raise ValueError("prompt required: pass --prompt")
    asyncio.run(
        streaming_serve(
            harness=resolved_harness,
            prompt=prompt,
            model=model,
            agent=agent,
            debug=debug,
        )
    )


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
            session=SessionRequest(
                requested_harness_session_id=continue_harness_session_id,
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


def _resolve_init_repo_root(path: str | None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    env_root = os.getenv("MERIDIAN_REPO_ROOT", "").strip()
    return Path(env_root).expanduser().resolve() if env_root else Path.cwd().resolve()


def _resolve_init_link_mars_command(
    repo_root: Path, link: str
) -> tuple[str, list[str]]:
    root_arg = repo_root.as_posix()
    if (repo_root / "mars.toml").is_file():
        return "link", ["--root", root_arg, "link", link]
    return "init", ["--root", root_arg, "init", "--link", link]


def _run_init_link_flow_json(
    *,
    executable: str,
    mars_mode: str,
    mars_args: Sequence[str],
    link: str,
    config_result: BaseModel,
) -> None:
    request = _parse_mars_passthrough(mars_args, output_format="json", executable=executable)
    result = _execute_mars_passthrough(request)
    parsed_events = _decode_json_values(result.stdout_text)
    if parsed_events is None:
        mars_output: object = result.stdout_text
    elif len(parsed_events) == 1:
        mars_output = parsed_events[0]
    else:
        mars_output = parsed_events

    mars_payload: dict[str, object] = {
        "mode": mars_mode,
        "target": link,
        "exit_code": result.returncode,
        "output": mars_output,
    }
    if result.stderr_text:
        mars_payload["stderr"] = result.stderr_text
    emit(
        {
            "ok": result.returncode == 0,
            "config": config_result.model_dump(),
            "mars": mars_payload,
        }
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)


@app.command(name="init")
def init_alias(
    path: Annotated[
        str | None,
        Parameter(name="path", help="Optional project path to initialize."),
    ] = None,
    link: Annotated[
        str | None,
        Parameter(
            name="--link",
            help="Link .agents/ into tool directory after config bootstrap (for example .claude).",
        ),
    ] = None,
) -> None:
    """Initialize meridian in the current project or provided path."""

    from meridian.lib.ops.config import ConfigInitInput, config_init_sync

    repo_root = _resolve_init_repo_root(path)
    result = config_init_sync(ConfigInitInput(repo_root=repo_root.as_posix()))
    if link is None:
        emit(result)
        return

    mars_mode, mars_args = _resolve_init_link_mars_command(repo_root, link)
    output_format = get_global_options().output.format
    if output_format == "json":
        executable = _resolve_mars_executable()
        if executable is None:
            print(
                "error: Failed to execute 'mars'. Install meridian with dependencies and retry.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        _run_init_link_flow_json(
            executable=executable,
            mars_mode=mars_mode,
            mars_args=mars_args,
            link=link,
            config_result=result,
        )
        return
    _run_mars_passthrough(mars_args, output_format=output_format)




@app.command(name="context")
def context_cmd() -> None:
    """Query runtime context: work_dir, fs_dir, repo_root, state_root, depth, context_roots."""

    from meridian.lib.ops.context import ContextInput, context_sync

    emit(context_sync(ContextInput()))


def _register_group_commands() -> None:
    from meridian.cli.spawn import register_spawn_commands
    from meridian.cli.work_cmd import register_work_commands

    register_spawn_commands(spawn_app, emit)
    register_report_commands(report_app, emit)
    register_session_commands(session_app, emit)
    register_work_commands(work_app, emit)
    register_models_commands(models_app, emit)
    register_config_commands(config_app, emit)
    register_workspace_commands(workspace_app, emit)
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
        "-m",
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
_HARNESS_SHORTCUT_NAMES = frozenset({"claude", "codex", "opencode"})


def _first_positional_token_with_index(argv: Sequence[str]) -> tuple[int, str] | None:
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            return None
        if not token.startswith("-"):
            return index, token
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


def _first_positional_token(argv: Sequence[str]) -> str | None:
    resolved = _first_positional_token_with_index(argv)
    if resolved is None:
        return None
    _, token = resolved
    return token


def _top_level_command_names() -> set[str]:
    return {name for name in app.resolved_commands() if not name.startswith("-")}


def _validate_top_level_command(argv: Sequence[str], *, global_harness: str | None = None) -> None:
    candidate = _first_positional_token(argv)
    if candidate is None:
        return
    if candidate in _top_level_command_names():
        return
    if global_harness is not None:
        return
    print(f"error: Unknown command: {candidate}", file=sys.stderr)
    raise SystemExit(1)


def _is_root_help_request(argv: Sequence[str]) -> bool:
    if not any(token in {"--help", "-h"} for token in argv):
        return False
    return _first_positional_token(argv) is None


def _first_subcommand_token(argv: Sequence[str]) -> str | None:
    resolved = _first_positional_token_with_index(argv)
    if resolved is None:
        return None
    index, _ = resolved
    for token in argv[index + 1 :]:
        if token == "--":
            return None
        if token.startswith("-"):
            continue
        return token
    return None


def _should_startup_bootstrap(argv: Sequence[str]) -> bool:
    if any(token in {"--help", "-h", "--version"} for token in argv):
        return False
    top_level = _first_positional_token(argv)
    if top_level is None:
        return True
    if top_level in {"context", "session", "completion", "doctor"}:
        return False
    subcommand = _first_subcommand_token(argv)
    if top_level == "models" and subcommand in {None, "list", "show"}:
        return False
    if top_level == "config" and subcommand in {"show", "get"}:
        return False
    if top_level == "work" and subcommand in {None, "list", "show", "sessions", "current"}:
        return False
    return not (
        top_level == "spawn"
        and subcommand in {"list", "show", "stats", "wait", "files", "log", "report"}
    )


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
    if not (cleaned_args and cleaned_args[0] == "mars"):
        cleaned_args, passthrough_args = _split_passthrough_args(cleaned_args)
        options = options.model_copy(update={"passthrough_args": passthrough_args})
    agent_mode = (
        agent_mode_enabled() and not options.force_human and not _interactive_terminal_attached()
    )
    if agent_mode and not options.output_explicit:
        options = options.model_copy(update={"output": OutputConfig(format="json")})

    if cleaned_args and cleaned_args[0] == "mars":
        _run_mars_passthrough(cleaned_args[1:], output_format=options.output.format)

    if agent_mode and (not cleaned_args or _is_root_help_request(cleaned_args)):
        _print_agent_root_help()
        return

    _validate_top_level_command(cleaned_args, global_harness=options.harness)

    if not agent_mode_enabled() and _should_startup_bootstrap(cleaned_args):
        try:
            from meridian.lib.config.settings import resolve_project_root
            from meridian.lib.ops.config import ensure_runtime_state_bootstrap_sync

            repo_root = resolve_project_root()
            ensure_runtime_state_bootstrap_sync(repo_root)
        except Exception:
            pass

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
