"""File-backed spawn event store for a Meridian state root's `spawns.jsonl`.

Also includes file-backed ID generation for spawns and sessions.
"""


from pathlib import Path
from typing import Any, Literal, Mapping, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.core.spawn_lifecycle import (
    ACTIVE_SPAWN_STATUSES as _ACTIVE_SPAWN_STATUSES,
    is_active_spawn_status as _is_active_spawn_status,
    validate_transition,
)
from meridian.lib.core.types import SpawnId
from meridian.lib.state.event_store import append_event, lock_file, read_events, utc_now_iso
from meridian.lib.state.paths import StateRootPaths


# ---------------------------------------------------------------------------
# ID generation (absorbed from state/id_gen.py)
# ---------------------------------------------------------------------------


def _count_start_events(path: Path) -> int:
    def _parse_start_event(payload: dict[str, Any]) -> bool | None:
        event = payload.get("event")
        if isinstance(event, str) and event == "start":
            return True
        return None

    return len(read_events(path, _parse_start_event))


def next_spawn_id(state_root: Path) -> SpawnId:
    """Return the next spawn ID (`p1`, `p2`, ...) for a state root."""

    starts = _count_start_events(state_root / "spawns.jsonl")
    return SpawnId(f"p{starts + 1}")


def next_chat_id(state_root: Path) -> str:
    """Return the next session/chat ID (`c1`, `c2`, ...) for a state root."""

    starts = _count_start_events(state_root / "sessions.jsonl")
    return f"c{starts + 1}"


LaunchMode = Literal["background", "foreground"]
BACKGROUND_LAUNCH_MODE: LaunchMode = "background"
FOREGROUND_LAUNCH_MODE: LaunchMode = "foreground"

ACTIVE_SPAWN_STATUSES = _ACTIVE_SPAWN_STATUSES
is_active_spawn_status = _is_active_spawn_status


# ---------------------------------------------------------------------------
# Spawn event store
# ---------------------------------------------------------------------------


class SpawnRecord(BaseModel):
    """Derived spawn state assembled from spawn JSONL events."""
    model_config = ConfigDict(frozen=True)

    id: str
    chat_id: str | None
    model: str | None
    agent: str | None
    harness: str | None
    kind: str
    desc: str | None
    work_id: str | None
    harness_session_id: str | None
    launch_mode: str | None
    wrapper_pid: int | None
    worker_pid: int | None
    status: SpawnStatus | Literal["unknown"]
    prompt: str | None
    started_at: str | None
    finished_at: str | None
    exit_code: int | None
    duration_secs: float | None
    total_cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None


class SpawnStartEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["start"] = "start"
    id: str = ""
    chat_id: str | None = None
    model: str | None = None
    agent: str | None = None
    harness: str | None = None
    kind: str | None = None
    desc: str | None = None
    work_id: str | None = None
    harness_session_id: str | None = None
    launch_mode: str | None = None
    worker_pid: int | None = None
    status: SpawnStatus = "running"
    prompt: str | None = None
    started_at: str | None = None


class SpawnUpdateEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["update"] = "update"
    id: str = ""
    status: SpawnStatus | None = None
    launch_mode: LaunchMode | None = None
    wrapper_pid: int | None = None
    worker_pid: int | None = None
    error: str | None = None
    desc: str | None = None
    work_id: str | None = None


class SpawnFinalizeEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["finalize"] = "finalize"
    id: str = ""
    status: SpawnStatus | None = None
    exit_code: int | None = None
    finished_at: str | None = None
    duration_secs: float | None = None
    total_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None


type SpawnEvent = SpawnStartEvent | SpawnUpdateEvent | SpawnFinalizeEvent


def _parse_event(payload: dict[str, Any]) -> SpawnEvent | None:
    event_type = payload.get("event")
    try:
        if event_type == "start":
            return SpawnStartEvent.model_validate(payload)
        if event_type == "update":
            return SpawnUpdateEvent.model_validate(payload)
        if event_type == "finalize":
            return SpawnFinalizeEvent.model_validate(payload)
    except ValidationError:
        return None
    return None


def start_spawn(
    state_root: Path,
    *,
    chat_id: str,
    model: str,
    agent: str,
    harness: str,
    kind: str = "child",
    prompt: str,
    desc: str | None = None,
    work_id: str | None = None,
    spawn_id: SpawnId | str | None = None,
    harness_session_id: str | None = None,
    launch_mode: LaunchMode | None = None,
    worker_pid: int | None = None,
    status: SpawnStatus = "running",
    started_at: str | None = None,
) -> SpawnId:
    """Append a spawn start event under `spawns.lock` and return the spawn ID."""

    paths = StateRootPaths.from_root_dir(state_root)
    started = started_at or utc_now_iso()

    with lock_file(paths.spawns_lock):
        resolved_spawn_id = (
            SpawnId(str(spawn_id)) if spawn_id is not None else next_spawn_id(state_root)
        )
        event = SpawnStartEvent(
            id=str(resolved_spawn_id),
            chat_id=chat_id,
            model=model,
            agent=agent,
            harness=harness,
            kind=kind,
            desc=desc,
            work_id=work_id,
            harness_session_id=harness_session_id,
            launch_mode=launch_mode,
            worker_pid=worker_pid,
            status=status,
            started_at=started,
            prompt=prompt,
        )
        append_event(
            paths.spawns_jsonl,
            paths.spawns_lock,
            event,
            store_name="spawn",
            exclude_none=True,
        )
        return resolved_spawn_id


def update_spawn(
    state_root: Path,
    spawn_id: SpawnId | str,
    *,
    status: SpawnStatus | None = None,
    launch_mode: LaunchMode | None = None,
    wrapper_pid: int | None = None,
    worker_pid: int | None = None,
    error: str | None = None,
    desc: str | None = None,
    work_id: str | None = None,
) -> None:
    """Append a non-terminal spawn update event under `spawns.lock`."""

    paths = StateRootPaths.from_root_dir(state_root)
    event = SpawnUpdateEvent(
        id=str(spawn_id),
        status=status,
        launch_mode=launch_mode,
        wrapper_pid=wrapper_pid,
        worker_pid=worker_pid,
        error=error,
        desc=desc,
        work_id=work_id,
    )
    append_event(
        paths.spawns_jsonl,
        paths.spawns_lock,
        event,
        store_name="spawn",
        exclude_none=True,
    )


def finalize_spawn(
    state_root: Path,
    spawn_id: SpawnId | str,
    status: SpawnStatus,
    exit_code: int,
    *,
    duration_secs: float | None = None,
    total_cost_usd: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    finished_at: str | None = None,
    error: str | None = None,
) -> None:
    """Append a spawn finalize event under ``spawns.lock``.

    Unguarded: does not read current state, so no transition validation.
    Callers that need state-consistent transitions should use
    ``finalize_spawn_if_running`` or ``finalize_spawn_if_active`` instead.
    """

    paths = StateRootPaths.from_root_dir(state_root)
    event = SpawnFinalizeEvent(
        id=str(spawn_id),
        status=status,
        exit_code=exit_code,
        finished_at=finished_at or utc_now_iso(),
        duration_secs=duration_secs,
        total_cost_usd=total_cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=error,
    )

    append_event(
        paths.spawns_jsonl,
        paths.spawns_lock,
        event,
        store_name="spawn",
        exclude_none=True,
    )


def finalize_spawn_if_running(
    state_root: Path,
    spawn_id: SpawnId | str,
    status: SpawnStatus,
    exit_code: int,
    *,
    error: str | None = None,
) -> bool:
    """Append finalize event only if spawn is still running. Returns True if finalized."""
    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.spawns_lock):
        records = _record_from_events(read_events(paths.spawns_jsonl, _parse_event))
        record = records.get(str(spawn_id))
        if record is None or record.status != "running":
            return False
        validate_transition(cast("SpawnStatus", record.status), status)
        event = SpawnFinalizeEvent(
            id=str(spawn_id),
            status=status,
            exit_code=exit_code,
            finished_at=utc_now_iso(),
            error=error,
        )
        append_event(
            paths.spawns_jsonl,
            paths.spawns_lock,
            event,
            store_name="spawn",
            exclude_none=True,
        )
        return True


def finalize_spawn_if_active(
    state_root: Path,
    spawn_id: SpawnId | str,
    status: SpawnStatus,
    exit_code: int,
    *,
    duration_secs: float | None = None,
    total_cost_usd: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    error: str | None = None,
) -> bool:
    """Append finalize event only if spawn is queued or running."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.spawns_lock):
        records = _record_from_events(read_events(paths.spawns_jsonl, _parse_event))
        record = records.get(str(spawn_id))
        if record is None or not is_active_spawn_status(record.status):
            return False
        validate_transition(cast("SpawnStatus", record.status), status)
        event = SpawnFinalizeEvent(
            id=str(spawn_id),
            status=status,
            exit_code=exit_code,
            finished_at=utc_now_iso(),
            duration_secs=duration_secs,
            total_cost_usd=total_cost_usd,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            error=error,
        )
        append_event(
            paths.spawns_jsonl,
            paths.spawns_lock,
            event,
            store_name="spawn",
            exclude_none=True,
        )
        return True


def mark_spawn_running(
    state_root: Path,
    spawn_id: SpawnId | str,
    *,
    launch_mode: LaunchMode | None = None,
    wrapper_pid: int | None = None,
    worker_pid: int | None = None,
) -> None:
    update_spawn(
        state_root,
        spawn_id,
        status="running",
        launch_mode=launch_mode,
        wrapper_pid=wrapper_pid,
        worker_pid=worker_pid,
    )


def _empty_record(spawn_id: str) -> SpawnRecord:
    return SpawnRecord(
        id=spawn_id,
        chat_id=None,
        model=None,
        agent=None,
        harness=None,
        kind="child",
        desc=None,
        work_id=None,
        harness_session_id=None,
        launch_mode=None,
        wrapper_pid=None,
        worker_pid=None,
        status="unknown",
        prompt=None,
        started_at=None,
        finished_at=None,
        exit_code=None,
        duration_secs=None,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        error=None,
    )


def _record_from_events(events: list[SpawnEvent]) -> dict[str, SpawnRecord]:
    records: dict[str, SpawnRecord] = {}

    for event in events:
        spawn_id = event.id
        if not spawn_id:
            continue
        current = records.get(spawn_id, _empty_record(spawn_id))

        if isinstance(event, SpawnStartEvent):
            records[spawn_id] = current.model_copy(
                update={
                    "chat_id": event.chat_id if event.chat_id is not None else current.chat_id,
                    "model": event.model if event.model is not None else current.model,
                    "agent": event.agent if event.agent is not None else current.agent,
                    "harness": event.harness if event.harness is not None else current.harness,
                    "kind": event.kind if event.kind is not None else current.kind,
                    "desc": event.desc if event.desc is not None else current.desc,
                    "work_id": event.work_id if event.work_id is not None else current.work_id,
                    "harness_session_id": (
                        event.harness_session_id
                        if event.harness_session_id is not None
                        else current.harness_session_id
                    ),
                    "launch_mode": (
                        event.launch_mode if event.launch_mode is not None else current.launch_mode
                    ),
                    "worker_pid": (
                        event.worker_pid if event.worker_pid is not None else current.worker_pid
                    ),
                    "status": event.status,
                    "prompt": event.prompt if event.prompt is not None else current.prompt,
                    "started_at": event.started_at if event.started_at is not None else current.started_at,
                }
            )
            continue

        if isinstance(event, SpawnUpdateEvent):
            records[spawn_id] = current.model_copy(
                update={
                    "status": event.status if event.status is not None else current.status,
                    "launch_mode": (
                        event.launch_mode if event.launch_mode is not None else current.launch_mode
                    ),
                    "wrapper_pid": (
                        event.wrapper_pid if event.wrapper_pid is not None else current.wrapper_pid
                    ),
                    "worker_pid": (
                        event.worker_pid if event.worker_pid is not None else current.worker_pid
                    ),
                    "error": event.error if event.error is not None else current.error,
                    "desc": event.desc if event.desc is not None else current.desc,
                    "work_id": event.work_id if event.work_id is not None else current.work_id,
                }
            )
            continue

        records[spawn_id] = current.model_copy(
            update={
                "status": event.status if event.status is not None else current.status,
                "finished_at": event.finished_at if event.finished_at is not None else current.finished_at,
                "exit_code": event.exit_code if event.exit_code is not None else current.exit_code,
                "duration_secs": (
                    event.duration_secs if event.duration_secs is not None else current.duration_secs
                ),
                "total_cost_usd": (
                    event.total_cost_usd if event.total_cost_usd is not None else current.total_cost_usd
                ),
                "input_tokens": (
                    event.input_tokens if event.input_tokens is not None else current.input_tokens
                ),
                "output_tokens": (
                    event.output_tokens if event.output_tokens is not None else current.output_tokens
                ),
                "error": (
                    None if event.status == "succeeded"
                    else event.error if event.error is not None
                    else current.error
                ),
            }
        )

    return records


def _spawn_sort_key(spawn: SpawnRecord) -> tuple[int, str]:
    if len(spawn.id) >= 2 and spawn.id[0] in {"p", "r"} and spawn.id[1:].isdigit():
        return (int(spawn.id[1:]), spawn.id)
    return (10**9, spawn.id)


def list_spawns(state_root: Path, filters: Mapping[str, Any] | None = None) -> list[SpawnRecord]:
    """List derived spawn records with optional equality filters."""

    paths = StateRootPaths.from_root_dir(state_root)
    spawns = list(_record_from_events(read_events(paths.spawns_jsonl, _parse_event)).values())

    if filters:
        filtered: list[SpawnRecord] = []
        for spawn in spawns:
            spawn_data = spawn.model_dump()
            keep = True
            for key, expected in filters.items():
                if expected is None:
                    continue
                if key not in spawn_data:
                    continue
                if spawn_data[key] != expected:
                    keep = False
                    break
            if keep:
                filtered.append(spawn)
        spawns = filtered

    return sorted(spawns, key=_spawn_sort_key)


def get_spawn(state_root: Path, spawn_id: SpawnId | str) -> SpawnRecord | None:
    """Return one spawn by ID."""

    wanted = str(spawn_id)
    for spawn in list_spawns(state_root):
        if spawn.id == wanted:
            return spawn
    return None


def spawn_stats(state_root: Path) -> dict[str, Any]:
    """Aggregate high-level spawn stats from JSONL-derived records."""

    from meridian.lib.state.projections import spawn_stats as _projection_spawn_stats

    return _projection_spawn_stats(state_root).model_dump()
