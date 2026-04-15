"""Types used for streaming control message injection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict


class UserMessageControl(TypedDict):
    """Inject one user message into an active connection."""

    type: Literal["user_message"]
    text: str


class InterruptControl(TypedDict):
    """Request a harness interrupt."""

    type: Literal["interrupt"]


ControlMessage = UserMessageControl | InterruptControl


@dataclass(frozen=True)
class InjectResult:
    """Outcome of attempting to inject one control message."""

    success: bool
    inbound_seq: int | None = None
    noop: bool = False
    error: str | None = None


__all__ = [
    "ControlMessage",
    "InjectResult",
    "InterruptControl",
    "UserMessageControl",
]
