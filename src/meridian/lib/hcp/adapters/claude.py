"""Claude HCP adapter."""

from __future__ import annotations

from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.hcp.capabilities import CLAUDE_CAPABILITIES, HcpCapabilities
from meridian.lib.launch.launch_types import ResolvedLaunchSpec


class ClaudeHcpAdapter:
    """Claude exposes its session ID asynchronously through stream events."""

    @property
    def capabilities(self) -> HcpCapabilities:
        return CLAUDE_CAPABILITIES

    async def create_session(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> str:
        _ = config, spec
        return ""

    async def resume_session(
        self,
        harness_session_id: str,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> str:
        _ = config, spec.model_copy(update={"continue_session_id": harness_session_id})
        return harness_session_id


__all__ = ["ClaudeHcpAdapter"]
