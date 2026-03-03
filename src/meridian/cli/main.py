"""Cyclopts CLI entry point for meridian."""

from __future__ import annotations

import json
import logging
import os
import sys
from contextvars import ContextVar
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, cast

from cyclopts import App, Parameter

from meridian import __version__
from meridian.cli.config_cmd import register_config_commands
from meridian.cli.doctor_cmd import register_doctor_command
from meridian.cli.models_cmd import register_models_commands
from meridian.cli.output import OutputConfig, normalize_output_format
from meridian.cli.output import emit as emit_output
from meridian.cli.report_cmd import register_report_commands
from meridian.cli.skills_cmd import register_skills_commands
from meridian.cli.space import register_space_commands
from meridian.lib.config._paths import resolve_repo_root
from meridian.lib.ops.spawn import SpawnActionOutput
from meridian.lib.ops.space import SpaceActionOutput
from meridian.lib.space import space_file
from meridian.lib.space.launch import SpaceLaunchRequest, cleanup_orphaned_locks, launch_primary
from meridian.lib.space.session_store import SessionRecord, cleanup_stale_sessions, resolve_session_ref
from meridian.lib.space.summary import generate_space_summary
from meridian.lib.state.paths import resolve_all_spaces_dir, resolve_space_dir
from meridian.lib.types import SpaceId
from meridian.server.main import run_server

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)
_SPAWN_ERROR_TEXT_LIMIT = 2000
_SPAWN_ERROR_TRUNCATED_SUFFIX = "... [truncated, full output in spawn logs]"

_AGENT_ROOT_HELP = """Usage: meridian COMMAND [ARGS]

Meridian orchestrator CLI

Commands:
  spawn: Spawn and manage subagents
  report: Manage spawn reports
  models: Model catalog commands
  skills: Skills catalog commands
"""


@dataclass(frozen=True, slots=True)
class GlobalOptions:
    """Top-level options that apply to all commands."""

    output: OutputConfig
    config_file: str | None = None
    yes: bool = False
    no_input: bool = False
    output_explicit: bool = False


_GLOBAL_OPTIONS: ContextVar[GlobalOptions | None] = ContextVar("_GLOBAL_OPTIONS", default=None)


@dataclass(frozen=True, slots=True)
class _ResolvedContinueTarget:
    space: space_file.SpaceRecord
    session: SessionRecord


def get_global_options() -> GlobalOptions:
    """Return parsed global options for current command."""

    default = GlobalOptions(output=OutputConfig(format="text"))
    return _GLOBAL_OPTIONS.get() or default


def _spawn_spawn_metadata_line(payload: SpawnActionOutput) -> str:
    duration = f"{payload.duration_secs:.1f}s" if payload.duration_secs is not None else "-"
    exit_code = str(payload.exit_code) if payload.exit_code is not None else "-"
    return " ".join(
        (
            f"spawn_id={payload.spawn_id or '-'}",
            f"model={payload.model or '-'}",
            f"harness={payload.harness_id or '-'}",
            f"status={payload.status}",
            f"duration={duration}",
            f"exit_code={exit_code}",
        )
    )


def _find_spawn_report_file(spawn_id: str) -> Path | None:
    try:
        repo_root = resolve_repo_root()
    except Exception:
        return None

    selected_space = os.getenv("MERIDIAN_SPACE_ID", "").strip()
    if selected_space:
        selected_path = resolve_space_dir(repo_root, selected_space) / "spawns" / spawn_id / "report.md"
        if selected_path.is_file():
            return selected_path

    spaces_dir = resolve_all_spaces_dir(repo_root)
    if not spaces_dir.is_dir():
        return None
    for space_dir in sorted(spaces_dir.iterdir()):
        if not space_dir.is_dir():
            continue
        candidate = space_dir / "spawns" / spawn_id / "report.md"
        if candidate.is_file():
            return candidate
    return None


def _read_spawn_report_text(spawn_id: str) -> str | None:
    report_file = _find_spawn_report_file(spawn_id)
    if report_file is None:
        return None
    text = report_file.read_text(encoding="utf-8", errors="ignore").strip()
    return text or None


def _truncate_spawn_error_text(text: str) -> str:
    normalized = text.strip()
    if len(normalized) <= _SPAWN_ERROR_TEXT_LIMIT:
        return normalized
    keep = max(_SPAWN_ERROR_TEXT_LIMIT - len(_SPAWN_ERROR_TRUNCATED_SUFFIX), 0)
    return f"{normalized[:keep].rstrip()}{_SPAWN_ERROR_TRUNCATED_SUFFIX}"


def _truncate_spawn_failure_fields(payload: SpawnActionOutput) -> SpawnActionOutput:
    if payload.status != "failed":
        return payload
    message = (
        _truncate_spawn_error_text(payload.message) if payload.message is not None else None
    )
    error = _truncate_spawn_error_text(payload.error) if payload.error is not None else None
    return replace(payload, message=message, error=error)


def _emit_spawn_text(payload: SpawnActionOutput) -> None:
    print(_spawn_spawn_metadata_line(payload), file=sys.stderr)
    if payload.warning:
        print(f"warning: {payload.warning}", file=sys.stderr)

    if payload.background and payload.status == "running" and payload.spawn_id is not None:
        print(payload.spawn_id)
        return

    if payload.spawn_id is None:
        # No stable spawn ID to resolve report from (e.g. preflight failure); defer to default emit.
        emit_output(payload, OutputConfig(format="text"))
        return

    report_text = _read_spawn_report_text(payload.spawn_id)
    if report_text is None:
        print(f"warning: no report extracted for spawn '{payload.spawn_id}'", file=sys.stderr)
        if payload.status == "failed":
            fallback_parts = []
            if payload.message is not None and payload.message.strip():
                fallback_parts.append(payload.message.strip())
            if payload.error is not None and payload.error.strip():
                fallback_parts.append(f"error={payload.error.strip()}")
            if fallback_parts:
                print(_truncate_spawn_error_text("  ".join(fallback_parts)), file=sys.stderr)
        return
    if payload.status == "failed":
        report_text = _truncate_spawn_error_text(report_text)
    print(report_text)


def emit(payload: object) -> None:
    """Write command output using current output format settings."""
    options = get_global_options()
    if (
        options.output.format == "text"
        and isinstance(payload, SpawnActionOutput)
        and payload.command == "spawn.create"
        and payload.status != "dry-run"
    ):
        if payload.spawn_id is not None:
            _emit_spawn_text(payload)
        else:
            emit_output(_truncate_spawn_failure_fields(payload), OutputConfig(format="text"))
        return
    emit_output(payload, options.output)


def _extract_global_options(argv: Sequence[str]) -> tuple[list[str], GlobalOptions]:
    json_mode = False
    porcelain_mode = False
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
        if arg == "--porcelain":
            porcelain_mode = True
            output_explicit = True
            i += 1
            continue
        if arg == "--no-porcelain":
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
        porcelain_mode=porcelain_mode,
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


def _agent_mode_enabled() -> bool:
    return bool(os.getenv("MERIDIAN_SPACE_ID", "").strip())


app = App(
    name="meridian",
    help="Meridian orchestrator CLI",
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
        Parameter(name="--format", help="Set output format: text, json, or porcelain."),
    ] = None,
    config_file: Annotated[
        str | None,
        Parameter(name="--config", help="Path to a user config TOML overlay."),
    ] = None,
    porcelain: Annotated[
        bool,
        Parameter(
            name="--porcelain",
            help="Emit stable tab-separated key/value output.",
            show=False,
        ),
    ] = False,
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
        Parameter(name="--permission", help="Permission tier for harness execution."),
    ] = None,
    unsafe: Annotated[
        bool,
        Parameter(name="--unsafe", help="Allow unsafe execution mode."),
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
            porcelain_mode=porcelain,
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
        unsafe=unsafe,
        autocompact=autocompact,
        dry_run=dry_run,
        harness_args=harness_args,
    )


@app.command(name="serve")
def serve() -> None:
    """Start FastMCP server on stdio."""

    run_server()


space_app = App(name="space", help="Space lifecycle commands", help_formatter="plain")
spawn_app = App(name="spawn", help="Spawn management commands", help_formatter="plain")
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
) -> space_file.SpaceRecord:
    if force_new and explicit_space is not None:
        raise ValueError("Cannot combine --new with --space.")

    if explicit_space is not None:
        record = space_file.get_space(repo_root, explicit_space)
        if record is None:
            raise ValueError(f"Space '{explicit_space}' not found")
        return record

    if force_new:
        return space_file.create_space(repo_root)

    spaces = space_file.list_spaces(repo_root)
    active = [record for record in spaces if record.status == "active"]
    if active:
        return max(active, key=lambda record: record.created_at)
    return space_file.create_space(repo_root)


def _run_primary_launch(
    *,
    new: bool,
    space: str | None,
    continue_ref: str | None,
    model: str,
    harness: str | None,
    agent: str | None,
    permission_tier: str | None,
    unsafe: bool,
    autocompact: int | None,
    dry_run: bool,
    harness_args: tuple[str, ...],
) -> None:
    """Shared primary launch flow for root command entry."""

    repo_root = resolve_repo_root()
    explicit_space = space.strip() if space is not None and space.strip() else None
    normalized_continue_ref = continue_ref.strip() if continue_ref is not None else ""
    resume_target = normalized_continue_ref if normalized_continue_ref else None

    selected: space_file.SpaceRecord
    continue_harness_session_id: str | None = None
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
        continue_harness_session_id = resolved_continue.session.harness_session_id.strip() or None
        if continue_harness_session_id is None:
            raise ValueError(
                f"Session '{resume_target}' in space '{selected.id}' cannot be continued "
                "because it has no harness session id."
            )
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
            harness=harness,
            agent=agent,
            autocompact=autocompact,
            passthrough_args=harness_args,
            fresh=fresh,
            pinned_context="",
            dry_run=dry_run,
            permission_tier=permission_tier,
            unsafe=unsafe,
            continue_harness_session_id=continue_harness_session_id,
        ),
    )

    transitioned = space_file.update_space_status(
        repo_root,
        selected.id,
        launch_result.final_state,
    )
    emit(
        SpaceActionOutput(
            space_id=selected.id,
            state=transitioned.status,
            message=(
                "Space resume dry-run."
                if dry_run and resume_target is not None
                else (
                    "Space launch dry-run."
                    if dry_run
                    else ("Space resumed." if resume_target is not None else "Space session finished.")
                )
            ),
            exit_code=launch_result.exit_code,
            command=launch_result.command if dry_run else (),
            lock_path=launch_result.lock_path.as_posix(),
            summary_path=summary_path.as_posix(),
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

    if explicit_space is not None:
        selected = space_file.get_space(repo_root, explicit_space)
        if selected is None:
            raise ValueError(f"Space '{explicit_space}' not found")
        session = resolve_session_ref(resolve_space_dir(repo_root, selected.id), normalized)
        if session is None:
            raise ValueError(
                f"Session '{normalized}' not found in space '{selected.id}'."
            )
        return _ResolvedContinueTarget(space=selected, session=session)

    matches: list[_ResolvedContinueTarget] = []
    for record in space_file.list_spaces(repo_root):
        space_dir = resolve_space_dir(repo_root, record.id)
        session = resolve_session_ref(space_dir, normalized)
        if session is None:
            continue
        matches.append(_ResolvedContinueTarget(space=record, session=session))

    if not matches:
        raise ValueError(f"Session '{normalized}' not found.")
    if len(matches) > 1:
        spaces = ", ".join(sorted(match.space.id for match in matches))
        raise ValueError(
            f"Session '{normalized}' is ambiguous across spaces ({spaces}). "
            "Use --space to disambiguate."
        )
    return matches[0]


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
    """Emit an error in the current output format and exit.

    In JSON/porcelain mode, emits a structured error object to stdout so
    callers (especially agent-mode subprocesses) can parse it reliably.
    Always prints human-readable text to stderr for logs/humans.
    """
    print(f"error: {message}", file=sys.stderr)
    opts = _GLOBAL_OPTIONS.get()
    if opts is not None and opts.output.format == "json":
        print(json.dumps({"error": message, "exit_code": exit_code}))
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
        "--porcelain",
        "--no-porcelain",
        "--yes",
        "--no-yes",
        "--no-input",
        "--no-no-input",
        "--human",
        "--new",
        "--no-new",
        "--unsafe",
        "--no-unsafe",
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

    from meridian.lib.logging import configure_logging

    args = list(sys.argv[1:] if argv is None else argv)

    # Configure logging early so structlog warnings go to stderr, not stdout.
    # Check if structured output is requested — only JSON format suppresses
    # human-readable log formatting.  "--format text" or "--format porcelain"
    # should NOT switch logging to JSON mode.
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
                    cleanup_stale_sessions(space_dir, repo_root=repo_root)
        except Exception:
            logger.debug("orphaned lock cleanup failed", exc_info=True)

    args, force_human = _extract_human_flag(args)
    cleaned_args, options = _extract_global_options(args)

    agent_mode = _agent_mode_enabled() and not force_human
    if agent_mode and not options.output_explicit:
        options = replace(options, output=OutputConfig(format="json"))

    if agent_mode and (not cleaned_args or _is_root_help_request(cleaned_args)):
        _print_agent_root_help()
        return

    _validate_top_level_command(cleaned_args)

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
        if options.config_file is not None:
            if prior_user_config is None:
                os.environ.pop("MERIDIAN_CONFIG", None)
            else:
                os.environ["MERIDIAN_CONFIG"] = prior_user_config
        _GLOBAL_OPTIONS.reset(token)


_register_group_commands()
