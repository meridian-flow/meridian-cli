"""AG-UI event replay from raw harness event sequences."""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from ag_ui.core import BaseEvent
from meridian.lib.app.agui_mapping import get_agui_mapper
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.state.history import iter_history_from_seq
from meridian.lib.streaming.drain_policy import TURN_BOUNDARY_EVENT_TYPE

PAGINATION_CURSOR_VERSION = 1


@dataclass(frozen=True)
class PaginationCursor:
    """Opaque cursor payload for AG-UI replay pagination."""

    raw_seq: int
    agui_skip: int
    checkpoint: int
    spawn_idx: int = 0
    v: int = PAGINATION_CURSOR_VERSION


@dataclass(frozen=True)
class PaginatedReplayResult:
    """Page of AG-UI replay events plus continuation metadata."""

    events: list[BaseEvent]
    next_cursor: str | None
    has_more: bool


class AguiReplayTurnState:
    """Track AG-UI run lifecycle events while replaying harness events."""

    def __init__(self, mapper: Any, spawn_id: str) -> None:
        self._mapper = mapper
        self._spawn_id = spawn_id
        self._turn_active = False
        self._error_emitted = False

    def start_replay(self) -> BaseEvent:
        """Start the initial turn for a replay stream."""

        self._turn_active = True
        self._error_emitted = False
        return self._mapper.make_run_started(self._spawn_id)

    def process_turn_boundary(self) -> list[BaseEvent]:
        """Process a synthetic turn boundary and return emitted lifecycle events."""

        events: list[BaseEvent] = []
        if self._turn_active and not self._error_emitted:
            events.append(self._mapper.make_run_finished(self._spawn_id))
        self._turn_active = False
        self._error_emitted = False
        return events

    def prepare_regular_event(self) -> list[BaseEvent]:
        """Return lifecycle events needed before translating a regular event."""

        if self._turn_active:
            return []
        self._turn_active = True
        return [self._mapper.make_run_started(self._spawn_id)]

    def observe_translated_event(self, event: BaseEvent) -> None:
        """Update turn state after one translated AG-UI event."""

        if getattr(event, "type", None) == "RUN_ERROR":
            self._error_emitted = True

    def finish_replay(self) -> list[BaseEvent]:
        """Return terminal lifecycle events for the current replay stream."""

        if self._turn_active and not self._error_emitted:
            return [self._mapper.make_run_finished(self._spawn_id)]
        return []

    def has_terminal_event(self) -> bool:
        """Return whether finish_replay would emit a terminal lifecycle event."""

        return self._turn_active and not self._error_emitted


def encode_pagination_cursor(cursor: PaginationCursor) -> str:
    """Encode cursor to an opaque URL-safe string."""

    payload = {
        "raw_seq": cursor.raw_seq,
        "agui_skip": cursor.agui_skip,
        "checkpoint": cursor.checkpoint,
        "spawn_idx": cursor.spawn_idx,
        "v": cursor.v,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_pagination_cursor(encoded: str) -> PaginationCursor:
    """Decode cursor from an opaque string."""

    try:
        padded = encoded + ("=" * (-len(encoded) % 4))
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(decoded.decode("utf-8"))
    except Exception as exc:
        raise ValueError("Invalid pagination cursor") from exc

    if not isinstance(payload, dict):
        raise ValueError("Invalid pagination cursor")
    payload_map = cast("Mapping[str, object]", payload)

    cursor = PaginationCursor(
        raw_seq=_required_non_negative_int(payload_map, "raw_seq"),
        agui_skip=_required_non_negative_int(payload_map, "agui_skip"),
        checkpoint=_required_non_negative_int(payload_map, "checkpoint"),
        spawn_idx=_required_non_negative_int(payload_map, "spawn_idx"),
        v=_required_non_negative_int(payload_map, "v"),
    )
    if cursor.v != PAGINATION_CURSOR_VERSION:
        raise ValueError("Unsupported pagination cursor version")
    if cursor.checkpoint > cursor.raw_seq:
        raise ValueError("Invalid pagination cursor checkpoint")
    return cursor


def replay_events_to_agui(
    raw_events: list[dict[str, Any]],
    harness_id: HarnessId,
    spawn_id: str,
) -> Iterator[BaseEvent]:
    """Replay raw harness events through a fresh mapper to produce AG-UI events.

    Args:
        raw_events: Raw event dictionaries, seq-enveloped or already stripped.
        harness_id: Harness identifier selecting the mapper.
        spawn_id: Spawn ID used for run started/finished events.

    Yields:
        AG-UI events in order, with run lifecycle boundaries.
    """

    mapper = get_agui_mapper(harness_id)
    turn_state = AguiReplayTurnState(mapper, spawn_id)

    yield turn_state.start_replay()

    for raw_event in raw_events:
        event = _raw_to_harness_event(raw_event)
        if event is None:
            continue

        if event.event_type == TURN_BOUNDARY_EVENT_TYPE:
            yield from turn_state.process_turn_boundary()
            continue

        yield from turn_state.prepare_regular_event()

        for translated in mapper.translate(event):
            yield translated
            turn_state.observe_translated_event(translated)

    yield from turn_state.finish_replay()


def replay_events_paginated(
    history_path: Path,
    harness_id: HarnessId,
    spawn_id: str,
    *,
    limit: int,
    cursor: str | None = None,
) -> PaginatedReplayResult:
    """Paginated AG-UI replay from raw history."""

    if limit <= 0:
        raise ValueError("limit must be positive")

    page_cursor = (
        PaginationCursor(raw_seq=0, agui_skip=0, checkpoint=0)
        if cursor is None
        else decode_pagination_cursor(cursor)
    )

    first_envelope = next(iter_history_from_seq(history_path, start_seq=0, limit=1), None)
    if first_envelope is None:
        return PaginatedReplayResult([], next_cursor=None, has_more=False)

    mapper = get_agui_mapper(harness_id)
    turn_state = AguiReplayTurnState(mapper, spawn_id)
    last_turn_boundary_seq = page_cursor.checkpoint
    next_raw_seq = page_cursor.raw_seq

    collected: list[BaseEvent] = []

    if cursor is None:
        collected.append(turn_state.start_replay())
        if len(collected) >= limit:
            next_cursor = encode_pagination_cursor(
                PaginationCursor(raw_seq=0, agui_skip=0, checkpoint=0)
            )
            return PaginatedReplayResult(collected, next_cursor, has_more=True)
    else:
        turn_state.start_replay()
        if page_cursor.checkpoint > 0:
            turn_state.process_turn_boundary()
        for envelope in iter_history_from_seq(history_path, start_seq=page_cursor.checkpoint):
            seq = envelope.get("seq", -1)
            if not isinstance(seq, int) or seq >= page_cursor.raw_seq:
                break
            event = _raw_to_harness_event(envelope)
            if event is None:
                continue
            last_turn_boundary_seq = _process_replay_event(
                event,
                seq,
                mapper,
                turn_state,
                last_turn_boundary_seq,
            )[1]

    skipped = 0
    for envelope in iter_history_from_seq(history_path, start_seq=page_cursor.raw_seq):
        seq = envelope.get("seq", -1)
        if not isinstance(seq, int):
            continue
        next_raw_seq = seq + 1
        event = _raw_to_harness_event(envelope)
        if event is None:
            continue

        agui_events, last_turn_boundary_seq = _process_replay_event(
            event,
            seq,
            mapper,
            turn_state,
            last_turn_boundary_seq,
        )
        for index, agui_event in enumerate(agui_events):
            if skipped < page_cursor.agui_skip:
                skipped += 1
                continue
            collected.append(agui_event)
            if len(collected) >= limit:
                remaining = len(agui_events) - index - 1
                if remaining > 0:
                    next_cursor = encode_pagination_cursor(
                        PaginationCursor(
                            raw_seq=seq,
                            agui_skip=index + 1,
                            checkpoint=last_turn_boundary_seq,
                        )
                    )
                    return PaginatedReplayResult(collected, next_cursor, has_more=True)
                if _has_more_after_raw(history_path, seq + 1, turn_state):
                    next_cursor = encode_pagination_cursor(
                        PaginationCursor(
                            raw_seq=seq + 1,
                            agui_skip=0,
                            checkpoint=last_turn_boundary_seq,
                        )
                    )
                    return PaginatedReplayResult(collected, next_cursor, has_more=True)
                return PaginatedReplayResult(collected, next_cursor=None, has_more=False)

        page_cursor = PaginationCursor(
            raw_seq=page_cursor.raw_seq,
            agui_skip=0,
            checkpoint=page_cursor.checkpoint,
            spawn_idx=page_cursor.spawn_idx,
            v=page_cursor.v,
        )

    terminal_events = turn_state.finish_replay()
    for index, terminal_event in enumerate(terminal_events):
        if skipped < page_cursor.agui_skip:
            skipped += 1
            continue
        collected.append(terminal_event)
        if len(collected) >= limit:
            remaining = len(terminal_events) - index - 1
            if remaining > 0:
                next_cursor = encode_pagination_cursor(
                    PaginationCursor(
                        raw_seq=next_raw_seq,
                        agui_skip=index + 1,
                        checkpoint=last_turn_boundary_seq,
                    )
                )
                return PaginatedReplayResult(collected, next_cursor, has_more=True)
            return PaginatedReplayResult(collected, next_cursor=None, has_more=False)

    return PaginatedReplayResult(collected, next_cursor=None, has_more=False)


def _raw_to_harness_event(raw: dict[str, Any]) -> HarnessEvent | None:
    """Convert one raw history event dictionary into a HarnessEvent."""

    base: Mapping[str, object] = raw
    nested = raw.get("event")
    if isinstance(nested, Mapping):
        base = cast("Mapping[str, object]", nested)

    event_type_obj = base.get("event_type")
    if not isinstance(event_type_obj, str):
        return None

    harness_id_obj = base.get("harness_id")
    if not isinstance(harness_id_obj, str):
        outer_harness = raw.get("harness_id")
        if not isinstance(outer_harness, str):
            return None
        harness_id_obj = outer_harness

    payload_obj = base.get("payload")
    payload: dict[str, object]
    if isinstance(payload_obj, Mapping):
        payload_map = cast("Mapping[object, object]", payload_obj)
        payload = {str(key): value for key, value in payload_map.items()}
    else:
        payload = {}

    raw_text_obj = base.get("raw_text")
    raw_text: str | None
    if isinstance(raw_text_obj, str):
        raw_text = raw_text_obj
    else:
        outer_raw_text = raw.get("raw_text")
        raw_text = outer_raw_text if isinstance(outer_raw_text, str) else None

    return HarnessEvent(
        event_type=event_type_obj,
        harness_id=harness_id_obj,
        payload=payload,
        raw_text=raw_text,
    )


def _process_replay_event(
    event: HarnessEvent,
    seq: int,
    mapper: Any,
    turn_state: AguiReplayTurnState,
    last_turn_boundary_seq: int,
) -> tuple[list[BaseEvent], int]:
    """Translate one raw event while updating replay lifecycle state."""

    if event.event_type == TURN_BOUNDARY_EVENT_TYPE:
        return turn_state.process_turn_boundary(), seq + 1

    events = turn_state.prepare_regular_event()
    for translated in mapper.translate(event):
        events.append(translated)
        turn_state.observe_translated_event(translated)
    return events, last_turn_boundary_seq


def _required_non_negative_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        raise ValueError("Invalid pagination cursor")
    return value


def _has_more_after_raw(
    history_path: Path,
    next_raw_seq: int,
    turn_state: AguiReplayTurnState,
) -> bool:
    if next(iter_history_from_seq(history_path, start_seq=next_raw_seq, limit=1), None) is not None:
        return True
    return turn_state.has_terminal_event()


__all__ = [
    "AguiReplayTurnState",
    "PaginatedReplayResult",
    "PaginationCursor",
    "decode_pagination_cursor",
    "encode_pagination_cursor",
    "replay_events_paginated",
    "replay_events_to_agui",
]
