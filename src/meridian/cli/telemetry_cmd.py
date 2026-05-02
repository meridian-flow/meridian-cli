"""CLI command handlers for telemetry reader operations."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from functools import partial
from typing import Annotated, Any

from cyclopts import App, Parameter

from meridian.lib.state.user_paths import get_user_home
from meridian.lib.telemetry.query import query_events
from meridian.lib.telemetry.reader import tail_events
from meridian.lib.telemetry.status import ROOTLESS_LIMITATION_NOTE, compute_status

Emitter = Callable[[Any], None]


def _telemetry_dir():
    return get_user_home() / "telemetry"


def _ids_filter(
    *,
    spawn_id: str = "",
    chat_id: str = "",
    work_id: str = "",
) -> dict[str, str] | None:
    filters = {}
    if spawn_id:
        filters["spawn_id"] = spawn_id
    if chat_id:
        filters["chat_id"] = chat_id
    if work_id:
        filters["work_id"] = work_id
    return filters or None


def _write_event(event: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(event, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _telemetry_tail(
    domain: Annotated[
        str | None,
        Parameter(name="--domain", help="Filter by telemetry domain."),
    ] = None,
    spawn_id: Annotated[
        str,
        Parameter(name="--spawn", help="Filter by spawn id."),
    ] = "",
    chat_id: Annotated[
        str,
        Parameter(name="--chat", help="Filter by chat id."),
    ] = "",
    work_id: Annotated[
        str,
        Parameter(name="--work", help="Filter by work id."),
    ] = "",
) -> None:
    """Live stream local telemetry events.

    Rootless MCP stdio server processes write telemetry to stderr only and are not
    visible in local segment readers.
    """
    try:
        for event in tail_events(
            _telemetry_dir(),
            domain=domain,
            ids_filter=_ids_filter(spawn_id=spawn_id, chat_id=chat_id, work_id=work_id),
        ):
            _write_event(event)
    except KeyboardInterrupt:
        return


def _telemetry_query(
    since: Annotated[
        str | None,
        Parameter(name="--since", help="Only include events newer than duration (for example 1h)."),
    ] = None,
    domain: Annotated[
        str | None,
        Parameter(name="--domain", help="Filter by telemetry domain."),
    ] = None,
    spawn_id: Annotated[
        str,
        Parameter(name="--spawn", help="Filter by spawn id."),
    ] = "",
    chat_id: Annotated[
        str,
        Parameter(name="--chat", help="Filter by chat id."),
    ] = "",
    work_id: Annotated[
        str,
        Parameter(name="--work", help="Filter by work id."),
    ] = "",
    limit: Annotated[
        int | None,
        Parameter(name="--limit", help="Maximum events to return."),
    ] = None,
) -> None:
    """Print historical local telemetry events as JSON lines."""
    for event in query_events(
        _telemetry_dir(),
        since=since,
        domain=domain,
        ids_filter=_ids_filter(spawn_id=spawn_id, chat_id=chat_id, work_id=work_id),
        limit=limit,
    ):
        _write_event(event)


def _telemetry_status(emit: Emitter) -> None:
    """Show telemetry sink health and local reader limitations."""
    emit(compute_status(get_user_home()))


def register_telemetry_commands(app: App, emit: Emitter) -> None:
    """Register telemetry CLI commands."""
    app.command(_telemetry_tail, name="tail")
    app.command(_telemetry_query, name="query")
    app.command(partial(_telemetry_status, emit), name="status")
    app.help_epilogue = f"Note: {ROOTLESS_LIMITATION_NOTE}"
