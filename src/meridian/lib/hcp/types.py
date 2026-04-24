"""HCP lifecycle types."""

from dataclasses import dataclass, field
from enum import StrEnum


class ChatState(StrEnum):
    ACTIVE = "active"
    DRAINING = "draining"
    IDLE = "idle"
    CLOSED = "closed"


class TurnState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    AWAITING_PERMISSION = "awaiting_permission"
    AWAITING_INPUT = "awaiting_input"
    COMPLETED = "completed"


@dataclass
class LifecycleEvent:
    event: str
    ts: str
    data: dict[str, object] = field(default_factory=lambda: {})


__all__ = ["ChatState", "LifecycleEvent", "TurnState"]
