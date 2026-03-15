"""Stable domain identifier types."""

from enum import StrEnum
from typing import NewType


class HarnessId(StrEnum):
    """Known harness identifiers."""

    CLAUDE = "claude"
    CODEX = "codex"
    OPENCODE = "opencode"
    DIRECT = "direct"


SpawnId = NewType("SpawnId", str)
ModelId = NewType("ModelId", str)
ArtifactKey = NewType("ArtifactKey", str)
SchemaVersion = NewType("SchemaVersion", int)
