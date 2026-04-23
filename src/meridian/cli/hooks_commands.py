"""CLI command handlers for hooks.* operations."""

from collections.abc import Callable
from functools import partial
from typing import Annotated, Any

from cyclopts import App, Parameter

from meridian.cli.ext_registration import register_extension_cli_group
from meridian.lib.extensions.registry import get_first_party_registry
from meridian.lib.hooks.types import HookEventName
from meridian.lib.ops.hooks import (
    HookCheckInput,
    HookListInput,
    HookRunInput,
    hooks_check_sync,
    hooks_list_sync,
    hooks_run_sync,
)

Emitter = Callable[[Any], None]


def _hooks_list(emit: Emitter) -> None:
    emit(hooks_list_sync(HookListInput()))


def _hooks_check(emit: Emitter) -> None:
    output = hooks_check_sync(HookCheckInput())
    emit(output)
    if not output.ok:
        raise SystemExit(1)


def _hooks_run(
    emit: Emitter,
    name: Annotated[
        str,
        Parameter(help="Hook name to execute manually."),
    ],
    event: Annotated[
        HookEventName | None,
        Parameter(
            name="--event",
            help="Optional event context to simulate (for example: spawn.finalized).",
        ),
    ] = None,
) -> None:
    emit(hooks_run_sync(HookRunInput(name=name, event=event)))


def register_hooks_commands(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    """Register hooks CLI commands using registry metadata as source of truth."""

    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "meridian.hooks.list": lambda: partial(_hooks_list, emit),
        "meridian.hooks.check": lambda: partial(_hooks_check, emit),
        "meridian.hooks.run": lambda: partial(_hooks_run, emit),
    }
    return register_extension_cli_group(
        app,
        registry=get_first_party_registry(),
        group="hooks",
        handlers=handlers,
        command_help_epilogues={
            "meridian.hooks.run": (
                "Examples:\n\n"
                "  meridian hooks run git-autosync\n\n"
                "  meridian hooks run git-autosync --event spawn.finalized\n\n"
                "`hooks run` bypasses interval throttling for manual execution."
            )
        },
        emit=emit,
        default_handler=partial(_hooks_list, emit),
    )
