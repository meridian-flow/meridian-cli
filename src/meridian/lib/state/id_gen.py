"""File-backed ID generation for spaces, spawns, and sessions."""

from __future__ import annotations

import json
from pathlib import Path

from meridian.lib.types import SpawnId, SpaceId


def _count_start_events(path: Path) -> int:
    if not path.exists():
        return 0

    count = 0
    with path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            # Self-heal truncated trailing line from interrupted append.
            if index == len(lines) - 1:
                continue
            continue
        if isinstance(payload, dict) and payload.get("event") == "start":
            count += 1
    return count


def next_space_id(repo_root: Path) -> SpaceId:
    """Return the next monotonic space ID (`s1`, `s2`, ...)."""

    spaces_dir = repo_root / ".meridian" / ".spaces"
    if not spaces_dir.exists():
        return SpaceId("s1")

    max_suffix = 0
    for child in spaces_dir.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if not name.startswith("s"):
            continue
        suffix = name[1:]
        if suffix.isdigit():
            max_suffix = max(max_suffix, int(suffix))
    return SpaceId(f"s{max_suffix + 1}")


def next_spawn_id(space_dir: Path) -> SpawnId:
    """Return the next run ID (`r1`, `r2`, ...) for a space."""

    starts = _count_start_events(space_dir / "spawns.jsonl")
    return SpawnId(f"r{starts + 1}")


def next_chat_id(space_dir: Path) -> str:
    """Return the next session/chat ID (`c1`, `c2`, ...) for a space."""

    starts = _count_start_events(space_dir / "sessions.jsonl")
    return f"c{starts + 1}"
