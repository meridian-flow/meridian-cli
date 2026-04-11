"""Spawn extraction adapters for non-subprocess execution paths."""

from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.adapter import ArtifactStore, SpawnExtractor
from meridian.lib.harness.common import (
    extract_claude_report,
    extract_codex_report,
    extract_opencode_report,
    extract_session_id_from_artifacts,
    extract_usage_from_artifacts,
)
from meridian.lib.harness.connections.base import HarnessConnection
from meridian.lib.harness.ids import HarnessId
from meridian.lib.launch.launch_types import ResolvedLaunchSpec


class StreamingExtractor(SpawnExtractor):
    """Extractor backed by connection runtime state and persisted artifacts."""

    def __init__(
        self,
        connection: HarnessConnection[ResolvedLaunchSpec] | None,
        harness_id: HarnessId,
    ) -> None:
        self._connection = connection
        self._harness_id = harness_id

    def extract_session_id(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        connection = self._connection
        if connection is not None:
            session_id = connection.session_id
            if session_id:
                return session_id
        return extract_session_id_from_artifacts(artifacts, spawn_id)

    def extract_usage(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> TokenUsage:
        return extract_usage_from_artifacts(artifacts, spawn_id)

    def extract_report(self, artifacts: ArtifactStore, spawn_id: SpawnId) -> str | None:
        if self._harness_id == HarnessId.CODEX:
            return extract_codex_report(artifacts, spawn_id)
        if self._harness_id == HarnessId.CLAUDE:
            return extract_claude_report(artifacts, spawn_id)
        if self._harness_id == HarnessId.OPENCODE:
            return extract_opencode_report(artifacts, spawn_id)
        return None


__all__ = ["StreamingExtractor"]
