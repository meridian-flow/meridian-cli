"""OpenCode harness event -> AG-UI event mapper."""

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

from meridian.lib.harness.connections.base import HarnessEvent

logger = logging.getLogger(__name__)


class OpenCodeAGUIMapper:
    """Stateful translator for OpenCode NDJSON/SSE events."""

    def __init__(self) -> None:
        self._run_counter = 0
        self._current_run_id: str | None = None

        self._text_message_id: str | None = None
        self._reasoning_message_id: str | None = None
        self._last_tool_call_id: str | None = None

    def make_run_started(self, spawn_id: str) -> RunStartedEvent:
        self._run_counter += 1
        self._current_run_id = f"{spawn_id}-run-{self._run_counter}"
        self._text_message_id = None
        self._reasoning_message_id = None
        self._last_tool_call_id = None
        return RunStartedEvent(thread_id=spawn_id, run_id=self._current_run_id)

    def make_run_finished(self, spawn_id: str) -> RunFinishedEvent:
        run_id = self._current_run_id
        if run_id is None:
            if self._run_counter <= 0:
                self._run_counter = 1
            run_id = f"{spawn_id}-run-{self._run_counter}"
        self._current_run_id = None
        self._text_message_id = None
        self._reasoning_message_id = None
        return RunFinishedEvent(thread_id=spawn_id, run_id=run_id)

    def translate(self, event: HarnessEvent) -> list[BaseEvent]:
        try:
            if event.event_type == "agent_message_chunk":
                return self._close_reasoning_message() + self._translate_agent_message_chunk(
                    event.payload
                )
            if event.event_type == "agent_thought_chunk":
                return self._close_text_message() + self._translate_agent_thought_chunk(
                    event.payload
                )
            if event.event_type == "tool_call":
                return self._close_open_messages() + self._translate_tool_call(event.payload)
            if event.event_type == "tool_call_update":
                return self._close_open_messages() + self._translate_tool_call_update(event.payload)
            if event.event_type in {"user_message_chunk", "session_info_update"}:
                return self._close_open_messages()
            return self._close_open_messages()
        except Exception:
            logger.warning("Failed translating OpenCode event", exc_info=True)
            return []

    def _translate_agent_message_chunk(self, payload: dict[str, object]) -> list[BaseEvent]:
        text = _extract_text(payload)
        if text is None:
            logger.warning("OpenCode agent_message_chunk missing text payload")
            return []

        events: list[BaseEvent] = []
        if self._text_message_id is None:
            self._text_message_id = _new_message_id()
            events.append(TextMessageStartEvent(message_id=self._text_message_id, role="assistant"))
        events.append(TextMessageContentEvent(message_id=self._text_message_id, delta=text))
        return events

    def _translate_agent_thought_chunk(self, payload: dict[str, object]) -> list[BaseEvent]:
        text = _extract_text(payload)
        if text is None:
            logger.warning("OpenCode agent_thought_chunk missing text payload")
            return []

        events: list[BaseEvent] = []
        if self._reasoning_message_id is None:
            self._reasoning_message_id = _new_message_id()
            events.append(
                ReasoningMessageStartEvent(
                    message_id=self._reasoning_message_id,
                    role="reasoning",
                )
            )
        events.append(
            ReasoningMessageContentEvent(message_id=self._reasoning_message_id, delta=text)
        )
        return events

    def _translate_tool_call(self, payload: dict[str, object]) -> list[BaseEvent]:
        tool_call_id = _extract_tool_call_id(payload)
        if tool_call_id is None:
            tool_call_id = f"tool-{uuid4()}"

        tool_name = (
            _coerce_str(payload.get("toolName"))
            or _coerce_str(payload.get("tool_name"))
            or _coerce_str(payload.get("name"))
            or _coerce_str(payload.get("tool"))
            or "ToolCall"
        )
        args_delta = _extract_args_delta(payload)
        self._last_tool_call_id = tool_call_id

        return [
            ToolCallStartEvent(tool_call_id=tool_call_id, tool_call_name=tool_name),
            ToolCallArgsEvent(tool_call_id=tool_call_id, delta=args_delta),
            ToolCallEndEvent(tool_call_id=tool_call_id),
        ]

    def _translate_tool_call_update(self, payload: dict[str, object]) -> list[BaseEvent]:
        tool_call_id = _extract_tool_call_id(payload) or self._last_tool_call_id
        if tool_call_id is None:
            logger.warning("OpenCode tool_call_update missing tool_call_id")
            return []

        content_value = (
            payload.get("result")
            or payload.get("output")
            or payload.get("content")
            or payload.get("update")
            or payload.get("delta")
            or payload.get("message")
            or payload
        )
        result_text = _stringify(content_value)

        return [
            ToolCallResultEvent(
                message_id=str(uuid4()),
                tool_call_id=tool_call_id,
                content=result_text,
            )
        ]

    def _close_open_messages(self) -> list[BaseEvent]:
        return self._close_text_message() + self._close_reasoning_message()

    def _close_text_message(self) -> list[BaseEvent]:
        if self._text_message_id is None:
            return []
        message_id = self._text_message_id
        self._text_message_id = None
        return [TextMessageEndEvent(message_id=message_id)]

    def _close_reasoning_message(self) -> list[BaseEvent]:
        if self._reasoning_message_id is None:
            return []
        message_id = self._reasoning_message_id
        self._reasoning_message_id = None
        return [ReasoningMessageEndEvent(message_id=message_id)]


def _coerce_str(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _new_message_id() -> str:
    return f"msg-{uuid4().hex[:8]}"


def _stringify(value: object) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _extract_text(payload: dict[str, object]) -> str | None:
    for key in ("delta", "text", "chunk", "content", "message"):
        value = payload.get(key)
        if isinstance(value, str):
            return value

    chunk_obj = payload.get("chunk")
    if isinstance(chunk_obj, dict):
        chunk_payload = cast("dict[str, object]", chunk_obj)
        nested_text = _extract_text(chunk_payload)
        if nested_text is not None:
            return nested_text

    return None


def _extract_tool_call_id(payload: dict[str, object]) -> str | None:
    for key in ("toolCallId", "tool_call_id", "callId", "id", "itemId"):
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized

    call_obj = payload.get("tool_call")
    if isinstance(call_obj, dict):
        return _extract_tool_call_id(cast("dict[str, object]", call_obj))
    return None


def _extract_args_delta(payload: dict[str, object]) -> str:
    for key in ("arguments", "args", "input", "delta"):
        value = payload.get(key)
        if value is None:
            continue
        return _stringify(value)
    return _stringify(payload)


__all__ = ["OpenCodeAGUIMapper"]
