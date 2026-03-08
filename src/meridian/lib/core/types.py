"""Stable domain identifier newtypes."""

from typing import NewType

SpawnId = NewType("SpawnId", str)
HarnessId = NewType("HarnessId", str)
ModelId = NewType("ModelId", str)
ArtifactKey = NewType("ArtifactKey", str)
SchemaVersion = NewType("SchemaVersion", int)
