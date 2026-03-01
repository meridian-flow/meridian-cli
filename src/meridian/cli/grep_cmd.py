"""CLI command handler for standalone grep operation."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, Any, Annotated

from cyclopts import Parameter

from meridian.lib.ops.grep import GrepInput, grep_sync
from meridian.lib.ops.registry import get_all_operations

if TYPE_CHECKING:
    from cyclopts import App

Emitter = Callable[[Any], None]


def _grep(
    emit: Emitter,
    pattern: str,
    space_id: Annotated[
        str | None,
        Parameter(name="--space", help="Only search one space."),
    ] = None,
    run_id: Annotated[
        str | None,
        Parameter(name="--run", help="Only search one run (requires --space)."),
    ] = None,
    file_type: Annotated[
        str | None,
        Parameter(name="--type", help="Restrict file type: output, logs, runs, sessions."),
    ] = None,
) -> None:
    emit(
        grep_sync(
            GrepInput(
                pattern=pattern,
                space_id=space_id,
                run_id=run_id,
                file_type=file_type,
            )
        )
    )


def register_grep_command(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    registered: set[str] = set()
    descriptions: dict[str, str] = {}

    for op in get_all_operations():
        if op.name != "grep" or op.mcp_only:
            continue
        handler = partial(_grep, emit)
        handler.__name__ = "cmd_grep"
        app.command(handler, name=op.cli_name, help=op.description)
        registered.add(f"{op.cli_group}.{op.cli_name}")
        descriptions[op.name] = op.description

    return registered, descriptions
