"""File-backed session tracking for `.meridian/.spaces/<space-id>/sessions.jsonl`."""


import fcntl
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO, Literal, NamedTuple, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from meridian.lib.state.spawn_store import next_chat_id
from meridian.lib.state.paths import SpacePaths

_SESSION_LOCK_HANDLES: dict[tuple[Path, str], BinaryIO] = {}


class SessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    chat_id: str
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


type SessionEvent = SessionStartEvent | SessionStopEvent | SessionUpdateEvent
type MaterializedCleanupScope = tuple[str, str]


class StaleSessionCleanup(NamedTuple):
    cleaned_ids: tuple[str, ...]
    materialized_scopes: tuple[MaterializedCleanupScope, ...]


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


def _append_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        handle.write("\n")


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


def _read_events(path: Path) -> list[SessionEvent]:
    if not path.exists():
        return []

    rows: list[SessionEvent] = []
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
        if not isinstance(payload, dict):
            continue
        parsed = _parse_event(cast("dict[str, Any]", payload))
        if parsed is not None:
            rows.append(parsed)
    return rows


def _record_from_start_event(event: SessionStartEvent) -> SessionRecord:
    return SessionRecord(
        chat_id=event.chat_id,
        harness=event.harness,
        harness_session_id=event.harness_session_id,
        model=event.model,
        agent=event.agent,
        agent_path=event.agent_path,
        skills=event.skills,
        skill_paths=event.skill_paths,
        params=event.params,
        started_at=event.started_at,
        stopped_at=None,
    )


def _records_by_session(space_dir: Path) -> dict[str, SessionRecord]:
    paths = SpacePaths.from_space_dir(space_dir)
    records: dict[str, SessionRecord] = {}

    for event in _read_events(paths.sessions_jsonl):
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
        records[event.chat_id] = existing.model_copy(
            update={"harness_session_id": event.harness_session_id}
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
        event = SessionStartEvent(
            chat_id=chat_id,
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
        _append_event(paths.sessions_jsonl, event.model_dump())

        lock_path = paths.sessions_dir / f"{chat_id}.lock"
        handle = _acquire_session_lock(lock_path)
        _SESSION_LOCK_HANDLES[_session_lock_key(space_dir, chat_id)] = handle
        return chat_id


def stop_session(space_dir: Path, chat_id: str) -> None:
    """Append a session stop event and release the lifetime session lock."""

    paths = SpacePaths.from_space_dir(space_dir)
    event = SessionStopEvent(chat_id=chat_id, stopped_at=_utc_now_iso())
    with _lock_file(paths.sessions_lock):
        _append_event(paths.sessions_jsonl, event.model_dump(exclude_none=True))
        _release_session_lock(space_dir, chat_id)


def update_session_harness_id(space_dir: Path, chat_id: str, harness_session_id: str) -> None:
    """Append a session update event carrying the resolved harness session ID."""

    paths = SpacePaths.from_space_dir(space_dir)
    event = SessionUpdateEvent(chat_id=chat_id, harness_session_id=harness_session_id)
    with _lock_file(paths.sessions_lock):
        _append_event(paths.sessions_jsonl, event.model_dump())


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
        if not isinstance(event, SessionStartEvent):
            continue
        last_session_id = event.chat_id

    if last_session_id is None:
        return None
    return _records_by_session(space_dir).get(last_session_id)


def resolve_session_ref(space_dir: Path, ref: str) -> SessionRecord | None:
    """Resolve session reference by harness session ID."""

    normalized = ref.strip()
    if not normalized:
        return None

    records = _records_by_session(space_dir)
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


def collect_active_chat_ids(repo_root: Path) -> frozenset[str] | None:
    """Collect chat IDs from all spaces with start events that lack a stop event."""

    from meridian.lib.state.paths import resolve_all_spaces_dir

    try:
        spaces_dir = resolve_all_spaces_dir(repo_root)
        if not spaces_dir.is_dir():
            return frozenset()

        active_ids: set[str] = set()
        for space_dir in spaces_dir.iterdir():
            if not space_dir.is_dir():
                continue
            sessions_file = space_dir / "sessions.jsonl"
            if not sessions_file.is_file():
                continue

            try:
                started: set[str] = set()
                stopped: set[str] = set()
                for event in _read_events(sessions_file):
                    if isinstance(event, SessionStartEvent):
                        started.add(event.chat_id)
                        continue
                    if isinstance(event, SessionStopEvent):
                        stopped.add(event.chat_id)

                active_ids.update(started - stopped)
            except OSError:
                continue

        return frozenset(active_ids)
    except OSError:
        return None


def cleanup_stale_sessions(space_dir: Path) -> StaleSessionCleanup:
    """Stop and remove dead session locks left behind by crashed harnesses."""

    paths = SpacePaths.from_space_dir(space_dir)
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
    stale_cleanup_scopes: list[tuple[str, str]] = []
    with _lock_file(paths.sessions_lock):
        records = _records_by_session(space_dir)
        stopped_at = _utc_now_iso()
        for chat_id, lock_path, _ in stale:
            existing = records.get(chat_id)
            if existing is not None and existing.stopped_at is None:
                _append_event(
                    paths.sessions_jsonl,
                    SessionStopEvent(chat_id=chat_id, stopped_at=stopped_at).model_dump(
                        exclude_none=True
                    ),
                )
            if existing is not None and existing.harness.strip():
                stale_cleanup_scopes.append((existing.harness.strip(), chat_id))
            lock_path.unlink(missing_ok=True)

    for chat_id, _, handle in stale:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
        _SESSION_LOCK_HANDLES.pop(_session_lock_key(space_dir, chat_id), None)

    return StaleSessionCleanup(
        cleaned_ids=tuple(cleaned_ids),
        materialized_scopes=tuple(sorted(set(stale_cleanup_scopes))),
    )
