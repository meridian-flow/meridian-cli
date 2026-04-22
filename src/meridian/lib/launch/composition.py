"""Semantic content models for launch composition.

This module provides harness-agnostic data structures for classified
launch content. The models follow the Semantic IR + Adapter Projection
pattern: composition code classifies content by meaning, then harness
adapters decide how to route content to CLI channels.

See spec S-1 for category definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ReferenceRouting:
    """Per-reference routing decision after harness projection.

    Captures how a single reference item was routed by the harness adapter.
    Serializes to the S-4c JSON schema.
    """

    path: str
    type: Literal["file", "directory"]
    routing: Literal["inline", "native-injection", "omitted"]
    native_flag: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """Serialize to S-4c schema dict."""
        return {
            "path": self.path,
            "type": self.type,
            "routing": self.routing,
            "native_flag": self.native_flag,
        }


@dataclass(frozen=True)
class ProjectionChannels:
    """Adapter-resolved channel decisions for semantic content categories."""

    system_instruction: Literal["append-system-prompt", "inline", "none"]
    user_task_prompt: Literal["user-turn", "inline"]
    task_context: Literal["user-turn", "inline", "native-injection"]

    def to_dict(self) -> dict[str, str]:
        return {
            "system_instruction": self.system_instruction,
            "user_task_prompt": self.user_task_prompt,
            "task_context": self.task_context,
        }


@dataclass(frozen=True)
class ComposedLaunchContent:
    """Semantic content blocks before harness channel projection.

    All fields are strings or tuples of strings.
    Harness adapters decide how to combine them.

    There are three semantic categories (see spec S-1):
      SYSTEM_INSTRUCTION — controls agent behavior
      USER_TASK_PROMPT   — user-supplied request text
      TASK_CONTEXT       — reference files, dirs, prior-run output

    Template variable expansions are not a category. Substitution
    happens in-place; expanded text inherits the category of the
    containing block.
    """

    # SYSTEM_INSTRUCTION blocks
    skill_injection: str
    """Composed skill content (from compose_skill_injections)."""

    agent_profile_body: str
    """Agent body (when not delivered via native agents)."""

    report_instruction: str
    """The 'write a report' directive."""

    inventory_prompt: str
    """Agent inventory — SYSTEM_INSTRUCTION, not startup context."""

    passthrough_system_fragments: tuple[str, ...]
    """Explicit --append-system-prompt passthrough args; appended last."""

    # USER_TASK_PROMPT
    user_task_prompt: str
    """Raw user request, template-substituted."""

    # TASK_CONTEXT blocks
    reference_blocks: tuple[str, ...]
    """Rendered reference file/dir content."""

    prior_output: str
    """Sanitized prior-run output."""


@dataclass(frozen=True)
class ProjectedContent:
    """Output of harness content projection.

    Represents the harness adapter's decision about how to route
    semantic content blocks to CLI channels.
    """

    system_prompt: str
    """Goes to --append-system-prompt channel (empty = omit)."""

    user_turn_content: str
    """Goes to user-turn / inline prompt channel."""

    reference_routing: tuple[ReferenceRouting, ...]
    """Per-reference routing decisions."""

    channels: ProjectionChannels
    """Per-category routing decisions for projection-manifest.json."""

    def channel_manifest(self) -> dict[str, str]:
        """Generate channel routing for projection-manifest.json (S-4d)."""
        return self.channels.to_dict()


__all__ = [
    "ComposedLaunchContent",
    "ProjectedContent",
    "ProjectionChannels",
    "ReferenceRouting",
]
