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


def merge_allowed_tools_flag(
    command: tuple[str, ...],
    additional_allowed_tools: Iterable[str],
) -> tuple[str, ...]:
    """Merge additional Claude allowed-tools values into one deduped flag."""

    additional = dedupe_nonempty(additional_allowed_tools)
    if not additional:
        return command

    existing_allowed_tools: list[str] = []
    merged_command: list[str] = []
    index = 0

    while index < len(command):
        arg = command[index]
        if arg == "--allowedTools":
            if index + 1 < len(command):
                existing_allowed_tools.extend(split_csv_entries(command[index + 1]))
                index += 2
                continue
            index += 1
            continue
        if arg.startswith("--allowedTools="):
            existing_allowed_tools.extend(split_csv_entries(arg.split("=", 1)[1]))
            index += 1
            continue
        merged_command.append(arg)
        index += 1

    combined_allowed_tools = dedupe_nonempty((*existing_allowed_tools, *additional))
    if not combined_allowed_tools:
        return tuple(merged_command)

    merged_command.extend(("--allowedTools", ",".join(combined_allowed_tools)))
    return tuple(merged_command)


__all__ = [
    "dedupe_nonempty",
    "merge_allowed_tools_flag",
    "split_csv_entries",
]
