"""File-backed session tracking for `.meridian/.spaces/<space-id>/sessions.jsonl`."""

from __future__ import annotations

import fcntl
import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from meridian.lib.harness.materialize import cleanup_materialized
from meridian.lib.state.id_gen import next_chat_id
from meridian.lib.state.paths import SpacePaths

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
type JSONRow = dict[str, JSONValue]

_SESSION_LOCK_HANDLES: dict[tuple[Path, str], BinaryIO] = {}
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SessionRecord:
    chat_id: str
    session_id: str
    harness: str
    harness_session_id: str
    model: str
    agent: str
    agent_path: str
    skills: tuple[str, ...]
    skill_paths: tuple[str, ...]
    params: tuple[str, ...]
    started_at: str
    stopped_at: str | None


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@contextmanager
def _lock_file(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _append_event(path: Path, payload: JSONRow) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        handle.write("\n")


def _read_events(path: Path) -> list[JSONRow]:
    if not path.exists():
        return []

    rows: list[JSONRow] = []
    with path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            # Self-healing: ignore interrupted trailing append.
            if index == len(lines) - 1:
                continue
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _coerce_params(value: JSONValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
    return tuple(result)


def _coerce_string_or_empty(value: JSONValue | None) -> str:
    if isinstance(value, str):
        return value
    return ""


def _record_from_start_event(event: JSONRow) -> SessionRecord | None:
    chat_id = event.get("chat_id")
    session_id = event.get("session_id")
    harness = event.get("harness")
    harness_session_id = event.get("harness_session_id")
    model = event.get("model")
    started_at = event.get("started_at")
    if not isinstance(chat_id, str):
        return None
    if session_id is None:
        session_id = chat_id
    if not isinstance(session_id, str):
        return None
    if not isinstance(harness, str):
        return None
    if not isinstance(harness_session_id, str):
        return None
    if not isinstance(model, str):
        return None
    if not isinstance(started_at, str):
        return None
    return SessionRecord(
        chat_id=chat_id,
        session_id=session_id,
        harness=harness,
        harness_session_id=harness_session_id,
        model=model,
        agent=_coerce_string_or_empty(event.get("agent")),
        agent_path=_coerce_string_or_empty(event.get("agent_path")),
        skills=_coerce_params(event.get("skills")),
        skill_paths=_coerce_params(event.get("skill_paths")),
        params=_coerce_params(event.get("params")),
        started_at=started_at,
        stopped_at=None,
    )


def _records_by_session(space_dir: Path) -> dict[str, SessionRecord]:
    paths = SpacePaths.from_space_dir(space_dir)
    records: dict[str, SessionRecord] = {}

    for event in _read_events(paths.sessions_jsonl):
        event_type = event.get("event")
        if event_type == "start":
            record = _record_from_start_event(event)
            if record is not None:
                records[record.chat_id] = record
            continue
        if event_type == "stop":
            chat_id = event.get("chat_id")
            if not isinstance(chat_id, str):
                continue
            existing = records.get(chat_id)
            if existing is None:
                continue
            stopped_at = event.get("stopped_at")
            records[chat_id] = SessionRecord(
                chat_id=existing.chat_id,
                session_id=existing.session_id,
                harness=existing.harness,
                harness_session_id=existing.harness_session_id,
                model=existing.model,
                agent=existing.agent,
                agent_path=existing.agent_path,
                skills=existing.skills,
                skill_paths=existing.skill_paths,
                params=existing.params,
                started_at=existing.started_at,
                stopped_at=str(stopped_at) if stopped_at is not None else existing.stopped_at,
            )
            continue
        if event_type == "update":
            chat_id = event.get("chat_id")
            harness_session_id = event.get("harness_session_id")
            if not isinstance(chat_id, str) or not isinstance(harness_session_id, str):
                continue
            existing = records.get(chat_id)
            if existing is None:
                continue
            records[chat_id] = SessionRecord(
                chat_id=existing.chat_id,
                session_id=existing.session_id,
                harness=existing.harness,
                harness_session_id=harness_session_id,
                model=existing.model,
                agent=existing.agent,
                agent_path=existing.agent_path,
                skills=existing.skills,
                skill_paths=existing.skill_paths,
                params=existing.params,
                started_at=existing.started_at,
                stopped_at=existing.stopped_at,
            )
    return records


def _session_sort_key(chat_id: str) -> tuple[int, str]:
    if chat_id.startswith("c") and chat_id[1:].isdigit():
        return (int(chat_id[1:]), chat_id)
    return (10**9, chat_id)


def _session_lock_key(space_dir: Path, chat_id: str) -> tuple[Path, str]:
    return (space_dir.resolve(), chat_id)


def _acquire_session_lock(lock_path: Path) -> BinaryIO:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _release_session_lock(space_dir: Path, chat_id: str) -> None:
    handle = _SESSION_LOCK_HANDLES.pop(_session_lock_key(space_dir, chat_id), None)
    if handle is None:
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def start_session(
    space_dir: Path,
    harness: str,
    harness_session_id: str,
    model: str,
    params: tuple[str, ...] = (),
    agent: str = "",
    agent_path: str = "",
    skills: tuple[str, ...] = (),
    skill_paths: tuple[str, ...] = (),
) -> str:
    """Append a session start event and acquire a lifetime session lock."""

    paths = SpacePaths.from_space_dir(space_dir)
    started_at = _utc_now_iso()

    with _lock_file(paths.sessions_lock):
        chat_id = next_chat_id(space_dir)
        session_id = str(uuid4())
        event: JSONRow = {
            "v": 1,
            "event": "start",
            "chat_id": chat_id,
            "session_id": session_id,
            "harness": harness,
            "harness_session_id": harness_session_id,
            "model": model,
            "agent": agent,
            "agent_path": agent_path,
            "skills": list(skills),
            "skill_paths": list(skill_paths),
            "params": list(params),
            "started_at": started_at,
        }
        _append_event(paths.sessions_jsonl, event)

        lock_path = paths.sessions_dir / f"{chat_id}.lock"
        handle = _acquire_session_lock(lock_path)
        _SESSION_LOCK_HANDLES[_session_lock_key(space_dir, chat_id)] = handle
        return chat_id


def stop_session(space_dir: Path, chat_id: str) -> None:
    """Append a session stop event and release the lifetime session lock."""

    paths = SpacePaths.from_space_dir(space_dir)
    event: JSONRow = {
        "v": 1,
        "event": "stop",
        "chat_id": chat_id,
        "stopped_at": _utc_now_iso(),
    }
    with _lock_file(paths.sessions_lock):
        _append_event(paths.sessions_jsonl, event)
        _release_session_lock(space_dir, chat_id)


def update_session_harness_id(space_dir: Path, chat_id: str, harness_session_id: str) -> None:
    """Append a session update event carrying the resolved harness session ID."""

    paths = SpacePaths.from_space_dir(space_dir)
    event: JSONRow = {
        "v": 1,
        "event": "update",
        "chat_id": chat_id,
        "harness_session_id": harness_session_id,
    }
    with _lock_file(paths.sessions_lock):
        _append_event(paths.sessions_jsonl, event)


def list_active_sessions(space_dir: Path) -> list[str]:
    """Return session IDs with currently held `sessions/<id>.lock` locks."""

    paths = SpacePaths.from_space_dir(space_dir)
    if not paths.sessions_dir.exists():
        return []

    active: list[str] = []
    for lock_path in paths.sessions_dir.glob("*.lock"):
        chat_id = lock_path.stem
        with lock_path.open("a+b") as handle:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                active.append(chat_id)
                continue
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return sorted(active, key=_session_sort_key)


def get_last_session(space_dir: Path) -> SessionRecord | None:
    """Return the most recently started session record in a space."""

    paths = SpacePaths.from_space_dir(space_dir)
    last_session_id: str | None = None
    for event in _read_events(paths.sessions_jsonl):
        if event.get("event") != "start":
            continue
        candidate = event.get("chat_id")
        if isinstance(candidate, str):
            last_session_id = candidate

    if last_session_id is None:
        return None
    return _records_by_session(space_dir).get(last_session_id)


def resolve_session_ref(space_dir: Path, ref: str) -> SessionRecord | None:
    """Resolve session reference by session/chat ID (`cN`) or harness session ID."""

    normalized = ref.strip()
    if not normalized:
        return None

    records = _records_by_session(space_dir)
    direct = records.get(normalized)
    if direct is not None:
        return direct

    for record in records.values():
        if record.session_id == normalized:
            return record

    matches = [
        record for record in records.values() if record.harness_session_id == normalized
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: (item.started_at, _session_sort_key(item.chat_id)))


def get_session_harness_id(space_dir: Path, chat_id: str) -> str | None:
    """Return harness session ID for a meridian chat/session ID."""

    record = _records_by_session(space_dir).get(chat_id)
    if record is None:
        return None
    return record.harness_session_id


def _infer_repo_root_from_space_dir(space_dir: Path) -> Path | None:
    resolved = space_dir.expanduser().resolve()
    if resolved.parent.name != ".spaces":
        return None
    state_root = resolved.parent.parent
    if state_root.name != ".meridian":
        return None
    return state_root.parent


def cleanup_stale_sessions(space_dir: Path, repo_root: Path | None = None) -> list[str]:
    """Stop and remove dead session locks left behind by crashed harnesses."""

    paths = SpacePaths.from_space_dir(space_dir)
    if not paths.sessions_dir.exists():
        return []

    stale: list[tuple[str, Path, BinaryIO]] = []
    for lock_path in paths.sessions_dir.glob("*.lock"):
        chat_id = lock_path.stem
        handle = lock_path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            continue
        stale.append((chat_id, lock_path, handle))

    if not stale:
        return []

    cleaned_ids = sorted((chat_id for chat_id, _, _ in stale), key=_session_sort_key)
    stale_cleanup_scopes: list[tuple[str, str]] = []
    with _lock_file(paths.sessions_lock):
        records = _records_by_session(space_dir)
        stopped_at = _utc_now_iso()
        for chat_id, lock_path, _ in stale:
            existing = records.get(chat_id)
            if existing is not None and existing.stopped_at is None:
                _append_event(
                    paths.sessions_jsonl,
                    {
                        "v": 1,
                        "event": "stop",
                        "chat_id": chat_id,
                        "stopped_at": stopped_at,
                    },
                )
            if existing is not None and existing.harness.strip():
                stale_cleanup_scopes.append((existing.harness.strip(), chat_id))
            lock_path.unlink(missing_ok=True)

    for chat_id, _, handle in stale:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        _SESSION_LOCK_HANDLES.pop(_session_lock_key(space_dir, chat_id), None)

    cleanup_root = (
        repo_root.expanduser().resolve()
        if repo_root is not None
        else _infer_repo_root_from_space_dir(space_dir)
    )
    if cleanup_root is not None:
        for harness_id, chat_id in sorted(set(stale_cleanup_scopes)):
            try:
                cleanup_materialized(harness_id, cleanup_root, chat_id)
            except Exception:
                logger.warning(
                    "Failed to cleanup stale-session materialized resources.",
                    harness_id=harness_id,
                    chat_id=chat_id,
                    exc_info=True,
                )

    return cleaned_ids
