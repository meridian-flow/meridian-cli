"""Non-core command registrations for the main CLI router."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, Protocol, cast

from cyclopts import App, Parameter

from meridian.cli.streaming_serve import streaming_serve


class _GlobalOptionsLike(Protocol):
    harness: str | None


def _normalize_completion_shell(shell: str) -> Literal["bash", "zsh", "fish"]:
    normalized = shell.strip().lower()
    if normalized not in {"bash", "zsh", "fish"}:
        raise ValueError("Unsupported shell. Expected one of: bash, zsh, fish.")
    return cast("Literal['bash', 'zsh', 'fish']", normalized)


def register_misc_commands(
    *,
    app: App,
    completion_app: App,
    streaming_app: App,
    emit: Callable[[object], None],
    get_global_options: Callable[[], _GlobalOptionsLike],
) -> None:
    @app.command(name="app")
    def app_command(
        uds: Annotated[
            str | None,
            Parameter(
                name="--uds",
                help="Unix domain socket path for the app server (default: .meridian/app.sock).",
            ),
        ] = None,
        port: Annotated[
            int | None,
            Parameter(
                name="--port",
                help=(
                    "TCP port for the app server (default: 7676). "
                    "Enables TCP binding instead of Unix socket."
                ),
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
            port=port,
            proxy=proxy,
            debug=debug,
            allow_unsafe_no_permissions=allow_unsafe_no_permissions,
        )

    def _emit_completion(shell: str) -> None:
        normalized = _normalize_completion_shell(shell)
        print(app.generate_completion(shell=normalized))

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
            Parameter(
                name="--shell",
                help="Shell to generate completion for (bash, zsh, or fish).",
            ),
        ] = "bash",
        output: Annotated[
            str | None,
            Parameter(
                name="--output",
                help="Optional file path where completion script is written.",
            ),
        ] = None,
        add_to_startup: Annotated[
            bool,
            Parameter(
                name="--add-to-startup",
                help="Append completion setup to shell startup files.",
            ),
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
        options = cast("_GlobalOptionsLike", get_global_options())
        resolved_harness = (harness or options.harness or "").strip()
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

    @app.command(name="context")
    def context_cmd(
        name: Annotated[
            str | None,
            Parameter(
                help=(
                    "Optional context name to print as an absolute path "
                    "(work, kb, or work.archive)."
                ),
            ),
        ] = None,
        verbose: Annotated[
            bool,
            Parameter(
                name="--verbose",
                help="Show source/path/resolved details for each context.",
            ),
        ] = False,
    ) -> None:
        """Query configured context paths."""

        from meridian.lib.ops.context import ContextInput, context_sync

        output = context_sync(ContextInput(verbose=verbose))
        if name is None:
            emit(output)
            return
        emit(output.resolve_name(name))
