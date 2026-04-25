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
    RunErrorEvent,
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
from meridian.lib.app.agui_mapping.extensions import make_run_error_event
from meridian.lib.harness.connections.base import HarnessEvent

logger = logging.getLogger(__name__)


class CodexAGUIMapper:
    """Stateful translator for Codex JSON-RPC notifications."""

    def __init__(self) -> None:
        self._run_counter = 0
        self._current_run_id: str | None = None
        self._active_text_message_id: str | None = None
        self._active_items: dict[str, dict[str, str]] = {}

    def make_run_started(self, spawn_id: str) -> RunStartedEvent:
        self._run_counter += 1
        self._current_run_id = f"{spawn_id}-run-{self._run_counter}"
        self._active_text_message_id = None
        self._active_items = {}
        return RunStartedEvent(thread_id=spawn_id, run_id=self._current_run_id)

    def make_run_finished(self, spawn_id: str) -> RunFinishedEvent:
        run_id = self._current_run_id
        if run_id is None:
            if self._run_counter <= 0:
                self._run_counter = 1
            run_id = f"{spawn_id}-run-{self._run_counter}"
        self._current_run_id = None
        self._active_text_message_id = None
        self._active_items = {}
        return RunFinishedEvent(thread_id=spawn_id, run_id=run_id)

    def make_run_error(self, message: str) -> RunErrorEvent:
        return make_run_error_event(message)

    def translate(self, event: HarnessEvent) -> list[BaseEvent]:
        try:
            if event.event_type == "error/connectionClosed":
                message = event.payload.get("message", "Connection closed unexpectedly")
                if not isinstance(message, str):
                    message = str(message)
                return [self.make_run_error(message)]
            if event.event_type == "cancelled":
                message = event.payload.get("error")
                if not isinstance(message, str) or not message:
                    message = "Cancelled"
                return [make_run_error_event(message, is_cancelled=True)]
            if event.event_type == "item/agentMessage":
                return self._translate_agent_message(event.payload)
            if event.event_type == "item/agentMessage/delta":
                return self._translate_agent_message_delta(event.payload)
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
            if event.event_type == "item/commandExecution/outputDelta":
                return self._translate_output_delta(event.payload)
            if event.event_type == "item/started":
                return self._translate_item_started(event.payload)
            if event.event_type == "item/completed":
                return self._translate_item_completed(event.payload)
            if event.event_type == "turn/completed":
                events: list[BaseEvent] = []
                events.extend(self._close_active_text_message())
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

    def _translate_agent_message_delta(self, payload: dict[str, object]) -> list[BaseEvent]:
        raw_delta = payload.get("delta")
        delta = raw_delta if isinstance(raw_delta, str) else None
        if delta is None or delta == "":
            logger.warning("Codex item/agentMessage/delta missing delta payload")
            return []

        events: list[BaseEvent] = []
        if self._active_text_message_id is None:
            self._active_text_message_id = _new_message_id()
            events.append(
                TextMessageStartEvent(message_id=self._active_text_message_id, role="assistant")
            )
        events.append(TextMessageContentEvent(message_id=self._active_text_message_id, delta=delta))
        return events

    def _close_active_text_message(self) -> list[BaseEvent]:
        if self._active_text_message_id is None:
            return []
        message_id = self._active_text_message_id
        self._active_text_message_id = None
        return [TextMessageEndEvent(message_id=message_id)]

    def _translate_item_started(self, payload: dict[str, object]) -> list[BaseEvent]:
        item = payload.get("item")
        if not isinstance(item, dict):
            return []

        item_dict = cast("dict[str, object]", item)
        item_type = _coerce_str(item_dict.get("type"))
        item_id = _coerce_str(item_dict.get("id"))

        if item_type == "commandExecution":
            if item_id is None:
                item_id = f"tool-{uuid4()}"
            command = _coerce_str(item_dict.get("command")) or "CommandExecution"
            self._active_items[item_id] = {"type": "commandExecution", "tool_call_id": item_id}
            return [ToolCallStartEvent(tool_call_id=item_id, tool_call_name=command)]

        if item_type == "reasoning":
            if item_id is None:
                item_id = f"reasoning-{uuid4()}"
            message_id = _new_message_id()
            self._active_items[item_id] = {"type": "reasoning", "message_id": message_id}
            return [ReasoningMessageStartEvent(message_id=message_id, role="reasoning")]

        return []

    def _translate_item_completed(self, payload: dict[str, object]) -> list[BaseEvent]:
        item = payload.get("item")
        if not isinstance(item, dict):
            return self._close_active_text_message()

        item_dict = cast("dict[str, object]", item)
        item_type = _coerce_str(item_dict.get("type"))
        item_id = _coerce_str(item_dict.get("id"))

        if item_type == "commandExecution":
            tool_call_id: str | None = None
            if item_id and item_id in self._active_items:
                info = self._active_items.pop(item_id)
                tool_call_id = info.get("tool_call_id")
            elif item_id:
                tool_call_id = item_id

            if tool_call_id is None:
                tool_call_id = f"tool-{uuid4()}"
                logger.warning(
                    "Codex item/completed missing item.id; lifecycle IDs will not match"
                )

            aggregated = item_dict.get("aggregatedOutput")
            result_content = aggregated if isinstance(aggregated, str) else ""

            return [
                ToolCallEndEvent(tool_call_id=tool_call_id),
                ToolCallResultEvent(
                    message_id=str(uuid4()),
                    tool_call_id=tool_call_id,
                    content=result_content,
                ),
            ]

        if item_type == "reasoning":
            events: list[BaseEvent] = []

            if item_id and item_id in self._active_items:
                info = self._active_items.pop(item_id)
                message_id = info.get("message_id") or _new_message_id()
            else:
                message_id = _new_message_id()
                events.append(ReasoningMessageStartEvent(message_id=message_id, role="reasoning"))

            content = _extract_reasoning_content(item_dict)
            if content:
                events.append(ReasoningMessageContentEvent(message_id=message_id, delta=content))

            events.append(ReasoningMessageEndEvent(message_id=message_id))
            return events

        if item_type == "agentMessage":
            return self._close_active_text_message()

        return self._close_active_text_message()

    def _translate_output_delta(self, payload: dict[str, object]) -> list[BaseEvent]:
        item_id = _coerce_str(payload.get("itemId"))
        if item_id is None or item_id not in self._active_items:
            logger.warning("Codex outputDelta for unknown itemId: %s", item_id)
            return []

        info = self._active_items[item_id]
        tool_call_id = info.get("tool_call_id")
        if tool_call_id is None:
            logger.warning("Codex outputDelta for non-tool item: %s", item_id)
            return []

        delta = payload.get("delta")
        if delta is None:
            delta_str = ""
        elif isinstance(delta, str):
            delta_str = delta
        else:
            delta_str = _stringify(delta)

        return [ToolCallArgsEvent(tool_call_id=tool_call_id, delta=delta_str)]

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
            generated_tool_call_id = getattr(generated, "tool_call_id", None)
            if isinstance(generated_tool_call_id, str) and generated_tool_call_id.strip():
                tool_call_id = generated_tool_call_id
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


def _extract_reasoning_content(item: dict[str, object]) -> str | None:
    for key in ("content", "summary"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            parts: list[str] = []
            for chunk in cast("list[object]", value):
                if isinstance(chunk, str) and chunk.strip():
                    parts.append(chunk.strip())
                elif isinstance(chunk, dict):
                    text = _coerce_str(cast("dict[str, object]", chunk).get("text"))
                    if text:
                        parts.append(text)
            if parts:
                return " ".join(parts)
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
