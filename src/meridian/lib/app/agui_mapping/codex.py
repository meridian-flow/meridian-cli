"""Codex harness event -> AG-UI event mapper."""

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
    StepFinishedEvent,
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


class CodexAGUIMapper:
    """Stateful translator for Codex JSON-RPC notifications."""

    def __init__(self) -> None:
        self._run_counter = 0
        self._current_run_id: str | None = None
        self._active_text_message_id: str | None = None

    def make_run_started(self, spawn_id: str) -> RunStartedEvent:
        self._run_counter += 1
        self._current_run_id = f"{spawn_id}-run-{self._run_counter}"
        self._active_text_message_id = None
        return RunStartedEvent(thread_id=spawn_id, run_id=self._current_run_id)

    def make_run_finished(self, spawn_id: str) -> RunFinishedEvent:
        run_id = self._current_run_id
        if run_id is None:
            if self._run_counter <= 0:
                self._run_counter = 1
            run_id = f"{spawn_id}-run-{self._run_counter}"
        self._current_run_id = None
        self._active_text_message_id = None
        return RunFinishedEvent(thread_id=spawn_id, run_id=run_id)

    def translate(self, event: HarnessEvent) -> list[BaseEvent]:
        try:
            if event.event_type == "item/agentMessage":
                return self._translate_agent_message(event.payload)
            if event.event_type == "item/commandExecution":
                return self._translate_tool_lifecycle(
                    event.payload,
                    default_name="CommandExecution",
                )
            if event.event_type == "item/fileChange":
                return self._translate_tool_lifecycle(event.payload, default_name="FileWrite")
            if event.event_type == "item/reasoning":
                return self._translate_reasoning(event.payload)
            if event.event_type == "item/webSearch":
                return self._translate_tool_lifecycle(event.payload, default_name="WebSearch")
            if event.event_type == "item/mcpToolCall":
                return self._translate_mcp_tool_call(event.payload)
            if event.event_type == "turn/completed":
                events: list[BaseEvent] = []
                if self._active_text_message_id is not None:
                    events.append(TextMessageEndEvent(message_id=self._active_text_message_id))
                    self._active_text_message_id = None
                step_name = _coerce_str(event.payload.get("turnId")) or "turn"
                events.append(StepFinishedEvent(step_name=step_name))
                return events
            return []
        except Exception:
            logger.warning("Failed translating Codex event", exc_info=True)
            return []

    def _translate_agent_message(self, payload: dict[str, object]) -> list[BaseEvent]:
        text = _extract_text(payload)
        if text is None:
            logger.warning("Codex item/agentMessage missing text payload")
            return []

        events: list[BaseEvent] = []
        if self._active_text_message_id is None:
            self._active_text_message_id = _new_message_id()
            events.append(
                TextMessageStartEvent(message_id=self._active_text_message_id, role="assistant")
            )
        events.append(TextMessageContentEvent(message_id=self._active_text_message_id, delta=text))
        return events

    def _translate_reasoning(self, payload: dict[str, object]) -> list[BaseEvent]:
        text = _extract_text(payload)
        if text is None:
            logger.warning("Codex item/reasoning missing text payload")
            return []

        message_id = str(uuid4())
        return [
            ReasoningMessageStartEvent(message_id=message_id, role="reasoning"),
            ReasoningMessageContentEvent(message_id=message_id, delta=text),
            ReasoningMessageEndEvent(message_id=message_id),
        ]

    def _translate_tool_lifecycle(
        self,
        payload: dict[str, object],
        *,
        default_name: str,
    ) -> list[BaseEvent]:
        tool_call_id = _extract_tool_call_id(payload)
        if tool_call_id is None:
            tool_call_id = f"tool-{uuid4()}"

        tool_name = (
            _coerce_str(payload.get("toolName"))
            or _coerce_str(payload.get("tool_name"))
            or _coerce_str(payload.get("name"))
            or default_name
        )
        args_delta = _extract_args_delta(payload)

        return [
            ToolCallStartEvent(tool_call_id=tool_call_id, tool_call_name=tool_name),
            ToolCallArgsEvent(tool_call_id=tool_call_id, delta=args_delta),
            ToolCallEndEvent(tool_call_id=tool_call_id),
        ]

    def _translate_mcp_tool_call(self, payload: dict[str, object]) -> list[BaseEvent]:
        lifecycle_events = self._translate_tool_lifecycle(payload, default_name="McpToolCall")

        tool_call_id = _extract_tool_call_id(payload)
        if tool_call_id is None:
            # _translate_tool_lifecycle generated a deterministic fallback for this call.
            generated = lifecycle_events[0]
            if isinstance(generated, ToolCallStartEvent):
                tool_call_id = generated.tool_call_id
            else:
                tool_call_id = f"tool-{uuid4()}"

        result_value = (
            payload.get("result")
            or payload.get("output")
            or payload.get("content")
            or payload.get("message")
            or payload
        )
        result_text = _stringify(result_value)

        lifecycle_events.append(
            ToolCallResultEvent(
                message_id=str(uuid4()),
                tool_call_id=tool_call_id,
                content=result_text,
            )
        )
        return lifecycle_events


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
    direct_candidates = ("delta", "text", "message", "reasoning", "content")
    for key in direct_candidates:
        value = payload.get(key)
        if isinstance(value, str):
            return value

    item_obj = payload.get("item")
    if isinstance(item_obj, dict):
        item_payload = cast("dict[str, object]", item_obj)
        nested = _extract_text(item_payload)
        if nested is not None:
            return nested

    content_obj = payload.get("content")
    if isinstance(content_obj, list):
        rendered_parts: list[str] = []
        for chunk in cast("list[object]", content_obj):
            if isinstance(chunk, str):
                rendered_parts.append(chunk)
                continue
            if isinstance(chunk, dict):
                chunk_payload = cast("dict[str, object]", chunk)
                text = _coerce_str(chunk_payload.get("text")) or _coerce_str(
                    chunk_payload.get("delta")
                )
                if text is not None:
                    rendered_parts.append(text)
        if rendered_parts:
            return "".join(rendered_parts)

    return None


def _extract_tool_call_id(payload: dict[str, object]) -> str | None:
    for key in ("toolCallId", "tool_call_id", "callId", "commandId", "id", "itemId"):
        value = payload.get(key)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return normalized

    item_obj = payload.get("item")
    if isinstance(item_obj, dict):
        return _extract_tool_call_id(cast("dict[str, object]", item_obj))
    return None


def _extract_args_delta(payload: dict[str, object]) -> str:
    for key in ("arguments", "args", "input", "delta", "command", "path"):
        value = payload.get(key)
        if value is None:
            continue
        return _stringify(value)
    return _stringify(payload)


__all__ = ["CodexAGUIMapper"]
