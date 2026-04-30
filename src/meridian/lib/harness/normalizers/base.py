"""Harness event normalizer protocol."""

from __future__ import annotations

from typing import Protocol

from meridian.lib.chat.protocol import ChatEvent
from meridian.lib.harness.connections.base import HarnessEvent


class EventNormalizer(Protocol):
    """Stateful translator from one raw harness stream to ChatEvents."""

    def normalize(self, event: HarnessEvent) -> list[ChatEvent]:
        """Translate one raw harness event into zero or more chat events."""
        ...

    def reset(self) -> None:
        """Clear state across backing execution boundaries."""
        ...


__all__ = ["EventNormalizer"]
