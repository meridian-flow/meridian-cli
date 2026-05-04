from __future__ import annotations

from typing import Any

from meridian.lib.state import spawn_store
from meridian.lib.state.spawn.events import reduce_events


class UnknownEvent:
    id = "p-skip"
    origin = "runner"
    status = "completed"


def test_reduce_events_skips_unknown_event_shapes() -> None:
    records = reduce_events([UnknownEvent()])  # type: ignore[list-item]

    assert records == {}


def test_reduce_events_tolerates_missing_ids_and_optional_start_fields() -> None:
    malformed_start = spawn_store.SpawnStartEvent.model_construct(id="p1")
    for field in ("chat_id", "parent_id", "model", "skills", "status", "started_at"):
        object.__delattr__(malformed_start, field)

    events: list[Any] = [object(), spawn_store.SpawnStartEvent(id=""), malformed_start]

    records = reduce_events(events)

    assert set(records) == {"p1"}
    record = records["p1"]
    assert record.id == "p1"
    assert record.status == "unknown"
    assert record.chat_id is None
    assert record.skills == ()
