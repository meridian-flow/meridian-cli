"""Stable domain identifier newtypes."""

from typing import NewType

SpaceId = NewType("SpaceId", str)
SpawnId = NewType("SpawnId", str)
HarnessId = NewType("HarnessId", str)
ModelId = NewType("ModelId", str)
WorkflowEventId = NewType("WorkflowEventId", int)
SpanId = NewType("SpanId", str)
TraceId = NewType("TraceId", str)
ArtifactKey = NewType("ArtifactKey", str)
SchemaVersion = NewType("SchemaVersion", int)
