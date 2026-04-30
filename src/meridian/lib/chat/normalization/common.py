"""Shared projection helpers for chat event normalizers."""

from __future__ import annotations


def canonical_item_type(raw_type: str | None, name: str | None = None) -> str:
    """Map raw harness item/tool types to canonical chat item taxonomy."""

    value = f"{raw_type or ''} {name or ''}".lower()
    if any(token in value for token in ("exec", "shell", "command", "bash")):
        return "command_execution"
    if any(token in value for token in ("file", "patch", "edit", "write")):
        return "file_change"
    return raw_type or name or "tool_use"


__all__ = ["canonical_item_type"]
