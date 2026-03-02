"""Model-family to harness routing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from meridian.lib.types import HarnessId

SpawnMode = Literal["harness", "direct"]


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """Routing result for a model selection request."""

    harness_id: HarnessId
    warning: str | None = None


def route_model(model: str, mode: SpawnMode = "harness") -> RoutingDecision:
    """Route a model ID to the corresponding harness family.

    Matches current bash behavior with Codex fallback for unknown families.
    """

    normalized = model.strip()
    if mode == "direct":
        return RoutingDecision(harness_id=HarnessId("direct"))

    if normalized.startswith(("claude-", "opus", "sonnet", "haiku")):
        return RoutingDecision(harness_id=HarnessId("claude"))
    if normalized.startswith(("gpt-", "o1", "o3", "o4", "codex")):
        return RoutingDecision(harness_id=HarnessId("codex"))
    if normalized.startswith(("opencode-", "gemini-", "gemini")) or "/" in normalized:
        return RoutingDecision(harness_id=HarnessId("opencode"))

    warning = f"Unknown model family '{model}'. Using harness 'codex'."
    return RoutingDecision(harness_id=HarnessId("codex"), warning=warning)
