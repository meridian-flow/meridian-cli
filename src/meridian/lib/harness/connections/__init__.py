"""Bidirectional harness connection registry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from meridian.lib.harness.connections.claude_ws import ClaudeConnection
from meridian.lib.harness.connections.codex_ws import CodexConnection
from meridian.lib.harness.connections.opencode_http import OpenCodeConnection
from meridian.lib.harness.ids import HarnessId

if TYPE_CHECKING:
    from meridian.lib.harness.connections.base import HarnessConnection

_CONNECTION_REGISTRY: dict[HarnessId, type[HarnessConnection[Any]]] = {}


def register_connection(harness_id: HarnessId, cls: type[HarnessConnection[Any]]) -> None:
    """Register one bidirectional harness connection implementation."""

    _CONNECTION_REGISTRY[harness_id] = cls


def get_connection_class(harness_id: HarnessId) -> type[HarnessConnection[Any]]:
    """Return the registered connection class for one harness ID."""

    if harness_id not in _CONNECTION_REGISTRY:
        raise ValueError(f"No bidirectional connection registered for {harness_id}")
    return _CONNECTION_REGISTRY[harness_id]


register_connection(HarnessId.CODEX, CodexConnection)
register_connection(HarnessId.CLAUDE, ClaudeConnection)
register_connection(HarnessId.OPENCODE, OpenCodeConnection)


__all__ = ["get_connection_class", "register_connection"]
