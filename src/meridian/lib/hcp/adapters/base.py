"""HCP adapter contract for harness-backed chat sessions."""

from __future__ import annotations

from typing import Protocol

from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.hcp.capabilities import HcpCapabilities
from meridian.lib.launch.launch_types import ResolvedLaunchSpec


class HcpAdapter(Protocol):
    """HCP adapter wraps a harness connection."""

    @property
    def capabilities(self) -> HcpCapabilities: ...

    async def create_session(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> str:
        """Start harness and return harness_session_id."""
        ...

    async def resume_session(
        self,
        harness_session_id: str,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> str:
        """Resume an existing harness session."""
        ...


__all__ = ["HcpAdapter"]
