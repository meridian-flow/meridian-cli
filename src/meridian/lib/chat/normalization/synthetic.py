"""Chat-side adapter for synthetic meridian/* event types."""

from __future__ import annotations

from meridian.lib.streaming.drain_policy import TURN_BOUNDARY_EVENT_TYPE


def is_turn_boundary_event(event_type: str) -> bool:
    """Return whether a raw event type is the synthetic turn boundary."""

    return event_type == TURN_BOUNDARY_EVENT_TYPE


__all__ = ["is_turn_boundary_event"]
