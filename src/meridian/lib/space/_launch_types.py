"""Shared types for the primary launch pipeline.

Separated from launch.py to allow _launch_command.py and _launch_process.py
to import these without creating circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from meridian.lib.types import SpaceId

_CONTINUATION_GUIDANCE = (
    "You are resuming an existing space. Continue from the current state, "
    "preserve prior decisions unless evidence has changed, and avoid duplicating "
    "already-completed work."
)


@dataclass(frozen=True, slots=True)
class SpaceLaunchRequest:
    """Inputs for launching one primary agent session."""

    space_id: SpaceId
    model: str = ""
    harness: str | None = None
    agent: str | None = None
    fresh: bool = False
    autocompact: int | None = None
    passthrough_args: tuple[str, ...] = ()
    pinned_context: str = ""
    dry_run: bool = False
    permission_tier: str | None = None
    approval: str = "confirm"
    continue_harness_session_id: str | None = None


@dataclass(frozen=True, slots=True)
class SpaceLaunchResult:
    """Result metadata from a completed primary launch."""

    command: tuple[str, ...]
    exit_code: int
    lock_path: Path
    continue_ref: str | None = None


@dataclass(frozen=True, slots=True)
class _PrimarySessionMetadata:
    harness: str
    model: str
    agent: str
    agent_path: str
    skills: tuple[str, ...]
    skill_paths: tuple[str, ...]


def build_primary_prompt(request: SpaceLaunchRequest) -> str:
    """Build launch prompt for space start/resume sessions."""

    sections: list[str] = [
        "# Meridian Space Session",
        f"Space: {request.space_id}",
    ]

    if request.fresh:
        sections.extend(
            [
                "",
                "# Session Mode",
                "",
                "Start a fresh primary conversation for this space.",
            ]
        )
    else:
        sections.extend(["", "# Continuation Guidance", "", _CONTINUATION_GUIDANCE])

    if request.pinned_context.strip():
        sections.extend(["", "# Re-Injected Pinned Context", "", request.pinned_context.strip()])

    return "\n".join(sections).strip()
