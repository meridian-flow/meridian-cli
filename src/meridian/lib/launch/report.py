"""Spawn report extraction from assistant output with report.md preference."""

import json
import logging
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.types import SpawnId
from meridian.lib.harness.adapter import SubprocessHarness
from meridian.lib.state.artifact_store import ArtifactStore

from .artifact_io import read_artifact_text

ReportSource = Literal["report_md", "assistant_message"]
_LOGGER = logging.getLogger(__name__)


class ExtractedReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    content: str | None
    source: ReportSource | None


def _text_from_value(value: object) -> str:
    if isinstance(value, str):
        return value.strip()

    if isinstance(value, list):
        parts = [_text_from_value(item) for item in cast("list[object]", value)]
        return "\n".join(part for part in parts if part).strip()

    if isinstance(value, dict):
        payload = cast("dict[str, object]", value)
        parts: list[str] = []
        for key in ("text", "message", "output"):
            if key in payload:
                text = _text_from_value(payload[key])
                if text:
                    parts.append(text)
        if "content" in payload:
            text = _text_from_value(payload["content"])
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    return ""


def _assistant_texts(payload: object) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        obj = cast("dict[str, object]", payload)
        role = str(obj.get("role", "")).lower()
        event_type = str(obj.get("type", obj.get("event", ""))).lower()

        if role == "assistant" or "assistant" in event_type:
            content_text = _text_from_value(obj.get("content"))
            if content_text:
                found.append(content_text)
            for key in ("text", "message", "output"):
                text = _text_from_value(obj.get(key))
                if text:
                    found.append(text)

        if "choices" in obj and isinstance(obj["choices"], list):
            for choice in cast("list[object]", obj["choices"]):
                if not isinstance(choice, dict):
                    continue
                choice_payload = cast("dict[str, object]", choice)
                message = choice_payload.get("message")
                if isinstance(message, dict):
                    message_payload = cast("dict[str, object]", message)
                    message_role = str(message_payload.get("role", "")).lower()
                    if message_role == "assistant":
                        text = _text_from_value(message_payload.get("content"))
                        if text:
                            found.append(text)

        for nested in obj.values():
            found.extend(_assistant_texts(nested))
        return found

    if isinstance(payload, list):
        for item in cast("list[object]", payload):
            found.extend(_assistant_texts(item))
    return found


def _extract_last_assistant_message(output_lines: str) -> str | None:
    last_assistant: str | None = None
    last_text_line: str | None = None
    for line in output_lines.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        last_text_line = stripped
        try:
            payload_obj = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        assistants = _assistant_texts(payload_obj)
        if assistants:
            last_assistant = assistants[-1].strip()
    if last_assistant:
        return last_assistant
    return last_text_line


def extract_or_fallback_report(
    artifacts: ArtifactStore,
    spawn_id: SpawnId,
    *,
    adapter: SubprocessHarness | None = None,
) -> ExtractedReport:
    """Extract report text from assistant output, preferring report.md when available."""

    report_content = read_artifact_text(artifacts, spawn_id, "report.md").strip()
    if report_content:
        return ExtractedReport(content=report_content, source="report_md")

    if adapter is not None:
        try:
            adapted_report = adapter.extract_report(artifacts, spawn_id)
        except Exception:
            _LOGGER.warning(
                "adapter.extract_report failed for spawn %s",
                spawn_id,
                exc_info=True,
            )
        else:
            adapted_text = adapted_report.strip() if adapted_report else ""
            if adapted_text:
                return ExtractedReport(content=adapted_text, source="assistant_message")

    output_lines = read_artifact_text(artifacts, spawn_id, "output.jsonl")
    assistant_message = _extract_last_assistant_message(output_lines)
    assistant_report = assistant_message.strip() if assistant_message else ""
    if not assistant_report:
        return ExtractedReport(content=None, source=None)
    return ExtractedReport(content=assistant_report, source="assistant_message")
