"""Session log operation with compaction-aware segment navigation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import NamedTuple, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.util import FormatContext
from meridian.lib.harness.session_detection import infer_harness_from_untracked_session_ref
from meridian.lib.ops.runtime import async_from_sync, resolve_runtime_root_and_config, resolve_state_root
from meridian.lib.ops.spawn.query import read_spawn_row
from meridian.lib.state import session_store


_CODEX_FILENAME_RE = re.compile(
    r"^rollout-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}-(?P<session_id>[0-9a-fA-F-]{36})\.jsonl$"
)
_MAX_PREVIEW = 120


class SessionLogInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: str = ""
    compaction: int = 0
    last_n: int | None = None
    offset: int = 0
    file_path: str | None = None
    repo_root: str | None = None


class SessionLogMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    role: str
    content: str


class SessionLogOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    total_compactions: int
    segment: int
    segment_messages: int
    showing: str
    messages: tuple[SessionLogMessage, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        message_label = "message" if self.segment_messages == 1 else "messages"
        lines = [
            f"Session {self.session_id} — segment {self.segment}, {self.segment_messages} {message_label} (showing {self.showing})"
        ]
        for message in self.messages:
            lines.append("")
            lines.append(f"--- {message.index} [{message.role}] ---")
            lines.append(message.content)
        return "\n".join(lines)


class _ResolvedTarget(NamedTuple):
    session_id: str
    harness: str | None
    file_path: Path


class _ExtractedMessage(NamedTuple):
    role: str
    content: str


def _normalize_text(value: str) -> str:
    return value.strip()


def _text_from_value(value: object) -> str:
    if isinstance(value, str):
        return _normalize_text(value)

    if isinstance(value, list):
        payload = cast("list[object]", value)
        parts = [_text_from_value(item) for item in payload]
        return "\n".join(part for part in parts if part).strip()

    if isinstance(value, dict):
        payload = cast("dict[str, object]", value)
        parts: list[str] = []
        for key in ("text", "content", "message", "output", "toolUseResult"):
            if key in payload:
                text = _text_from_value(payload[key])
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()

    return ""


def _preview(value: str, *, limit: int = _MAX_PREVIEW) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


def _tool_use_summary(block: dict[str, object]) -> str:
    name = str(block.get("name", "tool")).strip() or "tool"
    tool_input = block.get("input")
    if not isinstance(tool_input, dict):
        return f"[tool: {name}]"

    input_payload = cast("dict[str, object]", tool_input)
    for key in ("file_path", "path", "command", "pattern", "description", "skill"):
        value = input_payload.get(key)
        if isinstance(value, str) and value.strip():
            return f"[tool: {name} {_preview(value.strip())}]"
    return f"[tool: {name}]"


def _tool_result_summary(block: dict[str, object]) -> str:
    content = _text_from_value(block.get("content"))
    if not content:
        return "[tool_result]"
    return f"[tool_result] {content}"


def _extract_claude_content(role: str, content: object) -> list[_ExtractedMessage]:
    messages: list[_ExtractedMessage] = []

    if isinstance(content, str):
        text = _normalize_text(content)
        if text:
            messages.append(_ExtractedMessage(role=role, content=text))
        return messages

    if not isinstance(content, list):
        text = _text_from_value(content)
        if text:
            messages.append(_ExtractedMessage(role=role, content=text))
        return messages

    blocks = cast("list[object]", content)
    for item in blocks:
        if not isinstance(item, dict):
            text = _text_from_value(item)
            if text:
                messages.append(_ExtractedMessage(role=role, content=text))
            continue

        block = cast("dict[str, object]", item)
        block_type = str(block.get("type", "")).strip().lower()
        if block_type == "text":
            text = _text_from_value(block.get("text"))
            if text:
                messages.append(_ExtractedMessage(role=role, content=text))
            continue
        if role == "assistant" and block_type == "tool_use":
            messages.append(_ExtractedMessage(role=role, content=_tool_use_summary(block)))
            continue
        if role == "user" and block_type == "tool_result":
            messages.append(_ExtractedMessage(role=role, content=_tool_result_summary(block)))
            continue

        text = _text_from_value(block)
        if text:
            messages.append(_ExtractedMessage(role=role, content=text))

    return messages


def _extract_codex_response_item(payload: dict[str, object]) -> list[_ExtractedMessage]:
    item_type = str(payload.get("type", "")).strip().lower()
    if item_type == "message":
        role = str(payload.get("role", "assistant")).strip().lower() or "assistant"
        content = payload.get("content")
        messages: list[_ExtractedMessage] = []
        if isinstance(content, list):
            blocks = cast("list[object]", content)
            for block in blocks:
                if not isinstance(block, dict):
                    text = _text_from_value(block)
                    if text:
                        messages.append(_ExtractedMessage(role=role, content=text))
                    continue
                block_payload = cast("dict[str, object]", block)
                block_type = str(block_payload.get("type", "")).strip().lower()
                if block_type in {"input_text", "output_text", "text"}:
                    text = _text_from_value(block_payload.get("text"))
                    if text:
                        messages.append(_ExtractedMessage(role=role, content=text))
                    continue
                text = _text_from_value(block_payload)
                if text:
                    messages.append(_ExtractedMessage(role=role, content=text))
        else:
            text = _text_from_value(content)
            if text:
                messages.append(_ExtractedMessage(role=role, content=text))
        if not messages:
            fallback = _text_from_value(payload.get("text"))
            if fallback:
                messages.append(_ExtractedMessage(role=role, content=fallback))
        return messages

    if item_type == "function_call":
        name = str(payload.get("name", "tool")).strip() or "tool"
        arguments = _text_from_value(payload.get("arguments"))
        rendered = f"[tool: {name}]"
        if arguments:
            rendered = f"[tool: {name} {_preview(arguments)}]"
        return [_ExtractedMessage(role="assistant", content=rendered)]

    if item_type == "function_call_output":
        output = _text_from_value(payload.get("output"))
        if output:
            return [_ExtractedMessage(role="user", content=f"[tool_result] {output}")]
        return [_ExtractedMessage(role="user", content="[tool_result]")]

    return []


def _extract_codex_exec_item(item: dict[str, object]) -> list[_ExtractedMessage]:
    item_type = str(item.get("type", "")).strip().lower()
    if item_type == "agent_message":
        text = _text_from_value(item.get("text"))
        if not text:
            return []
        return [_ExtractedMessage(role="assistant", content=text)]

    if item_type == "command_execution":
        output = _text_from_value(item.get("aggregated_output"))
        command = _text_from_value(item.get("command"))
        if output:
            return [_ExtractedMessage(role="user", content=f"[tool_result] {output}")]
        if command:
            return [_ExtractedMessage(role="assistant", content=f"[tool: bash {_preview(command)}]")]

    return []


def _extract_from_event(payload: dict[str, object]) -> tuple[list[_ExtractedMessage], bool]:
    event_type = str(payload.get("type", "")).strip().lower()

    # Claude compaction boundary.
    is_boundary = event_type == "system" and str(payload.get("subtype", "")).strip().lower() == "compact_boundary"

    # Claude live progress wrappers embed assistant/user events at data.message.
    if event_type == "progress":
        data = payload.get("data")
        if isinstance(data, dict):
            nested_message = cast("dict[str, object]", data).get("message")
            if isinstance(nested_message, dict):
                nested_messages, nested_boundary = _extract_from_event(cast("dict[str, object]", nested_message))
                return nested_messages, is_boundary or nested_boundary
        return ([], is_boundary)

    if event_type in {"assistant", "user"}:
        role = event_type
        message = payload.get("message")
        if isinstance(message, dict):
            content = cast("dict[str, object]", message).get("content")
            extracted = _extract_claude_content(role, content)
            if extracted:
                return extracted, is_boundary
        fallback_text = _text_from_value(payload.get("tool_use_result"))
        if role == "user" and fallback_text:
            return ([_ExtractedMessage(role="user", content=f"[tool_result] {fallback_text}")], is_boundary)
        return ([], is_boundary)

    # Codex native session file.
    if event_type == "response_item":
        raw_payload = payload.get("payload")
        if isinstance(raw_payload, dict):
            extracted = _extract_codex_response_item(cast("dict[str, object]", raw_payload))
            return (extracted, is_boundary)
        return ([], is_boundary)

    # Codex spawn output style (also valid JSONL input for --file).
    if event_type == "item.completed":
        item = payload.get("item")
        if isinstance(item, dict):
            return (_extract_codex_exec_item(cast("dict[str, object]", item)), is_boundary)
        return ([], is_boundary)

    # Generic fallback for simple role/content payloads.
    role = str(payload.get("role", "")).strip().lower()
    if role in {"assistant", "user", "system"}:
        text = _text_from_value(payload.get("content"))
        if text:
            return ([_ExtractedMessage(role=role, content=text)], is_boundary)

    return ([], is_boundary)


def _parse_session_file(path: Path) -> tuple[list[list[_ExtractedMessage]], int]:
    segments: list[list[_ExtractedMessage]] = [[]]
    total_compactions = 0

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
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
            extracted, boundary = _extract_from_event(payload)
            if boundary:
                total_compactions += 1
                segments.append([])
                continue
            if extracted:
                segments[-1].extend(extracted)

    return segments, total_compactions


def _claude_project_slug(repo_root: Path) -> str:
    return str(repo_root.resolve()).replace("/", "-")


def _resolve_claude_session_path(repo_root: Path, session_id: str) -> Path:
    project_slug = _claude_project_slug(repo_root)
    return Path.home() / ".claude" / "projects" / project_slug / f"{session_id}.jsonl"


def _resolve_codex_session_path(session_id: str) -> Path | None:
    sessions_root = Path.home() / ".codex" / "sessions"
    if not sessions_root.is_dir():
        return None

    matches: list[tuple[float, Path]] = []
    for candidate in sessions_root.rglob(f"rollout-*-{session_id}.jsonl"):
        if _CODEX_FILENAME_RE.match(candidate.name) is None:
            continue
        try:
            modified_at = candidate.stat().st_mtime
        except OSError:
            continue
        matches.append((modified_at, candidate))

    if not matches:
        return None

    matches.sort(key=lambda item: item[0], reverse=True)
    return matches[0][1]


def _extract_session_id_from_path(path: Path) -> str:
    if path.suffix == ".jsonl" and path.stem:
        codex_match = _CODEX_FILENAME_RE.match(path.name)
        if codex_match is not None:
            return codex_match.group("session_id")
        return path.stem
    return path.name


def _resolve_file_target(file_path: str) -> _ResolvedTarget:
    resolved = Path(file_path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Session file '{resolved.as_posix()}' not found")

    harness: str | None = None
    parts = set(resolved.parts)
    if ".claude" in parts:
        harness = "claude"
    elif ".codex" in parts:
        harness = "codex"

    return _ResolvedTarget(
        session_id=_extract_session_id_from_path(resolved),
        harness=harness,
        file_path=resolved,
    )


def _resolve_harness_session_file(
    *,
    repo_root: Path,
    session_id: str,
    harness: str | None,
) -> _ResolvedTarget:
    normalized_harness = (harness or "").strip().lower() or None
    checked_paths: list[str] = []

    if normalized_harness in {None, "claude"}:
        candidate = _resolve_claude_session_path(repo_root, session_id)
        checked_paths.append(candidate.as_posix())
        if candidate.is_file():
            return _ResolvedTarget(session_id=session_id, harness="claude", file_path=candidate)

    if normalized_harness in {None, "codex"}:
        candidate = _resolve_codex_session_path(session_id)
        if candidate is not None:
            return _ResolvedTarget(session_id=session_id, harness="codex", file_path=candidate)
        checked_paths.append((Path.home() / ".codex" / "sessions" / f"**/rollout-*-{session_id}.jsonl").as_posix())

    if normalized_harness is not None:
        raise FileNotFoundError(
            f"Session file for '{session_id}' (harness={normalized_harness}) not found"
        )

    searched = "\n".join(checked_paths)
    raise FileNotFoundError(
        f"Session file for '{session_id}' not found. Checked:\n{searched}"
    )


def _resolve_from_chat_id(
    *,
    repo_root: Path,
    state_root: Path,
    chat_id: str,
) -> _ResolvedTarget:
    harness_session_id = session_store.get_session_harness_id(state_root, chat_id)
    normalized_session_id = (harness_session_id or "").strip()
    if not normalized_session_id:
        raise ValueError(f"Chat '{chat_id}' not found")

    record = session_store.resolve_session_ref(state_root, normalized_session_id)
    harness = record.harness if record is not None else None
    return _resolve_harness_session_file(
        repo_root=repo_root,
        session_id=normalized_session_id,
        harness=harness,
    )


def _resolve_from_spawn_id(
    *,
    repo_root: Path,
    state_root: Path,
    spawn_id: str,
) -> _ResolvedTarget:
    row = read_spawn_row(repo_root, spawn_id)
    if row is None:
        raise ValueError(f"Spawn '{spawn_id}' not found")

    session_id = (row.harness_session_id or "").strip()
    harness = (row.harness or "").strip() or None

    if not session_id and row.chat_id is not None:
        by_chat = session_store.get_session_harness_id(state_root, row.chat_id)
        session_id = (by_chat or "").strip()

    if not session_id:
        raise ValueError(f"Spawn '{spawn_id}' has no associated harness session id")

    if harness is None:
        record = session_store.resolve_session_ref(state_root, session_id)
        if record is not None and record.harness.strip():
            harness = record.harness.strip()

    return _resolve_harness_session_file(
        repo_root=repo_root,
        session_id=session_id,
        harness=harness,
    )


def _resolve_from_session_ref(
    *,
    repo_root: Path,
    state_root: Path,
    session_ref: str,
) -> _ResolvedTarget:
    record = session_store.resolve_session_ref(state_root, session_ref)
    if record is not None:
        session_id = record.harness_session_id.strip() or session_ref
        harness = record.harness.strip() or None
        return _resolve_harness_session_file(
            repo_root=repo_root,
            session_id=session_id,
            harness=harness,
        )

    inferred = infer_harness_from_untracked_session_ref(repo_root, session_ref)
    inferred_name = str(inferred) if inferred is not None else None
    return _resolve_harness_session_file(
        repo_root=repo_root,
        session_id=session_ref,
        harness=inferred_name,
    )


def _resolve_target(payload: SessionLogInput, *, repo_root: Path, state_root: Path) -> _ResolvedTarget:
    if payload.file_path is not None and payload.file_path.strip():
        return _resolve_file_target(payload.file_path)

    ref = payload.ref.strip()
    if not ref:
        raise ValueError("Session reference is required unless --file is provided")

    if ref.startswith("c") and ref[1:].isdigit():
        return _resolve_from_chat_id(repo_root=repo_root, state_root=state_root, chat_id=ref)

    if ref.startswith("p"):
        return _resolve_from_spawn_id(repo_root=repo_root, state_root=state_root, spawn_id=ref)

    return _resolve_from_session_ref(repo_root=repo_root, state_root=state_root, session_ref=ref)


def _select_segment(
    segments: list[list[_ExtractedMessage]],
    *,
    compaction: int,
) -> list[_ExtractedMessage]:
    if compaction < 0:
        raise ValueError("compaction must be >= 0")

    segment_index = len(segments) - 1 - compaction
    if segment_index < 0:
        raise ValueError(
            f"Compaction segment {compaction} out of range (available: 0-{len(segments) - 1})"
        )
    return segments[segment_index]


def _paginate_messages(
    messages: list[_ExtractedMessage],
    *,
    last_n: int | None,
    offset: int,
) -> tuple[list[_ExtractedMessage], int]:
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if last_n is not None and last_n < 0:
        raise ValueError("last_n must be >= 0")

    total = len(messages)
    if offset >= total:
        return ([], total)

    end = total - offset
    if last_n is None:
        start = 0
    else:
        start = max(end - last_n, 0)

    return (messages[start:end], start)


def _showing_window(messages: tuple[SessionLogMessage, ...]) -> str:
    if not messages:
        return "0-0"
    return f"{messages[0].index}-{messages[-1].index}"


def session_log_sync(
    payload: SessionLogInput,
    ctx: RuntimeContext | None = None,
) -> SessionLogOutput:
    _ = ctx
    repo_root, _ = resolve_runtime_root_and_config(payload.repo_root)
    state_root = resolve_state_root(repo_root)

    target = _resolve_target(payload, repo_root=repo_root, state_root=state_root)
    segments, total_compactions = _parse_session_file(target.file_path)
    segment_messages = _select_segment(segments, compaction=payload.compaction)

    selected, start_index = _paginate_messages(
        segment_messages,
        last_n=payload.last_n,
        offset=payload.offset,
    )

    output_messages = tuple(
        SessionLogMessage(index=start_index + idx + 1, role=item.role, content=item.content)
        for idx, item in enumerate(selected)
    )

    return SessionLogOutput(
        session_id=target.session_id,
        total_compactions=total_compactions,
        segment=payload.compaction,
        segment_messages=len(segment_messages),
        showing=_showing_window(output_messages),
        messages=output_messages,
    )


session_log = async_from_sync(session_log_sync)


__all__ = [
    "SessionLogInput",
    "SessionLogMessage",
    "SessionLogOutput",
    "session_log",
    "session_log_sync",
]
