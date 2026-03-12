"""File-backed session tracking for a Meridian state root's `sessions.jsonl`."""


import fcntl
from pathlib import Path
from typing import Any, BinaryIO, Literal, NamedTuple

from pydantic import BaseModel, ConfigDict, ValidationError

from meridian.lib.state.event_store import append_event, lock_file, read_events, utc_now_iso
from meridian.lib.state.spawn_store import next_chat_id
from meridian.lib.state.paths import StateRootPaths

_SESSION_LOCK_HANDLES: dict[tuple[Path, str], BinaryIO] = {}


class SessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    chat_id: str
    harness: str
    harness_session_id: str
    harness_session_ids: tuple[str, ...]
    model: str
    agent: str
    agent_path: str
    skills: tuple[str, ...]
    skill_paths: tuple[str, ...]
    params: tuple[str, ...]
    started_at: str
    stopped_at: str | None
    active_work_id: str | None = None


class SessionStartEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["start"] = "start"
    chat_id: str
    harness: str
    harness_session_id: str
    model: str
    agent: str = ""
    agent_path: str = ""
    skills: tuple[str, ...] = ()
    skill_paths: tuple[str, ...] = ()
    params: tuple[str, ...] = ()
    started_at: str


class SessionStopEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["stop"] = "stop"
    chat_id: str
    stopped_at: str | None = None


class SessionUpdateEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["update"] = "update"
    chat_id: str
    harness_session_id: str
    active_work_id: str | None = None


type SessionEvent = SessionStartEvent | SessionStopEvent | SessionUpdateEvent
type MaterializedCleanupScope = str


class StaleSessionCleanup(NamedTuple):
    cleaned_ids: tuple[str, ...]
    materialized_scopes: tuple[MaterializedCleanupScope, ...]


def _parse_event(payload: dict[str, Any]) -> SessionEvent | None:
    event_type = payload.get("event")
    try:
        if event_type == "start":
            return SessionStartEvent.model_validate(payload)
        if event_type == "stop":
            return SessionStopEvent.model_validate(payload)
        if event_type == "update":
            return SessionUpdateEvent.model_validate(payload)
    except ValidationError:
        return None
    return None


def _record_from_start_event(event: SessionStartEvent) -> SessionRecord:
    return SessionRecord(
        chat_id=event.chat_id,
        harness=event.harness,
        harness_session_id=event.harness_session_id,
        harness_session_ids=(event.harness_session_id,),
        model=event.model,
        agent=event.agent,
        agent_path=event.agent_path,
        skills=event.skills,
        skill_paths=event.skill_paths,
        params=event.params,
        started_at=event.started_at,
        stopped_at=None,
        active_work_id=None,
    )


def _records_by_session(state_root: Path) -> dict[str, SessionRecord]:
    paths = StateRootPaths.from_root_dir(state_root)
    records: dict[str, SessionRecord] = {}

    for event in read_events(paths.sessions_jsonl, _parse_event):
        if isinstance(event, SessionStartEvent):
            record = _record_from_start_event(event)
            records[record.chat_id] = record
            continue
        if isinstance(event, SessionStopEvent):
            existing = records.get(event.chat_id)
            if existing is None:
                continue
            records[event.chat_id] = existing.model_copy(
                update={
                    "stopped_at": event.stopped_at if event.stopped_at is not None else existing.stopped_at
                }
            )
            continue
        existing = records.get(event.chat_id)
        if existing is None:
            continue
        session_ids = existing.harness_session_ids
        harness_session_id = existing.harness_session_id
        updated_work_id = existing.active_work_id
        normalized_harness_session_id = event.harness_session_id.strip()
        if normalized_harness_session_id:
            if normalized_harness_session_id not in session_ids:
                session_ids = (*session_ids, normalized_harness_session_id)
            harness_session_id = normalized_harness_session_id
        if event.active_work_id is not None:
            normalized_work_id = event.active_work_id.strip()
            updated_work_id = normalized_work_id or None
        records[event.chat_id] = existing.model_copy(
            update={
                "harness_session_id": harness_session_id,
                "harness_session_ids": session_ids,
                "active_work_id": updated_work_id,
            }
        )
    return records


def _session_sort_key(chat_id: str) -> tuple[int, str]:
    if chat_id.startswith("c") and chat_id[1:].isdigit():
        return (int(chat_id[1:]), chat_id)
    return (10**9, chat_id)


def _session_lock_key(state_root: Path, chat_id: str) -> tuple[Path, str]:
    return (state_root.resolve(), chat_id)


def _acquire_session_lock(lock_path: Path) -> BinaryIO:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a+b")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _release_session_lock(state_root: Path, chat_id: str) -> None:
    handle = _SESSION_LOCK_HANDLES.pop(_session_lock_key(state_root, chat_id), None)
    if handle is None:
        return
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def start_session(
    state_root: Path,
    harness: str,
    harness_session_id: str,
    model: str,
    chat_id: str | None = None,
    params: tuple[str, ...] = (),
    agent: str = "",
    agent_path: str = "",
    skills: tuple[str, ...] = (),
    skill_paths: tuple[str, ...] = (),
) -> str:
    """Append a session start event and acquire a lifetime session lock."""

    paths = StateRootPaths.from_root_dir(state_root)
    started_at = utc_now_iso()

    with lock_file(paths.sessions_lock):
        resolved_chat_id = chat_id.strip() if chat_id is not None else ""
        if not resolved_chat_id:
            resolved_chat_id = next_chat_id(state_root)
        event = SessionStartEvent(
            chat_id=resolved_chat_id,
            harness=harness,
            harness_session_id=harness_session_id,
            model=model,
            agent=agent,
            agent_path=agent_path,
            skills=skills,
            skill_paths=skill_paths,
            params=params,
            started_at=started_at,
        )
        append_event(paths.sessions_jsonl, paths.sessions_lock, event, store_name="session")

        lock_path = paths.sessions_dir / f"{resolved_chat_id}.lock"
        handle = _acquire_session_lock(lock_path)
        _SESSION_LOCK_HANDLES[_session_lock_key(state_root, resolved_chat_id)] = handle
        return resolved_chat_id


def stop_session(state_root: Path, chat_id: str) -> None:
    """Append a session stop event and release the lifetime session lock."""

    paths = StateRootPaths.from_root_dir(state_root)
    event = SessionStopEvent(chat_id=chat_id, stopped_at=utc_now_iso())
    with lock_file(paths.sessions_lock):
        append_event(
            paths.sessions_jsonl,
            paths.sessions_lock,
            event,
            store_name="session",
            exclude_none=True,
        )
        _release_session_lock(state_root, chat_id)


def update_session_harness_id(state_root: Path, chat_id: str, harness_session_id: str) -> None:
    """Append a session update event carrying the resolved harness session ID."""

    paths = StateRootPaths.from_root_dir(state_root)
    event = SessionUpdateEvent(chat_id=chat_id, harness_session_id=harness_session_id)
    append_event(
        paths.sessions_jsonl,
        paths.sessions_lock,
        event,
        store_name="session",
        exclude_none=True,
    )


def update_session_work_id(state_root: Path, chat_id: str, work_id: str | None) -> None:
    """Set or clear the active work item for a session."""

    paths = StateRootPaths.from_root_dir(state_root)
    normalized_work_id = work_id.strip() if work_id is not None else ""
    event = SessionUpdateEvent(
        chat_id=chat_id,
        harness_session_id="",
        active_work_id=normalized_work_id,
    )
    append_event(
        paths.sessions_jsonl,
        paths.sessions_lock,
        event,
        store_name="session",
        exclude_none=True,
    )


def list_active_sessions(state_root: Path) -> list[str]:
    """Return session IDs with currently held `sessions/<id>.lock` locks."""

    paths = StateRootPaths.from_root_dir(state_root)
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


def get_last_session(state_root: Path) -> SessionRecord | None:
    """Return the most recently started session record in a state root."""

    paths = StateRootPaths.from_root_dir(state_root)
    last_session_id: str | None = None
    for event in read_events(paths.sessions_jsonl, _parse_event):
        if not isinstance(event, SessionStartEvent):
            continue
        last_session_id = event.chat_id

    if last_session_id is None:
        return None
    return _records_by_session(state_root).get(last_session_id)


def resolve_session_ref(state_root: Path, ref: str) -> SessionRecord | None:
    """Resolve session reference by harness session ID."""

    normalized = ref.strip()
    if not normalized:
        return None

    records = _records_by_session(state_root)
    matches = [
        record for record in records.values() if normalized in record.harness_session_ids
    ]
    if not matches:
        return None
    return max(matches, key=lambda item: (item.started_at, _session_sort_key(item.chat_id)))


def get_session_active_work_id(state_root: Path, chat_id: str) -> str | None:
    """Return the active work item ID for a session, or None."""

    record = _records_by_session(state_root).get(chat_id)
    if record is None:
        return None
    return record.active_work_id


def get_session_harness_id(state_root: Path, chat_id: str) -> str | None:
    """Return harness session ID for a meridian chat/session ID."""

    record = _records_by_session(state_root).get(chat_id)
    if record is None:
        return None
    return record.harness_session_id


def get_session_harness_ids(state_root: Path, chat_id: str) -> tuple[str, ...]:
    """Return all harness session IDs observed for a meridian chat/session ID."""

    record = _records_by_session(state_root).get(chat_id)
    if record is None:
        return ()
    return record.harness_session_ids


def collect_active_chat_ids(repo_root: Path) -> frozenset[str] | None:
    """Collect chat IDs with start events that lack a stop event."""

    from meridian.lib.state.paths import resolve_state_paths

    try:
        state_root = resolve_state_paths(repo_root).root_dir
        sessions_file = state_root / "sessions.jsonl"
        if not sessions_file.is_file():
            return frozenset()

        started: set[str] = set()
        stopped: set[str] = set()
        for event in read_events(sessions_file, _parse_event):
            if isinstance(event, SessionStartEvent):
                started.add(event.chat_id)
            elif isinstance(event, SessionStopEvent):
                stopped.add(event.chat_id)
        return frozenset(started - stopped)
    except OSError:
        return None


def cleanup_stale_sessions(state_root: Path) -> StaleSessionCleanup:
    """Stop and remove dead session locks left behind by crashed harnesses."""

    paths = StateRootPaths.from_root_dir(state_root)
    if not paths.sessions_dir.exists():
        return StaleSessionCleanup(cleaned_ids=(), materialized_scopes=())

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
        return StaleSessionCleanup(cleaned_ids=(), materialized_scopes=())

    cleaned_ids = sorted((chat_id for chat_id, _, _ in stale), key=_session_sort_key)
    stale_cleanup_scopes: list[str] = []
    with lock_file(paths.sessions_lock):
        records = _records_by_session(state_root)
        stopped_at = utc_now_iso()
        for chat_id, lock_path, _ in stale:
            existing = records.get(chat_id)
            if existing is not None and existing.stopped_at is None:
                append_event(
                    paths.sessions_jsonl,
                    paths.sessions_lock,
                    SessionStopEvent(chat_id=chat_id, stopped_at=stopped_at),
                    store_name="session",
                    exclude_none=True,
                )
            if existing is not None and existing.harness.strip():
                stale_cleanup_scopes.append(existing.harness.strip())
            lock_path.unlink(missing_ok=True)

    for chat_id, _, handle in stale:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        _SESSION_LOCK_HANDLES.pop(_session_lock_key(state_root, chat_id), None)

    return StaleSessionCleanup(
        cleaned_ids=tuple(cleaned_ids),
        materialized_scopes=tuple(sorted(set(stale_cleanup_scopes))),
    )
