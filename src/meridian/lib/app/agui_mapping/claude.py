"""Claude harness event -> AG-UI event mapper."""

from __future__ import annotations

import json
import logging
from typing import cast
from uuid import uuid4

from ag_ui.core import (
    BaseEvent,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    ReasoningMessageStartEvent,
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallArgsEvent,
    ToolCallEndEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from meridian.lib.app.agui_mapping.extensions import make_run_error_event
from meridian.lib.harness.connections.base import HarnessEvent

logger = logging.getLogger(__name__)


class ClaudeAGUIMapper:
    """Stateful translator for Claude SDK WebSocket events."""

    def __init__(self) -> None:
        self._run_counter = 0
        self._current_run_id: str | None = None

        self._active_block_type: str | None = None
        self._active_block_index: int | None = None

        self._block_type_by_index: dict[int, str] = {}
        self._text_message_id_by_index: dict[int, str] = {}
        self._reasoning_message_id_by_index: dict[int, str] = {}
        self._tool_call_id_by_index: dict[int, str] = {}

        self._active_text_message_id: str | None = None
        self._active_reasoning_message_id: str | None = None
        self._active_tool_call_id: str | None = None

        self._last_tool_call_id: str | None = None
        self._saw_stream_event = False

    def make_run_started(self, spawn_id: str) -> RunStartedEvent:
        self._run_counter += 1
        self._current_run_id = f"{spawn_id}-run-{self._run_counter}"
        self._saw_stream_event = False
        return RunStartedEvent(thread_id=spawn_id, run_id=self._current_run_id)

    def make_run_finished(self, spawn_id: str) -> RunFinishedEvent:
        run_id = self._current_run_id
        if run_id is None:
            if self._run_counter <= 0:
                self._run_counter = 1
            run_id = f"{spawn_id}-run-{self._run_counter}"
        self._current_run_id = None
        return RunFinishedEvent(thread_id=spawn_id, run_id=run_id)

    def make_run_error(self, message: str) -> RunErrorEvent:
        return make_run_error_event(message)

    def translate(self, event: HarnessEvent) -> list[BaseEvent]:
        try:
            if event.event_type == "error":
                message = event.payload.get("message", "Unknown error")
                if not isinstance(message, str):
                    message = str(message)
                return [self.make_run_error(message)]
            if event.event_type == "stream_event":
                self._saw_stream_event = True
                return self._translate_stream_event(event.payload)
            if event.event_type == "assistant":
                return self._translate_assistant_event(event.payload)
            if event.event_type in {"tool_use_summary", "tool_progress"}:
                return self._translate_tool_result(event.payload)
            if event.event_type == "result":
                return self._translate_result_event(event.payload)
            return []
        except Exception:
            logger.warning("Failed translating Claude event", exc_info=True)
            return []

    def _translate_assistant_event(self, payload: dict[str, object]) -> list[BaseEvent]:
        # stream_event carries richer block deltas; assistant fallback prevents blank UI
        # when Claude only emits final assistant payloads.
        if self._saw_stream_event:
            return []

        text = _extract_assistant_text(payload)
        if text is None:
            return []

        message_id = str(uuid4())
        return [
            TextMessageStartEvent(message_id=message_id, role="assistant"),
            TextMessageContentEvent(message_id=message_id, delta=text),
            TextMessageEndEvent(message_id=message_id),
        ]

    def _translate_result_event(self, payload: dict[str, object]) -> list[BaseEvent]:
        self._saw_stream_event = False

        is_error = bool(payload.get("is_error"))
        subtype = _coerce_str(payload.get("subtype"))
        errors_obj = payload.get("errors")
        error_items = cast("list[object]", errors_obj) if isinstance(errors_obj, list) else None
        has_errors = bool(
            error_items
            and any(isinstance(item, str) and item.strip() for item in error_items)
        )

        if not is_error and subtype != "error_during_execution" and not has_errors:
            return []

        if error_items is not None:
            for item in error_items:
                if isinstance(item, str) and item.strip():
                    return [self.make_run_error(item.strip())]

        message = _coerce_str(payload.get("message")) or "Claude reported an execution error"
        return [self.make_run_error(message)]

    def _translate_stream_event(self, payload: dict[str, object]) -> list[BaseEvent]:
        stream_event_obj = payload.get("event")
        if not isinstance(stream_event_obj, dict):
            logger.warning("Claude stream_event missing object 'event' payload")
            return []

        stream_event = cast("dict[str, object]", stream_event_obj)
        stream_event_type = _coerce_str(stream_event.get("type"))
        if stream_event_type is None:
            logger.warning("Claude stream_event missing string 'type'")
            return []

        if stream_event_type == "content_block_start":
            return self._handle_content_block_start(stream_event)
        if stream_event_type == "content_block_delta":
            return self._handle_content_block_delta(stream_event)
        if stream_event_type == "content_block_stop":
            return self._handle_content_block_stop(stream_event)
        return []

    def _handle_content_block_start(self, stream_event: dict[str, object]) -> list[BaseEvent]:
        block_obj = stream_event.get("content_block")
        if not isinstance(block_obj, dict):
            logger.warning("Claude content_block_start missing object 'content_block'")
            return []

        block = cast("dict[str, object]", block_obj)
        block_type = _coerce_str(block.get("type"))
        if block_type is None:
            logger.warning("Claude content_block_start missing content block type")
            return []

        block_index = _coerce_int(stream_event.get("index"))
        self._set_active_block(block_index=block_index, block_type=block_type)

        if block_type == "text":
            message_id = str(uuid4())
            self._active_text_message_id = message_id
            if block_index is not None:
                self._text_message_id_by_index[block_index] = message_id
            return [TextMessageStartEvent(message_id=message_id, role="assistant")]

        if block_type == "thinking":
            message_id = str(uuid4())
            self._active_reasoning_message_id = message_id
            if block_index is not None:
                self._reasoning_message_id_by_index[block_index] = message_id
            return [ReasoningMessageStartEvent(message_id=message_id, role="reasoning")]

        if block_type == "tool_use":
            tool_call_id = (
                _coerce_str(block.get("tool_use_id"))
                or _coerce_str(block.get("id"))
                or _coerce_str(stream_event.get("tool_use_id"))
            )
            if tool_call_id is None:
                tool_call_id = f"tool-{uuid4()}"
                logger.warning("Claude tool_use start missing tool_use_id; generated fallback ID")

            tool_name = _coerce_str(block.get("name")) or "ToolCall"
            self._active_tool_call_id = tool_call_id
            self._last_tool_call_id = tool_call_id
            if block_index is not None:
                self._tool_call_id_by_index[block_index] = tool_call_id
            return [
                ToolCallStartEvent(
                    tool_call_id=tool_call_id,
                    tool_call_name=tool_name,
                )
            ]

        return []

    def _handle_content_block_delta(self, stream_event: dict[str, object]) -> list[BaseEvent]:
        delta_obj = stream_event.get("delta")
        if not isinstance(delta_obj, dict):
            logger.warning("Claude content_block_delta missing object 'delta'")
            return []

        delta = cast("dict[str, object]", delta_obj)
        block_index = _coerce_int(stream_event.get("index"))
        block_type = self._resolve_block_type(block_index=block_index, delta=delta)
        if block_type is None:
            return []

        if block_type == "text":
            message_id = self._resolve_text_message_id(block_index)
            if message_id is None:
                logger.warning("Claude text delta missing message_id state")
                return []
            text_delta = _extract_delta_text(delta, candidates=("text", "delta"))
            if text_delta is None:
                return []
            return [TextMessageContentEvent(message_id=message_id, delta=text_delta)]

        if block_type == "thinking":
            message_id = self._resolve_reasoning_message_id(block_index)
            if message_id is None:
                logger.warning("Claude thinking delta missing message_id state")
                return []
            text_delta = _extract_delta_text(delta, candidates=("thinking", "text", "delta"))
            if text_delta is None:
                return []
            return [ReasoningMessageContentEvent(message_id=message_id, delta=text_delta)]

        if block_type == "tool_use":
            tool_call_id = self._resolve_tool_call_id(block_index)
            if tool_call_id is None:
                logger.warning("Claude tool delta missing tool_call_id state")
                return []
            args_delta = _extract_delta_text(
                delta,
                candidates=("partial_json", "json", "text", "delta"),
            )
            if args_delta is None:
                return []
            return [ToolCallArgsEvent(tool_call_id=tool_call_id, delta=args_delta)]

        return []

    def _handle_content_block_stop(self, stream_event: dict[str, object]) -> list[BaseEvent]:
        block_index = _coerce_int(stream_event.get("index"))
        block_type = self._resolve_block_type(block_index=block_index, delta=None)
        if block_type is None:
            return []

        self._clear_active_block(block_index=block_index)

        if block_type == "text":
            message_id = self._pop_text_message_id(block_index)
            if message_id is None:
                logger.warning("Claude text stop missing message_id state")
                return []
            return [TextMessageEndEvent(message_id=message_id)]

        if block_type == "thinking":
            message_id = self._pop_reasoning_message_id(block_index)
            if message_id is None:
                logger.warning("Claude thinking stop missing message_id state")
                return []
            return [ReasoningMessageEndEvent(message_id=message_id)]

        if block_type == "tool_use":
            tool_call_id = self._pop_tool_call_id(block_index)
            if tool_call_id is None:
                logger.warning("Claude tool stop missing tool_call_id state")
                return []
            return [ToolCallEndEvent(tool_call_id=tool_call_id)]

        return []

    def _translate_tool_result(self, payload: dict[str, object]) -> list[BaseEvent]:
        tool_call_id = (
            _coerce_str(payload.get("tool_use_id"))
            or _coerce_str(payload.get("toolCallId"))
            or self._last_tool_call_id
        )
        if tool_call_id is None:
            logger.warning("Claude tool result missing tool_use_id")
            return []

        content_value = (
            payload.get("result")
            or payload.get("progress")
            or payload.get("message")
            or payload.get("content")
            or payload
        )
        content = _stringify(content_value)
        if not content:
            return []

        return [
            ToolCallResultEvent(
                message_id=str(uuid4()),
                tool_call_id=tool_call_id,
                content=content,
            )
        ]

    def _set_active_block(self, *, block_index: int | None, block_type: str) -> None:
        self._active_block_type = block_type
        self._active_block_index = block_index
        if block_index is not None:
            self._block_type_by_index[block_index] = block_type

    def _clear_active_block(self, *, block_index: int | None) -> None:
        if block_index is not None:
            self._block_type_by_index.pop(block_index, None)
        if self._active_block_index == block_index:
            self._active_block_index = None
            self._active_block_type = None

    def _resolve_block_type(
        self,
        *,
        block_index: int | None,
        delta: dict[str, object] | None,
    ) -> str | None:
        if block_index is not None and block_index in self._block_type_by_index:
            return self._block_type_by_index[block_index]
        if block_index is None and self._active_block_type is not None:
            return self._active_block_type

        delta_type = _coerce_str(delta.get("type")) if delta is not None else None
        if delta_type == "text_delta":
            return "text"
        if delta_type == "thinking_delta":
            return "thinking"
        if delta_type == "input_json_delta":
            return "tool_use"
        return None

    def _resolve_text_message_id(self, block_index: int | None) -> str | None:
        if block_index is not None:
            return self._text_message_id_by_index.get(block_index)
        return self._active_text_message_id

    def _resolve_reasoning_message_id(self, block_index: int | None) -> str | None:
        if block_index is not None:
            return self._reasoning_message_id_by_index.get(block_index)
        return self._active_reasoning_message_id

    def _resolve_tool_call_id(self, block_index: int | None) -> str | None:
        if block_index is not None:
            return self._tool_call_id_by_index.get(block_index)
        return self._active_tool_call_id or self._last_tool_call_id

    def _pop_text_message_id(self, block_index: int | None) -> str | None:
        if block_index is not None:
            return self._text_message_id_by_index.pop(block_index, None)
        message_id = self._active_text_message_id
        self._active_text_message_id = None
        return message_id

    def _pop_reasoning_message_id(self, block_index: int | None) -> str | None:
        if block_index is not None:
            return self._reasoning_message_id_by_index.pop(block_index, None)
        message_id = self._active_reasoning_message_id
        self._active_reasoning_message_id = None
        return message_id

    def _pop_tool_call_id(self, block_index: int | None) -> str | None:
        if block_index is not None:
            tool_call_id = self._tool_call_id_by_index.pop(block_index, None)
        else:
            tool_call_id = self._active_tool_call_id
            self._active_tool_call_id = None
        if tool_call_id is not None:
            self._last_tool_call_id = tool_call_id
        return tool_call_id


def _coerce_str(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def _extract_delta_text(delta: dict[str, object], *, candidates: tuple[str, ...]) -> str | None:
    for key in candidates:
        value = delta.get(key)
        if isinstance(value, str):
            return value
    return None


def _extract_assistant_text(payload: dict[str, object]) -> str | None:
    direct = (
        payload.get("text")
        or payload.get("message")
        or payload.get("result")
    )
    if isinstance(direct, str):
        normalized = direct.strip()
        if normalized:
            return normalized

    content = payload.get("content")
    text_from_content = _extract_text_from_content(content)
    if text_from_content is not None:
        return text_from_content

    message_obj = payload.get("message")
    if isinstance(message_obj, dict):
        message_payload = cast("dict[str, object]", message_obj)
        nested_content = message_payload.get("content")
        text_from_nested = _extract_text_from_content(nested_content)
        if text_from_nested is not None:
            return text_from_nested
        nested_text = message_payload.get("text")
        if isinstance(nested_text, str):
            normalized = nested_text.strip()
            if normalized:
                return normalized

    return None


def _extract_text_from_content(content: object) -> str | None:
    if isinstance(content, str):
        normalized = content.strip()
        return normalized or None
    if not isinstance(content, list):
        return None

    segments: list[str] = []
    for block in cast("list[object]", content):
        if not isinstance(block, dict):
            continue
        typed_block = cast("dict[str, object]", block)
        if typed_block.get("type") == "text":
            text_value = typed_block.get("text")
            if isinstance(text_value, str) and text_value:
                segments.append(text_value)
    if not segments:
        return None
    return "".join(segments)


def _stringify(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


__all__ = ["ClaudeAGUIMapper"]
