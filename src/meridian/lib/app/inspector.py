"""Inspector: deterministic artifact extraction for thread events, tool calls, and token usage.

Event IDs are encoded as ``{spawn_id}:{line_index}`` where ``line_index`` is the
0-based index of the raw JSON line in ``output.jsonl``.  Because the artifact is
file-authoritative and append-only, these IDs survive restarts.

Tool-call IDs share the same scheme: the line that carries the tool_use payload
gets its position used as the call_id.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from meridian.lib.core.domain import TokenUsage
from meridian.lib.core.types import SpawnId
from meridian.lib.harness.common import extract_usage_from_artifacts, unwrap_event_payload
from meridian.lib.launch.constants import OUTPUT_FILENAME
from meridian.lib.state.artifact_store import LocalStore

_SEP = ":"


# ---------------------------------------------------------------------------
# Event-ID helpers
# ---------------------------------------------------------------------------


def make_event_id(spawn_id: str, line_index: int) -> str:
    """Encode a stable event ID from spawn ID and 0-based line index."""
    return f"{spawn_id}{_SEP}{line_index}"


def parse_event_id(event_id: str) -> tuple[str, int] | None:
    """Parse ``{spawn_id}:{line_index}``.  Returns *None* when malformed."""
    sep_pos = event_id.rfind(_SEP)
    if sep_pos < 1:
        return None
    raw_index = event_id[sep_pos + 1 :]
    try:
        line_index = int(raw_index)
    except ValueError:
        return None
    if line_index < 0:
        return None
    return event_id[:sep_pos], line_index


# ---------------------------------------------------------------------------
# Raw artifact reading
# ---------------------------------------------------------------------------


def read_raw_output_lines(artifact_root: Path, spawn_id: str) -> list[dict[str, object]]:
    """Read all non-empty parsed JSON lines from ``output.jsonl`` for *spawn_id*.

    Lines that fail JSON parsing are silently skipped — they may be partial
    writes from a still-running process.
    """
    output_path = artifact_root / spawn_id / OUTPUT_FILENAME
    if not output_path.is_file():
        return []
    lines: list[dict[str, object]] = []
    with output_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                lines.append(cast("dict[str, object]", obj))
    return lines


# ---------------------------------------------------------------------------
# Event lookup
# ---------------------------------------------------------------------------


def get_event_by_line(
    artifact_root: Path,
    spawn_id: str,
    line_index: int,
) -> dict[str, object] | None:
    """Return the unwrapped event payload at *line_index*, or *None* if out of range."""
    lines = read_raw_output_lines(artifact_root, spawn_id)
    if line_index < 0 or line_index >= len(lines):
        return None
    payload = unwrap_event_payload(lines[line_index])
    return {
        "event_id": make_event_id(spawn_id, line_index),
        "spawn_id": spawn_id,
        "line_index": line_index,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Tool-call extraction
# ---------------------------------------------------------------------------


def _is_tool_use_line(payload: dict[str, object]) -> bool:
    """Return *True* if *payload* carries a tool_use / function_call."""
    event_type = str(payload.get("type", payload.get("event", ""))).strip().lower()
    if "tool" in event_type or "function_call" in event_type:
        return True
    # Claude events wrap tool_use in assistant message content blocks.
    if event_type == "assistant":
        message = payload.get("message")
        if isinstance(message, dict):
            content = cast("dict[str, object]", message).get("content")
            if isinstance(content, list):
                for block in cast("list[object]", content):
                    if isinstance(block, dict):
                        block_type = str(
                            cast("dict[str, object]", block).get("type", "")
                        ).lower()
                        if block_type == "tool_use":
                            return True
    return False


def get_tool_calls(
    artifact_root: Path,
    spawn_id: str,
) -> list[dict[str, object]]:
    """Return all tool-call records for *spawn_id* in source order."""
    lines = read_raw_output_lines(artifact_root, spawn_id)
    results: list[dict[str, object]] = []
    for idx, raw in enumerate(lines):
        payload = unwrap_event_payload(raw)
        if not _is_tool_use_line(payload):
            continue
        results.append({
            "call_id": make_event_id(spawn_id, idx),
            "spawn_id": spawn_id,
            "line_index": idx,
            "payload": payload,
        })
    return results


def get_tool_call_by_id(
    artifact_root: Path,
    call_id: str,
) -> dict[str, object] | None:
    """Return one tool-call record by *call_id*, or *None* if not found."""
    parsed = parse_event_id(call_id)
    if parsed is None:
        return None
    spawn_id, line_index = parsed
    lines = read_raw_output_lines(artifact_root, spawn_id)
    if line_index < 0 or line_index >= len(lines):
        return None
    payload = unwrap_event_payload(lines[line_index])
    if not _is_tool_use_line(payload):
        return None
    return {
        "call_id": call_id,
        "spawn_id": spawn_id,
        "line_index": line_index,
        "payload": payload,
    }


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------


def get_token_usage(artifact_root: Path, spawn_id: str) -> TokenUsage:
    """Return token usage for *spawn_id* using shared extraction helpers."""
    store = LocalStore(root_dir=artifact_root)
    return extract_usage_from_artifacts(store, SpawnId(spawn_id))


__all__ = [
    "get_event_by_line",
    "get_token_usage",
    "get_tool_call_by_id",
    "get_tool_calls",
    "make_event_id",
    "parse_event_id",
    "read_raw_output_lines",
]
