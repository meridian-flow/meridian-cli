"""Core frozen domain dataclasses."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from pathlib import Path

    from meridian.lib.formatting import FormatContext
    from meridian.lib.types import (
        ArtifactKey,
        ModelId,
        SpawnId,
        SpanId,
        TraceId,
        WorkflowEventId,
        SpaceId,
    )

SpawnStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
SpaceState = Literal["active", "closed"]


def _empty_mapping() -> Mapping[str, Any]:
    return cast("Mapping[str, Any]", {})


@dataclass(frozen=True, slots=True)
class TokenUsage:
    """Token usage measured for a spawn."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_cost_usd: float | None = None


@dataclass(frozen=True, slots=True)
class SpawnCreateParams:
    """Input fields for creating a spawn record."""

    prompt: str
    model: ModelId
    space_id: SpaceId | None = None


@dataclass(frozen=True, slots=True)
class SpawnFilters:
    """Spawn list filter options."""

    space_id: SpaceId | None = None
    status: SpawnStatus | None = None


@dataclass(frozen=True, slots=True)
class SpawnEnrichment:
    """Post-spawn enrichment payload."""

    usage: TokenUsage = field(default_factory=TokenUsage)
    report_path: Path | None = None


@dataclass(frozen=True, slots=True)
class Spawn:
    """Spawn aggregate root."""

    spawn_id: SpawnId
    prompt: str
    model: ModelId
    status: SpawnStatus
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    space_id: SpaceId | None = None


@dataclass(frozen=True, slots=True)
class SpawnSummary:
    """Compact spawn view for list output."""

    spawn_id: SpawnId
    status: SpawnStatus
    model: ModelId
    space_id: SpaceId | None = None


@dataclass(frozen=True, slots=True)
class SpaceCreateParams:
    """Input fields for creating a space."""

    name: str | None = None


@dataclass(frozen=True, slots=True)
class SpaceFilters:
    """Space list filter options."""

    state: SpaceState | None = None


@dataclass(frozen=True, slots=True)
class Space:
    """Space aggregate root."""

    space_id: SpaceId
    state: SpaceState = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class SpaceSummary:
    """Compact space list entry."""

    space_id: SpaceId
    state: SpaceState
    finished_at: datetime | None = None
    name: str | None = None


@dataclass(frozen=True, slots=True)
class PinnedFile:
    """Pinned context file reference."""

    space_id: SpaceId
    file_path: str


@dataclass(frozen=True, slots=True)
class IndexReport:
    """Skill index operation summary."""

    indexed_count: int

    def format_text(self, ctx: FormatContext | None = None) -> str:
        return f"skills.reindex  ok  indexed={self.indexed_count}"


@dataclass(frozen=True, slots=True)
class SkillManifest:
    """Skill manifest metadata."""

    name: str
    description: str
    tags: tuple[str, ...] = ()
    path: str = ""


@dataclass(frozen=True, slots=True)
class SkillContent:
    """Loaded skill body."""

    name: str
    description: str
    tags: tuple[str, ...]
    content: str
    path: str

    def format_text(self, ctx: FormatContext | None = None) -> str:
        return f"{self.name}: {self.description}\n\n{self.content}"


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    """Event-sourced workflow event."""

    event_id: WorkflowEventId
    space_id: SpaceId
    event_type: str
    payload: Mapping[str, Any]
    spawn_id: SpawnId | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class Span:
    """OpenTelemetry-style trace span."""

    span_id: SpanId
    trace_id: TraceId
    name: str
    kind: str
    started_at: datetime
    parent_id: SpanId | None = None
    ended_at: datetime | None = None
    status: str = "ok"
    attributes: Mapping[str, Any] = field(default_factory=_empty_mapping)


@dataclass(frozen=True, slots=True)
class SpawnEdge:
    """Dependency edge between two spawns."""

    source_spawn_id: SpawnId
    target_run_id: SpawnId
    edge_type: str


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    """Metadata record for one spawn artifact."""

    spawn_id: SpawnId
    key: ArtifactKey
    path: Path
    size: int | None = None
