"""CLI command handlers for report.* operations."""

import sys
from collections.abc import Callable
from functools import partial
from typing import Annotated, Any

from cyclopts import Parameter

from meridian.cli.registration import register_manifest_cli_group
from meridian.lib.ops.report import (
    ReportCreateInput,
    ReportSearchInput,
    ReportShowInput,
    report_create_sync,
    report_search_sync,
    report_show_sync,
)

Emitter = Callable[[Any], None]


def _report_create(
    emit: Emitter,
    content: Annotated[
        str,
        Parameter(help="Report markdown content (ignored when --stdin is set)."),
    ] = "",
    spawn: Annotated[
        str | None,
        Parameter(name="--spawn", help="Spawn id or reference (e.g. @latest)."),
    ] = None,
    stdin: Annotated[
        bool,
        Parameter(name="--stdin", help="Read report content from stdin."),
    ] = False,
) -> None:
    text = sys.stdin.read() if stdin else content
    emit(
        report_create_sync(
            ReportCreateInput(
                content=text,
                spawn_id=spawn,
            )
        )
    )


def _report_show(
    emit: Emitter,
    spawn: Annotated[
        str | None,
        Parameter(name="--spawn", help="Spawn id or reference (e.g. @latest)."),
    ] = None,
) -> None:
    emit(
        report_show_sync(
            ReportShowInput(
                spawn_id=spawn,
            )
        )
    )


def _report_search(
    emit: Emitter,
    query: Annotated[
        str,
        Parameter(help="Case-insensitive text query."),
    ] = "",
    spawn: Annotated[
        str | None,
        Parameter(name="--spawn", help="Optional spawn id/reference to scope the search."),
    ] = None,
    limit: Annotated[
        int,
        Parameter(name="--limit", help="Maximum number of matching reports to return."),
    ] = 20,
) -> None:
    emit(
        report_search_sync(
            ReportSearchInput(
                query=query,
                spawn_id=spawn,
                limit=limit,
            )
        )
    )


def register_report_commands(app: Any, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "report.create": lambda: partial(_report_create, emit),
        "report.show": lambda: partial(_report_show, emit),
        "report.search": lambda: partial(_report_search, emit),
    }
    return register_manifest_cli_group(
        app,
        group="report",
        handlers=handlers,
        default_handler=partial(_report_create, emit),
    )
