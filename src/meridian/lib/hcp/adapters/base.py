"""HCP adapter contract for harness-backed chat sessions."""

from __future__ import annotations

from typing import Protocol

from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.hcp.capabilities import HcpCapabilities
from meridian.lib.launch.launch_types import ResolvedLaunchSpec


class HcpAdapter(Protocol):
    """HCP adapter exposes harness chat capabilities and session ID policy."""

    @property
    def capabilities(self) -> HcpCapabilities: ...

    async def create_session(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> str:
        """Return expected harness_session_id pattern, empty for async extraction."""
        ...

    async def resume_session(
        self,
        harness_session_id: str,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> str:
        """Return harness_session_id for resume spec preparation."""
        ...


__all__ = ["HcpAdapter"]
