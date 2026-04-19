"""Pure spawn event reduction logic."""

from meridian.lib.state.spawn_store import SpawnEvent, SpawnRecord


def reduce_events(events: list[SpawnEvent]) -> dict[str, SpawnRecord]:
    """Reduce spawn events into the latest spawn records."""

    _ = events
    return {}


__all__ = ["reduce_events"]
