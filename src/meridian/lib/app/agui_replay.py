"""AG-UI event replay from raw harness event sequences."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any, cast

from ag_ui.core import BaseEvent
from meridian.lib.app.agui_mapping import get_agui_mapper
from meridian.lib.core.types import HarnessId
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.streaming.drain_policy import TURN_BOUNDARY_EVENT_TYPE


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


__all__ = ["AguiReplayTurnState", "replay_events_to_agui"]
