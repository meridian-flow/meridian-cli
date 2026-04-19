"""Test doubles for deterministic behavior in unit and integration tests."""

from datetime import datetime, timezone

from meridian.lib.core.types import SpawnId


class FakeClock:
    def __init__(self, start: float = 0.0):
        self._now = start

    def monotonic(self) -> float:
        return self._now

    def time(self) -> float:
        return self._now

    def utc_now_iso(self) -> str:
        return datetime.fromtimestamp(self._now, tz=timezone.utc).isoformat()

    def advance(self, seconds: float) -> None:
        self._now += seconds


class FakeHeartbeat:
    """Test double for heartbeat touch operations."""

    def __init__(self) -> None:
        self.touches: list[float] = []
        self._clock: FakeClock | None = None

    def set_clock(self, clock: FakeClock) -> None:
        self._clock = clock

    def touch(self) -> None:
        timestamp = self._clock.time() if self._clock is not None else 0.0
        self.touches.append(timestamp)


class FakeSpawnRepository:
    """In-memory spawn repository test double."""

    def __init__(self) -> None:
        self._events: list[object] = []
        self._next_id_counter = 1

    def append_event(self, event: object) -> None:
        self._events.append(event)

    def read_events(self) -> list[object]:
        return list(self._events)

    def next_id(self) -> SpawnId:
        spawn_id = SpawnId(f"p{self._next_id_counter}")
        self._next_id_counter += 1
        return spawn_id
