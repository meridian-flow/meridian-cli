"""Stable domain identifier types."""

from typing import NewType

from meridian.lib.harness.ids import HarnessId

SpawnId = NewType("SpawnId", str)
ModelId = NewType("ModelId", str)
ArtifactKey = NewType("ArtifactKey", str)
SchemaVersion = NewType("SchemaVersion", int)

__all__ = ["ArtifactKey", "HarnessId", "ModelId", "SchemaVersion", "SpawnId"]
