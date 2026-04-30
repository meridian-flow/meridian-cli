"""Claude HarnessEvent to ChatEvent normalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast
from uuid import uuid4

from meridian.lib.chat.protocol import (
    CONTENT_DELTA,
    TURN_COMPLETED,
    TURN_STARTED,
    ChatEvent,
    utc_now_iso,
)
from meridian.lib.harness.connections.base import HarnessEvent
from meridian.lib.streaming.drain_policy import TURN_BOUNDARY_EVENT_TYPE

HARNESS_ID = "claude"
ITEM_STARTED = "item.started"
ITEM_UPDATED = "item.updated"
ITEM_COMPLETED = "item.completed"


@dataclass
class _BlockState:
    index: int
    block_type: str
    item_id: str | None = None
    name: str | None = None
    input_json: str = ""


class ClaudeNormalizer:
    """Stateful Claude stream normalizer for one backing execution."""

    def __init__(self, chat_id: str, execution_id: str) -> None:
        self._chat_id = chat_id
        self._execution_id = execution_id
        self._turn_id: str | None = None
        self._blocks: dict[int, _BlockState] = {}
        self._completed_for_turn = False

    def reset(self) -> None:
        self._turn_id = None
        self._blocks.clear()
        self._completed_for_turn = False

    def normalize(self, event: HarnessEvent) -> list[ChatEvent]:
        match event.event_type:
            case "message_start":
                return [self._message_start(event)]
            case "content_block_start":
                return self._content_block_start(event)
            case "content_block_delta":
                return self._content_block_delta(event)
            case "content_block_stop":
                return self._content_block_stop(event)
            case "message_stop":
                return []
            case "result":
                return self._turn_completed(event)
            case value if value == TURN_BOUNDARY_EVENT_TYPE:
                return self._turn_completed(event)
            case _:
                return []

    def _message_start(self, event: HarnessEvent) -> ChatEvent:
        self._turn_id = f"turn-{uuid4()}"
        self._blocks.clear()
        self._completed_for_turn = False
        payload = _as_dict(event.payload.get("message")) or event.payload
        model = _str(payload.get("model"))
        usage = _as_dict(payload.get("usage"))
        event_payload: dict[str, Any] = {}
        if model is not None:
            event_payload["model"] = model
        if usage is not None:
            event_payload["usage"] = usage
        return self._event(TURN_STARTED, event, payload=event_payload)

    def _content_block_start(self, event: HarnessEvent) -> list[ChatEvent]:
        index = _index(event.payload)
        block = _as_dict(event.payload.get("content_block")) or event.payload
        block_type = _str(block.get("type")) or "unknown"
        item_id = _str(block.get("id")) or (f"item-{uuid4()}" if block_type == "tool_use" else None)
        name = _str(block.get("name"))
        self._blocks[index] = _BlockState(
            index=index,
            block_type=block_type,
            item_id=item_id,
            name=name,
        )
        if block_type != "tool_use" or item_id is None:
            return []
        return [
            self._event(
                ITEM_STARTED,
                event,
                item_id=item_id,
                payload={
                    "item_type": name or "tool_use",
                    "name": name,
                    "raw_type": block_type,
                },
            )
        ]

    def _content_block_delta(self, event: HarnessEvent) -> list[ChatEvent]:
        index = _index(event.payload)
        block = self._blocks.get(index)
        delta = _as_dict(event.payload.get("delta")) or event.payload
        delta_type = _str(delta.get("type"))
        if delta_type == "text_delta":
            text = _str(delta.get("text")) or ""
            return [
                self._event(
                    CONTENT_DELTA,
                    event,
                    item_id=block.item_id if block else None,
                    payload={"stream_kind": "assistant_text", "text": text},
                )
            ]
        if delta_type == "thinking_delta":
            text = _str(delta.get("thinking")) or _str(delta.get("text")) or ""
            return [
                self._event(
                    CONTENT_DELTA,
                    event,
                    item_id=block.item_id if block else None,
                    payload={"stream_kind": "reasoning_text", "text": text},
                )
            ]
        if delta_type == "input_json_delta" and block is not None and block.item_id is not None:
            partial = _str(delta.get("partial_json")) or ""
            block.input_json += partial
            return [
                self._event(
                    ITEM_UPDATED,
                    event,
                    item_id=block.item_id,
                    payload={"input_json_delta": partial, "input_json": block.input_json},
                )
            ]
        return []

    def _content_block_stop(self, event: HarnessEvent) -> list[ChatEvent]:
        index = _index(event.payload)
        block = self._blocks.pop(index, None)
        if block is None or block.block_type != "tool_use" or block.item_id is None:
            return []
        return [
            self._event(
                ITEM_COMPLETED,
                event,
                item_id=block.item_id,
                payload={
                    "item_type": block.name or "tool_use",
                    "name": block.name,
                    "input_json": block.input_json,
                },
            )
        ]

    def _turn_completed(self, event: HarnessEvent) -> list[ChatEvent]:
        if self._turn_id is None:
            self._turn_id = f"turn-{uuid4()}"
        if self._completed_for_turn:
            return []
        self._completed_for_turn = True
        payload: dict[str, Any] = {}
        for key in (
            "status",
            "exit_code",
            "error",
            "usage",
            "cost_usd",
            "duration_ms",
            "synthetic",
        ):
            if key in event.payload:
                payload[key] = event.payload[key]
        if "total_cost_usd" in event.payload:
            payload["cost_usd"] = event.payload["total_cost_usd"]
        chat_event = self._event(TURN_COMPLETED, event, payload=payload)
        self._turn_id = None
        self._blocks.clear()
        return [chat_event]

    def _event(
        self,
        event_type: str,
        event: HarnessEvent,
        *,
        item_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> ChatEvent:
        return ChatEvent(
            type=event_type,
            seq=0,
            chat_id=self._chat_id,
            execution_id=self._execution_id,
            timestamp=utc_now_iso(),
            turn_id=self._turn_id,
            item_id=item_id,
            payload=payload or {},
            harness_id=event.harness_id,
        )


def _index(payload: dict[str, object]) -> int:
    value = payload.get("index")
    return value if isinstance(value, int) else 0


def _as_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast("dict[str, object]", value)


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["ClaudeNormalizer"]
