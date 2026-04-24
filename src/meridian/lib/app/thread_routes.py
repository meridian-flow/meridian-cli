"""Thread inspector route handlers.

Endpoints:
    GET /api/threads/{chat_id}/events/{event_id}
    GET /api/threads/{chat_id}/tool-calls/{call_id}
    GET /api/threads/{chat_id}/token-usage

``chat_id`` accepts both chat references (``cN``) and spawn IDs (``pN``).
All data is read from persisted artifacts so these routes work for completed
sessions without requiring an active WebSocket connection.

Event IDs and tool-call IDs are encoded as ``{spawn_id}:{line_index}`` —
stable across restarts because the spawn event log artifact is append-only.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast

from meridian.lib.app.api_models import EventRecord, TokenUsageResponse, ToolCallRecord
from meridian.lib.app.http_types import HTTPExceptionCallable
from meridian.lib.app.inspector import (
    get_event_by_line,
    get_token_usage,
    get_tool_call_by_id,
    get_tool_calls,
    parse_event_id,
)
from meridian.lib.state import spawn_store


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...


def _resolve_spawn_ids_for_thread(runtime_root: Path, chat_id: str) -> list[str]:
    """Return spawn IDs associated with *chat_id*.

    Accepts either a spawn ID (``pN``) or a chat ID (``cN``).  Returns a list
    so callers can iterate over all spawns when aggregating token usage.
    """
    # Direct spawn reference.
    if chat_id.startswith("p"):
        record = spawn_store.get_spawn(runtime_root, chat_id)
        if record is not None:
            return [record.id]
        return []

    # Chat-level lookup: gather all spawns for this chat.
    spawns = spawn_store.list_spawns(runtime_root, filters={"chat_id": chat_id})
    return [s.id for s in spawns]


def register_thread_routes(
    app: object,
    *,
    runtime_root: Path,
    artifact_root: Path,
    http_exception: HTTPExceptionCallable,
) -> None:
    """Register thread inspector routes on *app*."""

    typed_app = cast("_FastAPIApp", app)

    # ------------------------------------------------------------------
    # GET /api/threads/{chat_id}/events/{event_id}
    # ------------------------------------------------------------------

    async def get_event(chat_id: str, event_id: str) -> EventRecord:
        """Return the raw event payload at the given event ID.

        ``event_id`` must be in ``{spawn_id}:{line_index}`` format.  The spawn
        must be associated with *chat_id*.
        """
        parsed = parse_event_id(event_id)
        if parsed is None:
            raise http_exception(
                status_code=400,
                detail=(
                    f"Invalid event_id format: '{event_id}'."
                    " Expected '{spawn_id}:{line_index}'."
                ),
            )
        spawn_id, line_index = parsed

        valid_ids = _resolve_spawn_ids_for_thread(runtime_root, chat_id)
        if not valid_ids:
            raise http_exception(status_code=404, detail=f"Thread '{chat_id}' not found.")
        if spawn_id not in valid_ids:
            raise http_exception(
                status_code=404,
                detail=f"Event '{event_id}' does not belong to thread '{chat_id}'.",
            )

        record = get_event_by_line(artifact_root, spawn_id, line_index)
        if record is None:
            raise http_exception(
                status_code=404,
                detail=f"Event '{event_id}' not found.",
            )
        return EventRecord(
            event_id=str(record["event_id"]),
            spawn_id=str(record["spawn_id"]),
            line_index=int(cast("int", record["line_index"])),
            payload=cast("dict[str, object]", record["payload"]),
        )

    # ------------------------------------------------------------------
    # GET /api/threads/{chat_id}/tool-calls/{call_id}
    # ------------------------------------------------------------------

    async def get_tool_call(chat_id: str, call_id: str) -> ToolCallRecord:
        """Return tool-call details for the given call ID.

        ``call_id`` encodes the spawn and line position, so the spawn must be
        associated with *chat_id*.
        """
        parsed = parse_event_id(call_id)
        if parsed is None:
            raise http_exception(
                status_code=400,
                detail=(
                    f"Invalid call_id format: '{call_id}'."
                    " Expected '{spawn_id}:{line_index}'."
                ),
            )
        spawn_id, _ = parsed

        valid_ids = _resolve_spawn_ids_for_thread(runtime_root, chat_id)
        if not valid_ids:
            raise http_exception(status_code=404, detail=f"Thread '{chat_id}' not found.")
        if spawn_id not in valid_ids:
            raise http_exception(
                status_code=404,
                detail=f"Tool call '{call_id}' does not belong to thread '{chat_id}'.",
            )

        record = get_tool_call_by_id(artifact_root, call_id)
        if record is None:
            raise http_exception(
                status_code=404,
                detail=f"Tool call '{call_id}' not found.",
            )
        return ToolCallRecord(
            call_id=str(record["call_id"]),
            spawn_id=str(record["spawn_id"]),
            line_index=int(cast("int", record["line_index"])),
            payload=cast("dict[str, object]", record["payload"]),
        )

    # ------------------------------------------------------------------
    # GET /api/threads/{chat_id}/tool-calls  (list all)
    # ------------------------------------------------------------------

    async def list_tool_calls(chat_id: str) -> dict[str, object]:
        """Return all tool calls for a thread, in source order across all spawns."""
        spawn_ids = _resolve_spawn_ids_for_thread(runtime_root, chat_id)
        if not spawn_ids:
            raise http_exception(status_code=404, detail=f"Thread '{chat_id}' not found.")

        all_calls: list[ToolCallRecord] = []
        for spawn_id in spawn_ids:
            for record in get_tool_calls(artifact_root, spawn_id):
                all_calls.append(
                    ToolCallRecord(
                        call_id=str(record["call_id"]),
                        spawn_id=str(record["spawn_id"]),
                        line_index=int(cast("int", record["line_index"])),
                        payload=cast("dict[str, object]", record["payload"]),
                    )
                )
        return {"tool_calls": [tc.model_dump() for tc in all_calls]}

    # ------------------------------------------------------------------
    # GET /api/threads/{chat_id}/token-usage
    # ------------------------------------------------------------------

    async def get_token_usage_endpoint(chat_id: str) -> TokenUsageResponse:
        """Return aggregated token usage for a thread.

        When multiple spawns exist, the spawn with the highest total input
        tokens is used (matching the existing ``extract_usage_from_artifacts``
        selection logic which picks the best candidate).
        """
        spawn_ids = _resolve_spawn_ids_for_thread(runtime_root, chat_id)
        if not spawn_ids:
            raise http_exception(status_code=404, detail=f"Thread '{chat_id}' not found.")

        # Use the latest spawn (last in sorted list) as primary.
        primary_spawn_id = spawn_ids[-1]
        usage = get_token_usage(artifact_root, primary_spawn_id)
        return TokenUsageResponse(
            spawn_id=primary_spawn_id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            total_cost_usd=usage.total_cost_usd,
        )

    typed_app.get("/api/threads/{chat_id}/events/{event_id}")(get_event)
    typed_app.get("/api/threads/{chat_id}/tool-calls/{call_id}")(get_tool_call)
    typed_app.get("/api/threads/{chat_id}/tool-calls")(list_tool_calls)
    typed_app.get("/api/threads/{chat_id}/token-usage")(get_token_usage_endpoint)


__all__ = ["register_thread_routes"]
