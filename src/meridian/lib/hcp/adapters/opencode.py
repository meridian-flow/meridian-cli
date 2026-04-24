"""OpenCode HCP adapter."""

from __future__ import annotations

from typing import Any

from meridian.lib.harness.connections import get_connection_class
from meridian.lib.harness.connections.base import ConnectionConfig, HarnessConnection
from meridian.lib.hcp.capabilities import OPENCODE_CAPABILITIES, HcpCapabilities
from meridian.lib.launch.launch_types import ResolvedLaunchSpec


class OpenCodeHcpAdapter:
    @property
    def capabilities(self) -> HcpCapabilities:
        return OPENCODE_CAPABILITIES

    async def create_session(
        self,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> str:
        connection = await _start_connection(config, spec)
        return connection.session_id or ""

    async def resume_session(
        self,
        harness_session_id: str,
        config: ConnectionConfig,
        spec: ResolvedLaunchSpec,
    ) -> str:
        spec_with_resume = spec.model_copy(update={"continue_session_id": harness_session_id})
        connection = await _start_connection(config, spec_with_resume)
        return connection.session_id or harness_session_id


async def _start_connection(
    config: ConnectionConfig,
    spec: ResolvedLaunchSpec,
) -> HarnessConnection[Any]:
    connection_class = get_connection_class(config.harness_id)
    connection = connection_class()
    await connection.start(config, spec)
    return connection


__all__ = ["OpenCodeHcpAdapter"]
