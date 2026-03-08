"""Core frozen domain models."""


from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from meridian.lib.core.util import FormatContext
from meridian.lib.core.types import (
    ArtifactKey,
    ModelId,
    SpaceId,
    SpawnId,
)

SpawnStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class TokenUsage(BaseModel):
    """Token usage measured for a spawn."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_cost_usd: float | None = None


class SpawnCreateParams(BaseModel):
    """Input fields for creating a spawn record."""

    model_config = ConfigDict(frozen=True)

    prompt: str
    model: ModelId
    space_id: SpaceId | None = None


class SpawnFilters(BaseModel):
    """Spawn list filter options."""

    model_config = ConfigDict(frozen=True)

    space_id: SpaceId | None = None
    status: SpawnStatus | None = None


class SpawnEnrichment(BaseModel):
    """Post-spawn enrichment payload."""

    model_config = ConfigDict(frozen=True)

    usage: TokenUsage = Field(default_factory=TokenUsage)
    report_path: Path | None = None


class Spawn(BaseModel):
    """Spawn aggregate root."""

    model_config = ConfigDict(frozen=True)

    spawn_id: SpawnId
    prompt: str
    model: ModelId
    status: SpawnStatus
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    space_id: SpaceId | None = None


class SpawnSummary(BaseModel):
    """Compact spawn view for list output."""

    model_config = ConfigDict(frozen=True)

    spawn_id: SpawnId
    status: SpawnStatus
    model: ModelId
    space_id: SpaceId | None = None


class SpaceCreateParams(BaseModel):
    """Input fields for creating a space."""

    model_config = ConfigDict(frozen=True)

    name: str | None = None


class SpaceFilters(BaseModel):
    """Space list filter options."""

    model_config = ConfigDict(frozen=True)


class Space(BaseModel):
    """Space aggregate root."""

    model_config = ConfigDict(frozen=True)

    space_id: SpaceId
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    name: str | None = None


class SpaceSummary(BaseModel):
    """Compact space list entry."""

    model_config = ConfigDict(frozen=True)

    space_id: SpaceId
    name: str | None = None


class PinnedFile(BaseModel):
    """Pinned context file reference."""

    model_config = ConfigDict(frozen=True)

    space_id: SpaceId
    file_path: str


class IndexReport(BaseModel):
    """Skill index operation summary."""

    model_config = ConfigDict(frozen=True)

    indexed_count: int

    def format_text(self, ctx: FormatContext | None = None) -> str:
        return f"skills.reindex  ok  indexed={self.indexed_count}"


class SkillManifest(BaseModel):
    """Skill manifest metadata."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    tags: tuple[str, ...] = ()
    path: str = ""


class SkillContent(BaseModel):
    """Loaded skill body."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    tags: tuple[str, ...]
    content: str
    path: str

    def format_text(self, ctx: FormatContext | None = None) -> str:
        return f"{self.name}: {self.description}\n\n{self.content}"


class ArtifactRecord(BaseModel):
    """Metadata record for one spawn artifact."""

    model_config = ConfigDict(frozen=True)

    spawn_id: SpawnId
    key: ArtifactKey
    path: Path
    size: int | None = None
