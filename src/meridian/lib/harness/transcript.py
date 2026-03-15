"""Shared transcript parsing primitives used by ops-layer log extraction."""

from __future__ import annotations

from typing import NamedTuple, cast

_TRANSCRIPT_TEXT_KEYS: tuple[str, ...] = (
    "text",
    "content",
    "message",
    "output",
    "toolUseResult",
)


class TranscriptMessage(NamedTuple):
    role: str
    content: str


def text_from_value(value: object) -> str:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        payload = cast("list[object]", value)
        parts = [text_from_value(item) for item in payload]
        return "\n".join(part for part in parts if part).strip()

    if isinstance(value, dict):
        payload = cast("dict[str, object]", value)
        parts: list[str] = []
        for key in _TRANSCRIPT_TEXT_KEYS:
            if key not in payload:
                continue
            text = text_from_value(payload[key])
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    return ""


def _text_from_value(value: object) -> str:
    return text_from_value(value)


__all__ = ["TranscriptMessage", "_text_from_value", "text_from_value"]
