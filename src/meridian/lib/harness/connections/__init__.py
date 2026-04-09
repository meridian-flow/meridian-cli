"""Bidirectional harness connection registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from meridian.lib.core.types import HarnessId
from meridian.lib.harness.connections.claude_ws import ClaudeConnection
from meridian.lib.harness.connections.codex_ws import CodexConnection
from meridian.lib.harness.connections.opencode_http import OpenCodeConnection

if TYPE_CHECKING:
    from meridian.lib.harness.connections.base import HarnessConnection

_CONNECTION_REGISTRY: dict[HarnessId, type[HarnessConnection]] = {}


def register_connection(harness_id: HarnessId, cls: type[HarnessConnection]) -> None:
    """Register one bidirectional harness connection implementation."""

    _CONNECTION_REGISTRY[harness_id] = cls


def get_connection_class(harness_id: HarnessId) -> type[HarnessConnection]:
    """Return the registered connection class for one harness ID."""

    if harness_id not in _CONNECTION_REGISTRY:
        raise ValueError(f"No bidirectional connection registered for {harness_id}")
    return _CONNECTION_REGISTRY[harness_id]


register_connection(HarnessId.CODEX, CodexConnection)
register_connection(HarnessId.CLAUDE, ClaudeConnection)
register_connection(HarnessId.OPENCODE, OpenCodeConnection)


__all__ = ["get_connection_class", "register_connection"]
