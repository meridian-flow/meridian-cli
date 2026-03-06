"""Shared operation helpers."""

from __future__ import annotations


def minutes_to_seconds(timeout_minutes: float | None) -> float | None:
    if timeout_minutes is None:
        return None
    return timeout_minutes * 60.0


def merge_warnings(*warnings: str | None) -> str | None:
    """Join non-empty warning strings with consistent separators."""

    parts = [item.strip() for item in warnings if item and item.strip()]
    if not parts:
        return None
    return "; ".join(parts)
