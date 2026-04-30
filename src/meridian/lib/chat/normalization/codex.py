"""Codex HarnessEvent to ChatEvent normalization."""

from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from meridian.lib.chat.normalization.common import canonical_item_type
from meridian.lib.chat.normalization.synthetic import is_turn_boundary_event
from meridian.lib.chat.protocol import (
    CONTENT_DELTA,
    TURN_COMPLETED,
    TURN_STARTED,
    ChatEvent,
    utc_now_iso,
)
from meridian.lib.harness.connections.base import HarnessEvent

HARNESS_ID = "codex"
ITEM_STARTED = "item.started"
ITEM_UPDATED = "item.updated"
ITEM_COMPLETED = "item.completed"
FILES_PERSISTED = "files.persisted"
REQUEST_OPENED = "request.opened"
REQUEST_RESOLVED = "request.resolved"
USER_INPUT_REQUESTED = "user_input.requested"
RUNTIME_WARNING = "runtime.warning"


class CodexNormalizer:
    """Stateful Codex JSON-RPC stream normalizer for one backing execution."""

    def __init__(self, chat_id: str, execution_id: str) -> None:
        self._chat_id = chat_id
        self._execution_id = execution_id
        self._turn_id: str | None = None
        self._completed_for_turn = False

    def reset(self) -> None:
        self._turn_id = None
        self._completed_for_turn = False

    def normalize(self, event: HarnessEvent) -> list[ChatEvent]:
        match event.event_type:
            case "turn/started":
                return [self._turn_started(event)]
            case "turn/completed":
                return [self._turn_completed(event)]
            case value if is_turn_boundary_event(value):
                return [self._turn_completed(event)]
            case "item/tool/started":
                return [self._item_event(ITEM_STARTED, event)]
            case "item/tool/updated":
                return [self._item_event(ITEM_UPDATED, event), *self._file_events(event)]
            case "item/tool/completed":
                return [self._item_event(ITEM_COMPLETED, event), *self._file_events(event)]
            case "agent_message_chunk" | "content/delta" | "agent/message/delta":
                return [self._content_delta(event, "assistant_text")]
            case "agent_thought_chunk" | "reasoning/delta" | "agent/thought/delta":
                return [self._content_delta(event, "reasoning_text")]
            case "request.opened" | "request/opened":
                return [self._request_event(REQUEST_OPENED, event)]
            case "request.resolved" | "request/resolved":
                return [self._request_event(REQUEST_RESOLVED, event)]
            case "user_input.requested" | "user_input/requested":
                return [self._request_event(USER_INPUT_REQUESTED, event)]
            case "files/persisted" | "files.persisted" | "file/write" | "file/persisted":
                return self._file_events(event) or [
                    self._event(FILES_PERSISTED, event, payload=dict(event.payload))
                ]
            case "warning/unsupportedServerRequest" | "warning/approvalRejected":
                return [self._event(RUNTIME_WARNING, event, payload=dict(event.payload))]
            case _:
                return []

    def _turn_started(self, event: HarnessEvent) -> ChatEvent:
        turn_id = (
            _str(event.payload.get("turn_id"))
            or _str(event.payload.get("id"))
            or f"turn-{uuid4()}"
        )
        self._turn_id = turn_id
        self._completed_for_turn = False
        payload: dict[str, Any] = {}
        for key in ("model", "thread_id", "session_id"):
            if key in event.payload:
                payload[key] = event.payload[key]
        return self._event(TURN_STARTED, event, payload=payload)

    def _turn_completed(self, event: HarnessEvent) -> ChatEvent:
        if self._turn_id is None:
            self._turn_id = _str(event.payload.get("turn_id")) or f"turn-{uuid4()}"
        payload: dict[str, Any] = {}
        for key in ("status", "exit_code", "error", "usage", "duration_ms", "synthetic"):
            if key in event.payload:
                payload[key] = event.payload[key]
        chat_event = self._event(TURN_COMPLETED, event, payload=payload)
        self._turn_id = None
        self._completed_for_turn = True
        return chat_event

    def _item_event(self, event_type: str, event: HarnessEvent) -> ChatEvent:
        item = _item_payload(event.payload)
        item_id = _str(item.get("id")) or _str(event.payload.get("item_id")) or f"item-{uuid4()}"
        raw_type = (
            _str(item.get("type"))
            or _str(event.payload.get("tool_type"))
            or _str(event.payload.get("type"))
        )
        name = _str(item.get("name")) or _str(event.payload.get("name"))
        payload = dict(event.payload)
        payload["item_type"] = canonical_item_type(raw_type, name)
        if raw_type is not None:
            payload["raw_type"] = raw_type
        if name is not None:
            payload["name"] = name
        return self._event(event_type, event, item_id=item_id, payload=payload)

    def _content_delta(self, event: HarnessEvent, stream_kind: str) -> ChatEvent:
        return self._event(
            CONTENT_DELTA,
            event,
            item_id=_str(event.payload.get("item_id")),
            payload={"stream_kind": stream_kind, "text": _text_from_payload(event.payload)},
        )

    def _request_event(self, event_type: str, event: HarnessEvent) -> ChatEvent:
        request_id = _str(event.payload.get("request_id")) or _str(event.payload.get("id"))
        payload = dict(event.payload)
        if event_type == USER_INPUT_REQUESTED:
            payload.setdefault("request_type", "user_input")
        return self._event(event_type, event, request_id=request_id, payload=payload)

    def _file_events(self, event: HarnessEvent) -> list[ChatEvent]:
        files = _extract_files(event.payload)
        if not files:
            return []
        return [self._event(FILES_PERSISTED, event, payload={"files": files})]

    def _event(
        self,
        event_type: str,
        event: HarnessEvent,
        *,
        item_id: str | None = None,
        request_id: str | None = None,
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
            request_id=request_id,
            payload=payload or {},
            harness_id=event.harness_id,
        )


def _item_payload(payload: dict[str, object]) -> dict[str, object]:
    item = payload.get("item") or payload.get("tool")
    return cast("dict[str, object]", item) if isinstance(item, dict) else payload


def _text_from_payload(payload: dict[str, object]) -> str:
    for key in ("text", "delta", "content"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    nested = payload.get("message")
    if isinstance(nested, dict):
        return _text_from_payload(cast("dict[str, object]", nested))
    return ""


def _extract_files(payload: dict[str, object]) -> list[dict[str, object]]:
    value = payload.get("files") or payload.get("paths")
    if isinstance(value, list):
        files: list[dict[str, object]] = []
        for entry in cast("list[object]", value):
            if isinstance(entry, str):
                files.append({"path": entry})
            elif isinstance(entry, dict):
                files.append(cast("dict[str, object]", entry))
        return files
    path = payload.get("path") or payload.get("file")
    if isinstance(path, str):
        result: dict[str, object] = {"path": path}
        for key in ("operation", "status"):
            if key in payload:
                result[key] = payload[key]
        return [result]
    return []


def _str(value: object) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["CodexNormalizer"]
