"""Shared text helpers used by launch preflight and projection code."""

from __future__ import annotations

from collections.abc import Iterable


def dedupe_nonempty(values: Iterable[str]) -> list[str]:
    """Strip and dedupe values while preserving first-seen order."""

    seen: set[str] = set()
    deduped: list[str] = []
    for raw_value in values:
        value = raw_value.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def split_csv_entries(value: str) -> list[str]:
    """Split one comma-delimited string into non-empty, stripped entries."""

    return [entry.strip() for entry in value.split(",") if entry.strip()]


__all__ = [
    "dedupe_nonempty",
    "split_csv_entries",
]
