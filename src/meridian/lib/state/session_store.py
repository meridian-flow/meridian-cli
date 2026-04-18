"""File-backed session tracking for a Meridian state root's `sessions.jsonl`."""

import json
import os
import uuid
from importlib import import_module
from pathlib import Path
from typing import Any, BinaryIO, Literal, NamedTuple, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from meridian.lib.platform import IS_WINDOWS
from meridian.lib.platform.locking import lock_file
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.event_store import append_event, read_events, utc_now_iso
from meridian.lib.state.paths import StateRootPaths

_SESSION_LOCK_HANDLES: dict[tuple[Path, str], tuple[BinaryIO, str]] = {}


class _DeferredUnixModule:
    """Lazy module proxy so Unix-only modules load only on demand."""

    def __init__(self, module_name: str) -> None:
        self._module_name = module_name
        self._module: Any | None = None

    def _resolve(self) -> Any:
        if self._module is None:
            self._module = import_module(self._module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)


fcntl = _DeferredUnixModule("fcntl")


class SessionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    chat_id: str
    kind: Literal["primary", "spawn"]
    harness: str
    harness_session_id: str
    execution_cwd: str | None = None
    harness_session_ids: tuple[str, ...]
    model: str
    agent: str
    agent_path: str
    skills: tuple[str, ...]
    skill_paths: tuple[str, ...]
    params: tuple[str, ...]
    started_at: str
    stopped_at: str | None
    session_instance_id: str = ""
    active_work_id: str | None = None
    forked_from_chat_id: str | None = None


class SessionStartEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["start"] = "start"
    chat_id: str
    kind: Literal["primary", "spawn"] = "spawn"
    harness: str
    harness_session_id: str
    execution_cwd: str | None = None
    model: str
    agent: str = ""
    agent_path: str = ""
    skills: tuple[str, ...] = ()
    skill_paths: tuple[str, ...] = ()
    params: tuple[str, ...] = ()
    session_instance_id: str = ""
    started_at: str
    forked_from_chat_id: str | None = None


class SessionStopEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["stop"] = "stop"
    chat_id: str
    session_instance_id: str = ""
    stopped_at: str | None = None


class SessionUpdateEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["update"] = "update"
    chat_id: str
    harness_session_id: str
    session_instance_id: str = ""
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
        kind=event.kind,
        harness=event.harness,
        harness_session_id=event.harness_session_id,
        execution_cwd=event.execution_cwd,
        harness_session_ids=(event.harness_session_id,),
        model=event.model,
        agent=event.agent,
        agent_path=event.agent_path,
        skills=event.skills,
        skill_paths=event.skill_paths,
        params=event.params,
        started_at=event.started_at,
        stopped_at=None,
        session_instance_id=event.session_instance_id,
        active_work_id=None,
        forked_from_chat_id=event.forked_from_chat_id,
    )


def _session_lease_path(paths: StateRootPaths, chat_id: str) -> Path:
    return paths.sessions_dir / f"{chat_id}.lease.json"


def _normalized_generation(generation: str) -> str:
    return generation.strip()


def _generation_matches(expected: str, actual: str) -> bool:
    normalized_expected = _normalized_generation(expected)
    normalized_actual = _normalized_generation(actual)
    if not normalized_expected and not normalized_actual:
        return True
    return normalized_expected == normalized_actual


def _read_session_lease(paths: StateRootPaths, chat_id: str) -> tuple[bool, str]:
    lease_path = _session_lease_path(paths, chat_id)
    if not lease_path.is_file():
        return (False, "")
    try:
        payload = json.loads(lease_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return (False, "")
    if not isinstance(payload, dict):
        return (False, "")
    payload_dict = cast("dict[str, Any]", payload)
    generation = payload_dict.get("session_instance_id")
    if isinstance(generation, str):
        return (True, generation)
    return (True, "")


def _write_session_lease(paths: StateRootPaths, chat_id: str, session_instance_id: str) -> None:
    payload = {
        "chat_id": chat_id,
        "owner_pid": os.getpid(),
        "session_instance_id": session_instance_id,
    }
    atomic_write_text(
        _session_lease_path(paths, chat_id),
        json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n",
    )


def _session_instance_for_event(paths: StateRootPaths, state_root: Path, chat_id: str) -> str:
    held = _SESSION_LOCK_HANDLES.get(_session_lock_key(state_root, chat_id))
    if held is not None:
        _, session_instance_id = held
        return session_instance_id

    _, lease_session_instance_id = _read_session_lease(paths, chat_id)
    if lease_session_instance_id.strip():
        return lease_session_instance_id

    record = _records_by_session(state_root).get(chat_id)
    if record is None:
        return ""
    return record.session_instance_id


def _read_session_counter(paths: StateRootPaths) -> int:
    if not paths.session_id_counter.is_file():
        return 0
    try:
        return int(paths.session_id_counter.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def _seed_counter_from_events(paths: StateRootPaths) -> int:
    """Scan sessions.jsonl for the highest c<N> chat ID to seed the counter on upgrade."""

    max_id = 0
    if not paths.sessions_jsonl.is_file():
        return max_id
    for event in read_events(paths.sessions_jsonl, _parse_event):
        if not isinstance(event, SessionStartEvent):
            continue
        chat_id = event.chat_id
        if chat_id.startswith("c") and chat_id[1:].isdigit():
            max_id = max(max_id, int(chat_id[1:]))
    return max_id


def reserve_chat_id(state_root: Path) -> str:
    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.session_id_counter_flock):
        current = _read_session_counter(paths)
        if current == 0 and not paths.session_id_counter.is_file():
            current = _seed_counter_from_events(paths)
        next_value = current + 1
        atomic_write_text(paths.session_id_counter, f"{next_value}\n")
        return f"c{next_value}"


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
            if not _generation_matches(existing.session_instance_id, event.session_instance_id):
                continue
            records[event.chat_id] = existing.model_copy(
                update={
                    "stopped_at": event.stopped_at
                    if event.stopped_at is not None
                    else existing.stopped_at,
                    "session_instance_id": event.session_instance_id
                    or existing.session_instance_id,
                }
            )
            continue
        existing = records.get(event.chat_id)
        if existing is None:
            continue
        if not _generation_matches(existing.session_instance_id, event.session_instance_id):
            continue
        session_ids = existing.harness_session_ids
        harness_session_id = existing.harness_session_id
        updated_work_id = existing.active_work_id
        session_instance_id = existing.session_instance_id
        normalized_harness_session_id = event.harness_session_id.strip()
        if normalized_harness_session_id:
            if normalized_harness_session_id not in session_ids:
                session_ids = (*session_ids, normalized_harness_session_id)
            harness_session_id = normalized_harness_session_id
        if event.session_instance_id.strip():
            session_instance_id = event.session_instance_id
        if event.active_work_id is not None:
            normalized_work_id = event.active_work_id.strip()
            updated_work_id = normalized_work_id or None
        records[event.chat_id] = existing.model_copy(
            update={
                "harness_session_id": harness_session_id,
                "harness_session_ids": session_ids,
                "session_instance_id": session_instance_id,
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
    if IS_WINDOWS:
        return _win_acquire_session_lock(lock_path)
    return _posix_acquire_session_lock(lock_path)


def _lock_handle_matches_path(handle: BinaryIO, lock_path: Path) -> bool:
    stat_handle = os.fstat(handle.fileno())
    stat_path = lock_path.stat()
    return stat_handle.st_ino == stat_path.st_ino and stat_handle.st_dev == stat_path.st_dev


def _posix_acquire_session_lock(lock_path: Path) -> BinaryIO:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        handle = lock_path.open("a+b")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            if _lock_handle_matches_path(handle, lock_path):
                return handle
        except FileNotFoundError:
            pass
        _posix_release_session_lock(handle)
        handle.close()


def _win_acquire_session_lock(lock_path: Path) -> BinaryIO:
    import msvcrt as _msvcrt

    msvcrt = cast("Any", _msvcrt)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    while True:
        handle = lock_path.open("a+b")
        _ensure_windows_lock_region(handle)
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        try:
            if _lock_handle_matches_path(handle, lock_path):
                return handle
        except FileNotFoundError:
            pass
        _win_release_session_lock(handle)
        handle.close()


def _release_session_lock_handle(handle: BinaryIO) -> None:
    if IS_WINDOWS:
        _win_release_session_lock(handle)
    else:
        _posix_release_session_lock(handle)


def _posix_release_session_lock(handle: BinaryIO) -> None:
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _win_release_session_lock(handle: BinaryIO) -> None:
    import msvcrt as _msvcrt

    msvcrt = cast("Any", _msvcrt)
    handle.seek(0)
    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _ensure_windows_lock_region(handle: BinaryIO) -> None:
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"\0")
        handle.flush()
        os.fsync(handle.fileno())
    handle.seek(0)


def _try_lock_nonblocking(handle: BinaryIO) -> bool:
    if IS_WINDOWS:
        return _win_try_lock_nonblocking(handle)
    return _posix_try_lock_nonblocking(handle)


def _posix_try_lock_nonblocking(handle: BinaryIO) -> bool:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return False
    return True


def _win_try_lock_nonblocking(handle: BinaryIO) -> bool:
    import msvcrt as _msvcrt

    msvcrt = cast("Any", _msvcrt)
    _ensure_windows_lock_region(handle)
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return False
    return True


def _release_session_lock(state_root: Path, chat_id: str) -> None:
    lock_data = _SESSION_LOCK_HANDLES.pop(_session_lock_key(state_root, chat_id), None)
    if lock_data is None:
        return
    handle, _ = lock_data
    _release_session_lock_handle(handle)
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
    forked_from_chat_id: str | None = None,
    execution_cwd: str | None = None,
    kind: Literal["primary", "spawn"] = "spawn",
) -> str:
    """Append a session start event and acquire a lifetime session lock."""

    paths = StateRootPaths.from_root_dir(state_root)
    started_at = utc_now_iso()
    resolved_chat_id = chat_id.strip() if chat_id is not None else ""
    if not resolved_chat_id:
        resolved_chat_id = reserve_chat_id(state_root)

    lock_path = paths.sessions_dir / f"{resolved_chat_id}.lock"
    handle = _acquire_session_lock(lock_path)
    session_instance_id = uuid.uuid4().hex
    try:
        event = SessionStartEvent(
            chat_id=resolved_chat_id,
            kind=kind,
            harness=harness,
            harness_session_id=harness_session_id,
            execution_cwd=execution_cwd,
            model=model,
            agent=agent,
            agent_path=agent_path,
            skills=skills,
            skill_paths=skill_paths,
            params=params,
            session_instance_id=session_instance_id,
            started_at=started_at,
            forked_from_chat_id=forked_from_chat_id,
        )
        with lock_file(paths.sessions_flock):
            append_event(paths.sessions_jsonl, paths.sessions_flock, event)
            _write_session_lease(paths, resolved_chat_id, session_instance_id)
    except Exception:
        _release_session_lock_handle(handle)
        handle.close()
        raise

    _SESSION_LOCK_HANDLES[_session_lock_key(state_root, resolved_chat_id)] = (
        handle,
        session_instance_id,
    )
    return resolved_chat_id


def stop_session(state_root: Path, chat_id: str) -> None:
    """Append a session stop event and release the lifetime session lock."""

    paths = StateRootPaths.from_root_dir(state_root)
    session_instance_id = _session_instance_for_event(paths, state_root, chat_id)
    event = SessionStopEvent(
        chat_id=chat_id,
        session_instance_id=session_instance_id,
        stopped_at=utc_now_iso(),
    )
    with lock_file(paths.sessions_flock):
        append_event(
            paths.sessions_jsonl,
            paths.sessions_flock,
            event,
            exclude_none=True,
        )
        _session_lease_path(paths, chat_id).unlink(missing_ok=True)
    _release_session_lock(state_root, chat_id)


def update_session_harness_id(state_root: Path, chat_id: str, harness_session_id: str) -> None:
    """Append a session update event carrying the resolved harness session ID."""

    paths = StateRootPaths.from_root_dir(state_root)
    event = SessionUpdateEvent(
        chat_id=chat_id,
        harness_session_id=harness_session_id,
        session_instance_id=_session_instance_for_event(paths, state_root, chat_id),
    )
    append_event(
        paths.sessions_jsonl,
        paths.sessions_flock,
        event,
        exclude_none=True,
    )


def update_session_work_id(state_root: Path, chat_id: str, work_id: str | None) -> None:
    """Set or clear the active work item for a session."""

    paths = StateRootPaths.from_root_dir(state_root)
    normalized_work_id = work_id.strip() if work_id is not None else ""
    event = SessionUpdateEvent(
        chat_id=chat_id,
        harness_session_id="",
        session_instance_id=_session_instance_for_event(paths, state_root, chat_id),
        active_work_id=normalized_work_id,
    )
    append_event(
        paths.sessions_jsonl,
        paths.sessions_flock,
        event,
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
            if not _try_lock_nonblocking(handle):
                active.append(chat_id)
                continue
            _release_session_lock_handle(handle)
    return sorted(active, key=_session_sort_key)


def list_active_session_records(state_root: Path) -> list[SessionRecord]:
    """Return materialized records for active sessions."""

    records = _records_by_session(state_root)
    return [
        record
        for chat_id in list_active_sessions(state_root)
        if (record := records.get(chat_id)) is not None
    ]


def list_active_sessions_for_work_id(state_root: Path, work_id: str) -> list[str]:
    """Return active session IDs currently attached to a work item."""

    normalized = work_id.strip()
    if not normalized:
        return []
    return [
        record.chat_id
        for record in list_active_session_records(state_root)
        if record.active_work_id == normalized
    ]


def chat_ids_ever_attached_to_work(state_root: Path, work_id: str) -> set[str]:
    """Return session IDs ever attached to a work item in raw session events."""

    normalized_work_id = work_id.strip()
    if not normalized_work_id:
        return set()

    paths = StateRootPaths.from_root_dir(state_root)

    def _parse_work_attachment(payload: dict[str, Any]) -> str | None:
        event_type = payload.get("event")
        if event_type not in {"start", "update"}:
            return None
        chat_id = payload.get("chat_id")
        if not isinstance(chat_id, str) or not chat_id.strip():
            return None
        active_work_id = payload.get("active_work_id")
        if not isinstance(active_work_id, str):
            return None
        if active_work_id.strip() != normalized_work_id:
            return None
        return chat_id.strip()

    return set(read_events(paths.sessions_jsonl, _parse_work_attachment))


def get_session_records(state_root: Path, chat_ids: set[str]) -> list[SessionRecord]:
    """Return materialized records for a set of Meridian chat/session IDs."""

    if not chat_ids:
        return []
    records = _records_by_session(state_root)
    return [
        records[chat_id]
        for chat_id in sorted(
            {chat_id.strip() for chat_id in chat_ids if chat_id.strip()},
            key=_session_sort_key,
        )
        if chat_id in records
    ]


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
    matches = [record for record in records.values() if normalized in record.harness_session_ids]
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

    from meridian.lib.state.paths import resolve_runtime_state_root

    try:
        state_root = resolve_runtime_state_root(repo_root)
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
        if not _try_lock_nonblocking(handle):
            handle.close()
            continue
        stale.append((chat_id, lock_path, handle))

    if not stale:
        return StaleSessionCleanup(cleaned_ids=(), materialized_scopes=())

    cleaned_ids: list[str] = []
    stale_cleanup_scopes: list[str] = []
    with lock_file(paths.sessions_flock):
        records = _records_by_session(state_root)
        stopped_at = utc_now_iso()
        for chat_id, lock_path, _ in stale:
            existing = records.get(chat_id)
            lease_exists, lease_session_instance_id = _read_session_lease(paths, chat_id)
            if existing is not None and existing.kind == "primary":
                continue
            stop_session_instance_id = lease_session_instance_id
            if not lease_exists and existing is not None:
                stop_session_instance_id = existing.session_instance_id
            if (
                existing is not None
                and existing.stopped_at is None
                and (
                    not lease_exists
                    or _generation_matches(
                        existing.session_instance_id,
                        lease_session_instance_id,
                    )
                )
            ):
                append_event(
                    paths.sessions_jsonl,
                    paths.sessions_flock,
                    SessionStopEvent(
                        chat_id=chat_id,
                        session_instance_id=stop_session_instance_id,
                        stopped_at=stopped_at,
                    ),
                    exclude_none=True,
                )
                records[chat_id] = existing.model_copy(update={"stopped_at": stopped_at})

            should_clean = existing is None or existing.stopped_at is not None or not lease_exists
            if existing is not None and existing.stopped_at is None:
                should_clean = not lease_exists or _generation_matches(
                    existing.session_instance_id, lease_session_instance_id
                )
            if not should_clean:
                continue

            if existing is not None and existing.harness.strip():
                stale_cleanup_scopes.append(existing.harness.strip())
            cleaned_ids.append(chat_id)
            lock_path.unlink(missing_ok=True)
            _session_lease_path(paths, chat_id).unlink(missing_ok=True)

    for chat_id, _, handle in stale:
        _release_session_lock_handle(handle)
        handle.close()
        if chat_id in cleaned_ids:
            _SESSION_LOCK_HANDLES.pop(_session_lock_key(state_root, chat_id), None)

    return StaleSessionCleanup(
        cleaned_ids=tuple(sorted(cleaned_ids, key=_session_sort_key)),
        materialized_scopes=tuple(sorted(set(stale_cleanup_scopes))),
    )
