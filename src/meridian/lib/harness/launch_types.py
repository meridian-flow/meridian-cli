"""Neutral launch types shared between harness adapters and launch orchestration.

Placed in ``meridian.lib.harness`` (not ``meridian.lib.space``) to avoid
import-cycle pressure from ``space/__init__.py`` which eagerly imports
``space.launch``.
"""

from pydantic import BaseModel, ConfigDict


class SessionSeed(BaseModel):
    """Adapter's session decisions, resolved early (before process starts)."""

    model_config = ConfigDict(frozen=True)

    session_id: str = ""
    session_args: tuple[str, ...] = ()


class PromptPolicy(BaseModel):
    """Adapter's prompt decisions, resolved during command assembly."""

    model_config = ConfigDict(frozen=True)

    prompt: str = ""
    skill_injection: str | None = None
