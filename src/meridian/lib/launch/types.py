"""Shared types for the launch pipeline."""

from pydantic import BaseModel, ConfigDict, Field

_CONTINUATION_GUIDANCE = (
    "You are resuming an existing Meridian session. Continue from the current state, "
    "preserve prior decisions unless evidence has changed, and avoid duplicating "
    "already-completed work."
)


class LaunchRequest(BaseModel):
    """Inputs for launching one primary agent session."""

    model_config = ConfigDict(frozen=True)

    model: str = ""
    harness: str | None = None
    agent: str | None = None
    work_id: str | None = None
    fresh: bool = False
    autocompact: int | None = None
    passthrough_args: tuple[str, ...] = ()
    pinned_context: str = ""
    dry_run: bool = False
    approval: str = "confirm"
    continue_harness_session_id: str | None = None
    continue_chat_id: str | None = None


class LaunchResult(BaseModel):
    """Result metadata from a completed primary launch."""

    model_config = ConfigDict(frozen=True)

    command: tuple[str, ...]
    exit_code: int
    continue_ref: str | None = None


class PrimarySessionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    harness: str
    model: str
    agent: str
    agent_path: str
    agent_source: str | None = None
    skills: tuple[str, ...]
    skill_paths: tuple[str, ...]
    skill_sources: dict[str, str] = Field(default_factory=dict)
    bootstrap_required_items: tuple[str, ...] = ()
    bootstrap_missing_items: tuple[str, ...] = ()


def build_primary_prompt(request: LaunchRequest) -> str:
    """Build launch prompt for primary sessions."""

    sections: list[str] = ["# Meridian Session"]

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


__all__ = [
    "LaunchRequest",
    "LaunchResult",
    "PrimarySessionMetadata",
    "build_primary_prompt",
]
