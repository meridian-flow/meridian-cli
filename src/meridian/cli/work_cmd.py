"""CLI command handlers for work.* operations."""

from collections.abc import Callable
from functools import partial
from typing import Annotated, Any

from cyclopts import App, Parameter

from meridian.cli.registration import register_manifest_cli_group
from meridian.lib.core.context import RuntimeContext
from meridian.lib.ops.work_dashboard import (
    WorkDashboardInput,
    WorkListInput,
    WorkSessionsInput,
    WorkShowInput,
    work_dashboard_sync,
    work_list_sync,
    work_sessions_sync,
    work_show_sync,
)
from meridian.lib.ops.work_lifecycle import (
    WorkClearInput,
    WorkDoneInput,
    WorkRenameInput,
    WorkReopenInput,
    WorkStartInput,
    WorkSwitchInput,
    WorkUpdateInput,
    work_clear_sync,
    work_done_sync,
    work_rename_sync,
    work_reopen_sync,
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
    done: Annotated[
        bool,
        Parameter(name="--done", help="Show only done/archived items."),
    ] = False,
) -> None:
    emit(work_list_sync(WorkListInput(done_only=done)))


def _work_show(
    emit: Emitter,
    work_id: Annotated[
        str,
        Parameter(help="Work item id."),
    ],
) -> None:
    emit(work_show_sync(WorkShowInput(work_id=work_id)))


def _work_sessions(
    emit: Emitter,
    work_id: Annotated[
        str,
        Parameter(
            help=(
                "Work item id. Defaults to MERIDIAN_WORK_ID, "
                "then the active work item attached to this session."
            )
        ),
    ] = "",
    all: Annotated[
        bool,
        Parameter(name="--all", help="Include historical sessions."),
    ] = False,
) -> None:
    emit(work_sessions_sync(WorkSessionsInput(work_id=work_id, all=all)))


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


def _work_reopen(
    emit: Emitter,
    work_id: Annotated[
        str,
        Parameter(help="Work item id."),
    ],
) -> None:
    emit(work_reopen_sync(WorkReopenInput(work_id=work_id)))


def _work_rename(
    emit: Emitter,
    work_id: Annotated[
        str,
        Parameter(help="Current work item id."),
    ],
    new_name: Annotated[
        str,
        Parameter(help="New name (slug) for the work item."),
    ],
) -> None:
    emit(
        work_rename_sync(
            WorkRenameInput(work_id=work_id, new_name=new_name, chat_id=_runtime_chat_id())
        )
    )


def _work_clear(emit: Emitter) -> None:
    emit(work_clear_sync(WorkClearInput(chat_id=_runtime_chat_id())))


def register_work_commands(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    """Register work CLI commands using registry metadata as source of truth."""

    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "work.start": lambda: partial(_work_start, emit),
        "work.list": lambda: partial(_work_list, emit),
        "work.show": lambda: partial(_work_show, emit),
        "work.sessions": lambda: partial(_work_sessions, emit),
        "work.update": lambda: partial(_work_update, emit),
        "work.done": lambda: partial(_work_done, emit),
        "work.switch": lambda: partial(_work_switch, emit),
        "work.reopen": lambda: partial(_work_reopen, emit),
        "work.rename": lambda: partial(_work_rename, emit),
        "work.clear": lambda: partial(_work_clear, emit),
    }
    return register_manifest_cli_group(
        app,
        group="work",
        handlers=handlers,
        emit=emit,
        default_handler=partial(_work_dashboard, emit),
    )
