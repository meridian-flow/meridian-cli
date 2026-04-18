"""Spawn log operation: extract assistant messages from output.jsonl."""

from __future__ import annotations

import json
from typing import cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.types import ArtifactKey
from meridian.lib.core.util import FormatContext
from meridian.lib.harness.transcript import text_from_value
from meridian.lib.ops.runtime import (
    async_from_sync,
    resolve_runtime_root_and_config,
    resolve_state_root,
)
from meridian.lib.state.artifact_store import LocalStore

from .query import read_spawn_row, resolve_spawn_reference


class SpawnLogInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    last_n: int = 3
    offset: int = 0
    repo_root: str | None = None


class SpawnLogMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    content: str


class SpawnLogOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spawn_id: str
    total_messages: int
    showing: str
    messages: tuple[SpawnLogMessage, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        message_label = "message" if self.total_messages == 1 else "messages"
        lines = [
            f"Spawn {self.spawn_id} — {self.total_messages} assistant "
            f"{message_label} (showing {self.showing})"
        ]
        for message in self.messages:
            lines.append("")
            lines.append(f"--- {message.index} ---")
            lines.append(message.content)
        return "\n".join(lines)


def _append_dedup(messages: list[str], candidate: str) -> None:
    normalized = candidate.strip()
    if not normalized:
        return
    if messages and messages[-1] == normalized:
        return
    messages.append(normalized)


def _extract_claude_text_blocks(content: object) -> list[str]:
    found: list[str] = []

    if isinstance(content, list):
        for item in cast("list[object]", content):
            if not isinstance(item, dict):
                text = text_from_value(item)
                if text:
                    found.append(text)
                continue

            block = cast("dict[str, object]", item)
            if str(block.get("type", "")).strip().lower() != "text":
                continue
            text = text_from_value(block.get("text"))
            if text:
                found.append(text)
        return found

    text = text_from_value(content)
    if text:
        found.append(text)
    return found


def _extract_claude_assistant_messages(payload: dict[str, object]) -> list[str]:
    event_type = str(payload.get("type", "")).strip().lower()
    if event_type != "assistant":
        return []

    found: list[str] = []
    message = payload.get("message")

    if isinstance(message, str):
        text = text_from_value(message)
        if text:
            found.append(text)
        return found

    if isinstance(message, dict):
        message_payload = cast("dict[str, object]", message)
        found.extend(_extract_claude_text_blocks(message_payload.get("content")))
        if not found:
            text = text_from_value(message_payload.get("text"))
            if text:
                found.append(text)

    if not found:
        found.extend(_extract_claude_text_blocks(payload.get("content")))

    return found


def _extract_codex_assistant_messages(payload: dict[str, object]) -> list[str]:
    event_type = (
        str(payload.get("event_type", payload.get("event", payload.get("type", ""))))
        .strip()
        .lower()
        .replace("/", ".")
    )
    if event_type != "item.completed":
        return []

    item = payload.get("item")
    if not isinstance(item, dict):
        return []

    item_payload = cast("dict[str, object]", item)
    item_type = str(item_payload.get("type", "")).strip().lower().replace("_", "")
    if item_type != "agentmessage":
        return []

    text = text_from_value(item_payload.get("text"))
    if not text:
        return []
    return [text]


def _assistant_texts_generic(payload: object) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        obj = cast("dict[str, object]", payload)
        role = str(obj.get("role", "")).lower()
        event_type = str(obj.get("type", obj.get("event", ""))).lower()
        category = str(obj.get("category", "")).lower()

        if role == "assistant" or "assistant" in event_type or category == "assistant":
            text = text_from_value(obj)
            if text:
                found.append(text)

        for nested in obj.values():
            found.extend(_assistant_texts_generic(nested))
        return found

    if isinstance(payload, list):
        for item in cast("list[object]", payload):
            found.extend(_assistant_texts_generic(item))
    return found


def _extract_from_payload(payload: dict[str, object]) -> list[str]:
    event_type = (
        str(payload.get("event_type", payload.get("event", payload.get("type", ""))))
        .strip()
        .lower()
        .replace("/", ".")
    )
    if "event_type" in payload and "payload" in payload:
        nested_payload = payload.get("payload")
        if isinstance(nested_payload, dict):
            merged_payload = dict(cast("dict[str, object]", nested_payload))
            merged_payload.setdefault("event_type", payload["event_type"])
            return _extract_from_payload(merged_payload)

    if event_type == "progress":
        data = payload.get("data")
        if isinstance(data, dict):
            nested_message = cast("dict[str, object]", data).get("message")
            if isinstance(nested_message, dict):
                return _extract_from_payload(cast("dict[str, object]", nested_message))
        return []
    if event_type == "rate_limit_event":
        return []

    extracted: list[str] = []
    extracted.extend(_extract_codex_assistant_messages(payload))
    extracted.extend(_extract_claude_assistant_messages(payload))
    if extracted:
        return extracted

    # Codex item.completed events without extracted assistant text should
    # not recurse generically (prevents command/tool payload noise).
    if event_type == "item.completed":
        return []

    return _assistant_texts_generic(payload)


def _extract_assistant_messages(output_lines: str) -> list[str]:
    messages: list[str] = []
    for line in output_lines.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload_obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload_obj, dict):
            continue

        payload = cast("dict[str, object]", payload_obj)
        extracted = _extract_from_payload(payload)
        for text in extracted:
            _append_dedup(messages, text)

    return messages


def _paginate(total_messages: int, *, last_n: int, offset: int) -> tuple[int, int]:
    if offset >= total_messages:
        return (0, 0)
    end = total_messages - offset
    if last_n <= 0:
        return (end, end)
    start = max(end - last_n, 0)
    return (start, end)


def _output_window(messages: tuple[SpawnLogMessage, ...]) -> str:
    if not messages:
        return "0-0"
    return f"{messages[0].index}-{messages[-1].index}"


def spawn_log_sync(
    payload: SpawnLogInput,
    ctx: RuntimeContext | None = None,
) -> SpawnLogOutput:
    _ = ctx
    if payload.last_n < 0:
        raise ValueError("last_n must be >= 0")
    if payload.offset < 0:
        raise ValueError("offset must be >= 0")

    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    spawn_id = resolve_spawn_reference(repo_root, payload.spawn_id)
    row = read_spawn_row(repo_root, spawn_id)
    if row is None:
        raise ValueError(f"Spawn '{spawn_id}' not found")

    state_root = resolve_state_root(repo_root)
    artifacts = LocalStore(root_dir=state_root / "artifacts")
    output_key = ArtifactKey(f"{spawn_id}/output.jsonl")
    if artifacts.exists(output_key):
        output_text = artifacts.get(output_key).decode("utf-8", errors="ignore")
    else:
        live_output_path = state_root / "spawns" / spawn_id / "output.jsonl"
        if not live_output_path.is_file():
            raise ValueError(f"Spawn '{spawn_id}' has no output.jsonl artifact")
        output_text = live_output_path.read_text(encoding="utf-8", errors="ignore")
    assistant_messages = _extract_assistant_messages(output_text)

    start, end = _paginate(
        len(assistant_messages),
        last_n=payload.last_n,
        offset=payload.offset,
    )
    selected = assistant_messages[start:end]
    messages = tuple(
        SpawnLogMessage(index=start + idx + 1, content=text) for idx, text in enumerate(selected)
    )
    return SpawnLogOutput(
        spawn_id=spawn_id,
        total_messages=len(assistant_messages),
        showing=_output_window(messages),
        messages=messages,
    )


spawn_log = async_from_sync(spawn_log_sync)


__all__ = [
    "SpawnLogInput",
    "SpawnLogMessage",
    "SpawnLogOutput",
    "spawn_log",
    "spawn_log_sync",
]
