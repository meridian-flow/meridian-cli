"""CLI command handlers for work.* operations."""

from collections.abc import Callable
from functools import partial
from typing import Annotated, Any

from cyclopts import App, Parameter

from meridian.lib.core.context import RuntimeContext
from meridian.lib.ops.manifest import get_operations_for_surface
from meridian.lib.ops.work import (
    WorkClearInput,
    WorkDashboardInput,
    WorkDoneInput,
    WorkListInput,
    WorkShowInput,
    WorkStartInput,
    WorkSwitchInput,
    WorkUpdateInput,
    work_clear_sync,
    work_dashboard_sync,
    work_done_sync,
    work_list_sync,
    work_show_sync,
    work_start_sync,
    work_switch_sync,
    work_update_sync,
)

Emitter = Callable[[Any], None]


def _runtime_chat_id() -> str:
    return RuntimeContext.from_environment().chat_id


def _work_dashboard(emit: Emitter) -> None:
    emit(work_dashboard_sync(WorkDashboardInput()))


def _work_start(
    emit: Emitter,
    label: Annotated[
        str,
        Parameter(help="Label used to derive the work item slug."),
    ],
    description: Annotated[
        str,
        Parameter(name="--description", help="Optional work item description."),
    ] = "",
) -> None:
    emit(
        work_start_sync(
            WorkStartInput(
                label=label,
                description=description,
                chat_id=_runtime_chat_id(),
            )
        )
    )


def _work_list(
    emit: Emitter,
    active: Annotated[
        bool,
        Parameter(name="--active", help='Hide items with status "done".'),
    ] = False,
) -> None:
    emit(work_list_sync(WorkListInput(active=active)))


def _work_show(
    emit: Emitter,
    work_id: Annotated[
        str,
        Parameter(help="Work item id."),
    ],
) -> None:
    emit(work_show_sync(WorkShowInput(work_id=work_id)))


def _work_update(
    emit: Emitter,
    work_id: Annotated[
        str,
        Parameter(help="Work item id."),
    ],
    status: Annotated[
        str | None,
        Parameter(name="--status", help="New work status label."),
    ] = None,
    description: Annotated[
        str | None,
        Parameter(name="--description", help="Updated work item description."),
    ] = None,
) -> None:
    emit(
        work_update_sync(
            WorkUpdateInput(
                work_id=work_id,
                status=status,
                description=description,
            )
        )
    )


def _work_done(
    emit: Emitter,
    work_id: Annotated[
        str,
        Parameter(help="Work item id."),
    ],
) -> None:
    emit(work_done_sync(WorkDoneInput(work_id=work_id)))


def _work_switch(
    emit: Emitter,
    work_id: Annotated[
        str,
        Parameter(help="Work item id."),
    ],
) -> None:
    emit(work_switch_sync(WorkSwitchInput(work_id=work_id, chat_id=_runtime_chat_id())))


def _work_clear(emit: Emitter) -> None:
    emit(work_clear_sync(WorkClearInput(chat_id=_runtime_chat_id())))


def register_work_commands(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    """Register work CLI commands using registry metadata as source of truth."""

    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "work.start": lambda: partial(_work_start, emit),
        "work.list": lambda: partial(_work_list, emit),
        "work.show": lambda: partial(_work_show, emit),
        "work.update": lambda: partial(_work_update, emit),
        "work.done": lambda: partial(_work_done, emit),
        "work.switch": lambda: partial(_work_switch, emit),
        "work.clear": lambda: partial(_work_clear, emit),
    }

    registered: set[str] = set()
    descriptions: dict[str, str] = {}

    for op in get_operations_for_surface("cli"):
        if op.cli_group != "work":
            continue
        handler_factory = handlers.get(op.name)
        if handler_factory is None:
            raise ValueError(f"No CLI handler for '{op.name}'")
        handler = handler_factory()
        handler.__name__ = f"cmd_work_{op.cli_name}"
        app.command(handler, name=op.cli_name, help=op.description)
        registered.add(f"work.{op.cli_name}")
        descriptions[op.name] = op.description

    app.default(partial(_work_dashboard, emit))
    return registered, descriptions
