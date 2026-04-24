"""Meridian-specific helpers for AG-UI extension events."""

from __future__ import annotations

from ag_ui.core import CustomEvent, RunErrorEvent
from meridian.lib.harness.connections.base import ConnectionCapabilities


def make_capabilities_event(caps: ConnectionCapabilities) -> CustomEvent:
    """Wrap connection capabilities in one AG-UI CUSTOM event payload."""

    return CustomEvent(
        name="capabilities",
        value={
            "midTurnInjection": caps.mid_turn_injection,
            "supportsSteer": caps.supports_steer,
            "supportsCancel": caps.supports_cancel,
            "runtimeModelSwitch": caps.runtime_model_switch,
            "structuredReasoning": caps.structured_reasoning,
        },
    )


def make_run_error_event(message: str, is_cancelled: bool = False) -> RunErrorEvent:
    """Create one RUN_ERROR event with Meridian's cancellation extension field."""

    return RunErrorEvent.model_validate(
        {
            "message": message,
            "isCancelled": is_cancelled,
        }
    )


__all__ = ["make_capabilities_event", "make_run_error_event"]
