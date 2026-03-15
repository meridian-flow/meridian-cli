"""Shared artifact read helpers for launch extraction."""

from meridian.lib.core.types import ArtifactKey, SpawnId
from meridian.lib.state.artifact_store import ArtifactStore


def read_artifact_text(artifacts: ArtifactStore, spawn_id: SpawnId, name: str) -> str:
    key = ArtifactKey(f"{spawn_id}/{name}")
    if not artifacts.exists(key):
        return ""
    return artifacts.get(key).decode("utf-8", errors="ignore")
