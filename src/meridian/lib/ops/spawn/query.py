"""Spawn state query and shaping helpers backed by `spawns.jsonl`."""


import json
import re
from pathlib import Path
from typing import cast

from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir, resolve_state_paths

from ..runtime import require_space_id
from .models import SpawnDetailOutput

_SPAWN_REFERENCE_STATUS_FILTERS: dict[str, tuple[str, ...] | None] = {
    "@latest": None,
    "@last-failed": ("failed",),
    "@last-completed": ("succeeded",),
}
_RUNNING_LOG_MESSAGE_LIMIT = 120
_ASSISTANT_ROLE_MARKER_RE = re.compile(r"^(assistant|codex)$", re.IGNORECASE)
_LOG_ROLE_MARKER_RE = re.compile(r"^(user|assistant|codex|exec)$", re.IGNORECASE)


def _space_dir(
    repo_root: Path,
    space: str | None = None,
    *,
    space_id: str | None = None,
) -> Path:
    return resolve_space_dir(repo_root, require_space_id(space, space_id=space_id))


def _select_latest_spawn_id(
    repo_root: Path,
    *,
    statuses: tuple[str, ...] | None,
    space: str | None = None,
    space_id: str | None = None,
) -> str | None:
    spawns = spawn_store.list_spawns(_space_dir(repo_root, space, space_id=space_id))
    if statuses is not None:
        wanted = set(statuses)
        spawns = [item for item in spawns if item.status in wanted]
    if not spawns:
        return None
    return spawns[-1].id


def resolve_spawn_reference(
    repo_root: Path,
    ref: str,
    space: str | None = None,
    *,
    space_id: str | None = None,
) -> str:
    normalized = ref.strip()
    if not normalized:
        raise ValueError("spawn_id is required")
    if not normalized.startswith("@"):
        return normalized

    status_filter = _SPAWN_REFERENCE_STATUS_FILTERS.get(normalized)
    if normalized not in _SPAWN_REFERENCE_STATUS_FILTERS:
        supported = ", ".join(sorted(_SPAWN_REFERENCE_STATUS_FILTERS))
        raise ValueError(f"Unknown spawn reference '{normalized}'. Supported references: {supported}")

    resolved = _select_latest_spawn_id(
        repo_root,
        statuses=status_filter,
        space=space,
        space_id=space_id,
    )
    if resolved is None:
        raise ValueError(f"No spawns found for reference '{normalized}'")
    return resolved


def resolve_spawn_references(
    repo_root: Path,
    refs: tuple[str, ...],
    space: str | None = None,
    *,
    space_id: str | None = None,
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            resolve_spawn_reference(repo_root, ref, space, space_id=space_id) for ref in refs
        )
    )


def read_spawn_row(
    repo_root: Path,
    spawn_id: str,
    space: str | None = None,
    *,
    space_id: str | None = None,
) -> spawn_store.SpawnRecord | None:
    return spawn_store.get_spawn(_space_dir(repo_root, space, space_id=space_id), spawn_id)


def read_report_text(
    repo_root: Path,
    spawn_id: str,
    space: str | None = None,
    *,
    space_id: str | None = None,
) -> tuple[str | None, str | None]:
    report_path = _space_dir(repo_root, space, space_id=space_id) / "spawns" / spawn_id / "report.md"
    if not report_path.is_file():
        return None, None
    text = report_path.read_text(encoding="utf-8", errors="ignore").strip() or None
    return report_path.as_posix(), text


def _truncate_log_message(value: str, *, max_chars: int = _RUNNING_LOG_MESSAGE_LIMIT) -> str:
    compact = " ".join(value.split()).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3].rstrip()}..."


def _log_text_from_value(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [_log_text_from_value(item) for item in cast("list[object]", value)]
        return " ".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        payload = cast("dict[str, object]", value)
        parts: list[str] = []
        for key in ("text", "message", "output", "content"):
            if key in payload:
                text = _log_text_from_value(payload[key])
                if text:
                    parts.append(text)
        return " ".join(parts).strip()
    return ""


def _assistant_texts(payload: object) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        obj = cast("dict[str, object]", payload)
        role = str(obj.get("role", "")).lower()
        event_type = str(obj.get("type", obj.get("event", ""))).lower()
        category = str(obj.get("category", "")).lower()
        if role == "assistant" or "assistant" in event_type or category == "assistant":
            text = _log_text_from_value(obj)
            if text:
                found.append(text)
        for nested in obj.values():
            found.extend(_assistant_texts(nested))
        return found
    if isinstance(payload, list):
        for item in cast("list[object]", payload):
            found.extend(_assistant_texts(item))
    return found


def _extract_last_assistant_message(stderr_text: str) -> str | None:
    last_message: str | None = None
    pending_assistant_lines: list[str] | None = None

    def _flush_pending_assistant() -> None:
        nonlocal last_message, pending_assistant_lines
        if pending_assistant_lines is None:
            return
        candidate = " ".join(line for line in pending_assistant_lines if line).strip()
        if candidate:
            last_message = candidate
        pending_assistant_lines = None

    for line in stderr_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if _ASSISTANT_ROLE_MARKER_RE.fullmatch(stripped):
            _flush_pending_assistant()
            pending_assistant_lines = []
            continue

        if pending_assistant_lines is not None:
            if _LOG_ROLE_MARKER_RE.fullmatch(stripped):
                _flush_pending_assistant()
                if _ASSISTANT_ROLE_MARKER_RE.fullmatch(stripped):
                    pending_assistant_lines = []
                continue
            pending_assistant_lines.append(stripped)
            continue

        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        assistant_texts = _assistant_texts(payload)
        if assistant_texts:
            last_message = assistant_texts[-1]
    _flush_pending_assistant()
    if last_message is None:
        return None
    return _truncate_log_message(last_message)


def _read_running_log_details(
    repo_root: Path,
    spawn_id: str,
    space: str | None = None,
    *,
    space_id: str | None = None,
) -> tuple[str, str | None]:
    stderr_path = _space_dir(repo_root, space, space_id=space_id) / "spawns" / spawn_id / "stderr.log"
    if not stderr_path.is_file():
        return stderr_path.as_posix(), None
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="ignore")
    return stderr_path.as_posix(), _extract_last_assistant_message(stderr_text)


def _read_files_touched(
    repo_root: Path,
    spawn_id: str,
    space: str | None = None,
    *,
    space_id: str | None = None,
) -> tuple[str, ...]:
    from meridian.lib.launch.files_touched import extract_files_touched
    from meridian.lib.state.artifact_store import LocalStore
    from meridian.lib.core.types import SpawnId

    artifacts = LocalStore(root_dir=resolve_state_paths(repo_root).artifacts_dir)
    _ = (space, space_id)
    return extract_files_touched(artifacts, SpawnId(spawn_id))


def detail_from_row(
    *,
    repo_root: Path,
    row: spawn_store.SpawnRecord,
    report: bool,
    include_files: bool,
    space_id: str | None = None,
    context_space_id: str | None = None,
) -> SpawnDetailOutput:
    resolved_space_id = str(require_space_id(space_id, space_id=context_space_id))
    report_path, report_text = read_report_text(
        repo_root,
        row.id,
        resolved_space_id,
        space_id=context_space_id,
    )
    report_summary = report_text[:500] if report_text else None

    files_touched: tuple[str, ...] | None = None
    if include_files:
        files_touched = _read_files_touched(
            repo_root,
            row.id,
            resolved_space_id,
            space_id=context_space_id,
        )

    last_message: str | None = None
    log_path: str | None = None
    if row.status == "running":
        log_path, last_message = _read_running_log_details(
            repo_root,
            row.id,
            resolved_space_id,
            space_id=context_space_id,
        )

    return SpawnDetailOutput(
        spawn_id=row.id,
        status=row.status,
        model=row.model or "",
        harness=row.harness or "",
        space_id=resolved_space_id,
        started_at=row.started_at or "",
        finished_at=row.finished_at,
        duration_secs=row.duration_secs,
        exit_code=row.exit_code,
        failure_reason=row.error,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        cost_usd=row.total_cost_usd,
        report_path=report_path,
        report_summary=report_summary,
        report=report_text if report else None,
        files_touched=files_touched,
        last_message=last_message,
        log_path=log_path,
    )


__all__ = [
    "detail_from_row",
    "read_report_text",
    "read_spawn_row",
    "resolve_spawn_reference",
    "resolve_spawn_references",
]
