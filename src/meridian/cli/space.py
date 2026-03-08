"""CLI command handlers for space.* operations."""


from collections.abc import Callable
from functools import partial
from typing import Annotated, Any

from cyclopts import App, Parameter

from meridian.lib.ops.manifest import get_operations_for_surface
from meridian.lib.ops.space import (
    SpaceListInput,
    SpaceResumeInput,
    SpaceShowInput,
    SpaceStartInput,
    space_list_sync,
    space_resume_sync,
    space_show_sync,
    space_start_sync,
)


def _space_start(
    emit: Any,
    name: Annotated[
        str | None,
        Parameter(name="--name", help="Optional space name."),
    ] = None,
    model: Annotated[
        str,
        Parameter(name="--model", help="Model id or alias for space harness."),
    ] = "",
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
    emit(
        space_start_sync(
            SpaceStartInput(
                name=name,
                model=model,
                autocompact=autocompact,
                dry_run=dry_run,
                harness_args=harness_args,
            )
        )
    )


def _space_resume(
    emit: Any,
    space: Annotated[
        str | None,
        Parameter(
            name=["--space-id", "--space"],
            help="Space id to resume.",
        ),
    ] = None,
    fresh: Annotated[
        bool,
        Parameter(name="--fresh", help="Start a new harness process before resume."),
    ] = False,
    model: Annotated[
        str,
        Parameter(name="--model", help="Override model id or alias."),
    ] = "",
    autocompact: Annotated[
        int | None,
        Parameter(name="--autocompact", help="Auto-compact threshold in messages."),
    ] = None,
    harness_args: Annotated[
        tuple[str, ...],
        Parameter(
            name="--harness-arg",
            help="Additional harness arguments (repeatable).",
            negative_iterable=(),
        ),
    ] = (),
) -> None:
    emit(
        space_resume_sync(
            SpaceResumeInput(
                space=space,
                fresh=fresh,
                model=model,
                autocompact=autocompact,
                harness_args=harness_args,
            )
        )
    )


def _space_list(
    emit: Any,
    limit: Annotated[
        int,
        Parameter(name="--limit", help="Maximum number of spaces to return."),
    ] = 10,
) -> None:
    emit(space_list_sync(SpaceListInput(limit=limit)))


def _space_show(emit: Any, space: str) -> None:
    emit(space_show_sync(SpaceShowInput(space=space)))


def register_space_commands(app: App, emit: Any) -> tuple[set[str], dict[str, str]]:
    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "space.start": lambda: partial(_space_start, emit),
        "space.resume": lambda: partial(_space_resume, emit),
        "space.list": lambda: partial(_space_list, emit),
        "space.show": lambda: partial(_space_show, emit),
    }

    registered: set[str] = set()
    descriptions: dict[str, str] = {}

    for op in get_operations_for_surface("cli"):
        if op.cli_group != "space":
            continue
        handler_factory = handlers.get(op.name)
        if handler_factory is None:
            raise ValueError(f"No CLI handler registered for operation '{op.name}'")
        handler = handler_factory()
        handler.__name__ = f"cmd_{op.cli_group}_{op.cli_name}"
        app.command(handler, name=op.cli_name, help=op.description)
        registered.add(f"{op.cli_group}.{op.cli_name}")
        descriptions[op.name] = op.description

    return registered, descriptions
