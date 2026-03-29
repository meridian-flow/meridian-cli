"""CLI command handlers for session.* operations."""

from collections.abc import Callable
from functools import partial
from typing import Annotated, Any

from cyclopts import App, Parameter

from meridian.cli.registration import register_manifest_cli_group
from meridian.lib.ops.session_log import SessionLogInput, session_log_sync
from meridian.lib.ops.session_search import SessionSearchInput, session_search_sync

Emitter = Callable[[Any], None]


def _session_log(
    emit: Emitter,
    ref: Annotated[
        str,
        Parameter(
            help=("Session reference: chat id (c123), spawn id (p123), or harness session id.")
        ),
    ] = "",
    compaction: Annotated[
        int,
        Parameter(
            name=["--compaction", "-c"],
            help=(
                "Compaction segment index (0 = after last boundary, 1 = previous segment, etc.)."
            ),
        ),
    ] = 0,
    last_n: Annotated[
        int | None,
        Parameter(
            name=["--last", "-n"],
            help=(
                "Number of messages to show inside the selected segment "
                "(default: 5; use -n 0 for all)."
            ),
        ),
    ] = 5,
    offset: Annotated[
        int,
        Parameter(
            name="--offset",
            help="Skip this many messages from the end of the selected segment.",
        ),
    ] = 0,
    file_path: Annotated[
        str | None,
        Parameter(
            name="--file",
            help="Read this session JSONL file directly instead of resolving REF.",
        ),
    ] = None,
) -> None:
    mapped_last_n: int | None = None if last_n == 0 else last_n
    emit(
        session_log_sync(
            SessionLogInput(
                ref=ref,
                compaction=compaction,
                last_n=mapped_last_n,
                offset=offset,
                file_path=file_path,
            )
        )
    )


def _session_search(
    emit: Emitter,
    query: Annotated[
        str,
        Parameter(help="Case-insensitive text query."),
    ],
    ref: Annotated[
        str,
        Parameter(
            help=("Session reference: chat id (c123), spawn id (p123), or harness session id.")
        ),
    ],
    file_path: Annotated[
        str | None,
        Parameter(
            name="--file",
            help="Read this session JSONL file directly instead of resolving REF.",
        ),
    ] = None,
) -> None:
    emit(
        session_search_sync(
            SessionSearchInput(
                query=query,
                ref=ref,
                file_path=file_path,
            )
        )
    )


def register_session_commands(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    """Register session CLI commands using registry metadata as source of truth."""

    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "session.log": lambda: partial(_session_log, emit),
        "session.search": lambda: partial(_session_search, emit),
    }
    return register_manifest_cli_group(
        app,
        group="session",
        handlers=handlers,
        emit=emit,
        default_handler=None,
    )
