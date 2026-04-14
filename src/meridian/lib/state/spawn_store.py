"""File-backed spawn event store for a Meridian state root's `spawns.jsonl`.

Also includes file-backed ID generation for spawns and sessions.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from meridian.lib.core.domain import SpawnStatus
from meridian.lib.core.spawn_lifecycle import (
    ACTIVE_SPAWN_STATUSES as _ACTIVE_SPAWN_STATUSES,
)
from meridian.lib.core.spawn_lifecycle import (
    TERMINAL_SPAWN_STATUSES as _TERMINAL_SPAWN_STATUSES,
)
from meridian.lib.core.spawn_lifecycle import (
    is_active_spawn_status as _is_active_spawn_status,
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


LaunchMode = Literal["background", "foreground"]
BACKGROUND_LAUNCH_MODE: LaunchMode = "background"
FOREGROUND_LAUNCH_MODE: LaunchMode = "foreground"
SpawnOrigin = Literal["runner", "launcher", "launch_failure", "cancel", "reconciler"]

_AUTHORITATIVE_ORIGIN_VALUES: tuple[SpawnOrigin, ...] = (
    "runner",
    "launcher",
    "launch_failure",
    "cancel",
)
AUTHORITATIVE_ORIGINS: frozenset[SpawnOrigin] = frozenset(_AUTHORITATIVE_ORIGIN_VALUES)

_LEGACY_RECONCILER_ERROR_VALUES: tuple[str, ...] = (
    "orphan_run",
    "orphan_finalization",
    "missing_worker_pid",
    "harness_completed",
)
LEGACY_RECONCILER_ERRORS: frozenset[str] = frozenset(_LEGACY_RECONCILER_ERROR_VALUES)

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
    parent_id: str | None
    model: str | None
    agent: str | None
    agent_path: str | None
    skills: tuple[str, ...]
    skill_paths: tuple[str, ...]
    harness: str | None
    kind: str
    desc: str | None
    work_id: str | None
    harness_session_id: str | None
    execution_cwd: str | None = None
    launch_mode: str | None
    wrapper_pid: int | None
    worker_pid: int | None
    runner_pid: int | None
    status: SpawnStatus | Literal["unknown"]
    prompt: str | None
    started_at: str | None
    exited_at: str | None
    process_exit_code: int | None
    finished_at: str | None
    exit_code: int | None
    duration_secs: float | None
    total_cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    error: str | None
    terminal_origin: SpawnOrigin | None


class SpawnStartEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["start"] = "start"
    id: str = ""
    chat_id: str | None = None
    parent_id: str | None = None
    model: str | None = None
    agent: str | None = None
    agent_path: str | None = None
    skills: tuple[str, ...] = ()
    skill_paths: tuple[str, ...] = ()
    harness: str | None = None
    kind: str | None = None
    desc: str | None = None
    work_id: str | None = None
    harness_session_id: str | None = None
    execution_cwd: str | None = None
    launch_mode: str | None = None
    worker_pid: int | None = None
    runner_pid: int | None = None
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
    runner_pid: int | None = None
    harness_session_id: str | None = None
    execution_cwd: str | None = None
    error: str | None = None
    desc: str | None = None
    work_id: str | None = None


class SpawnExitedEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["exited"] = "exited"
    id: str = ""
    exit_code: int = 0
    exited_at: str | None = None


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
    origin: SpawnOrigin | None = None


type SpawnEvent = SpawnStartEvent | SpawnUpdateEvent | SpawnExitedEvent | SpawnFinalizeEvent


def _parse_event(payload: dict[str, Any]) -> SpawnEvent | None:
    event_type = payload.get("event")
    try:
        if event_type == "start":
            return SpawnStartEvent.model_validate(payload)
        if event_type == "update":
            return SpawnUpdateEvent.model_validate(payload)
        if event_type == "exited":
            return SpawnExitedEvent.model_validate(payload)
        if event_type == "finalize":
            return SpawnFinalizeEvent.model_validate(payload)
    except ValidationError:
        return None
    return None


def start_spawn(
    state_root: Path,
    *,
    chat_id: str,
    parent_id: str | None = None,
    model: str,
    agent: str,
    agent_path: str | None = None,
    skills: tuple[str, ...] = (),
    skill_paths: tuple[str, ...] = (),
    harness: str,
    kind: str = "child",
    prompt: str,
    desc: str | None = None,
    work_id: str | None = None,
    spawn_id: SpawnId | str | None = None,
    harness_session_id: str | None = None,
    execution_cwd: str | None = None,
    launch_mode: LaunchMode | None = None,
    worker_pid: int | None = None,
    runner_pid: int | None = None,
    status: SpawnStatus = "running",
    started_at: str | None = None,
) -> SpawnId:
    """Append a spawn start event under `spawns.jsonl.flock` and return the spawn ID."""

    paths = StateRootPaths.from_root_dir(state_root)
    started = started_at or utc_now_iso()

    with lock_file(paths.spawns_flock):
        resolved_spawn_id = (
            SpawnId(str(spawn_id)) if spawn_id is not None else next_spawn_id(state_root)
        )
        event = SpawnStartEvent(
            id=str(resolved_spawn_id),
            chat_id=chat_id,
            parent_id=parent_id,
            model=model,
            agent=agent,
            agent_path=agent_path,
            skills=skills,
            skill_paths=skill_paths,
            harness=harness,
            kind=kind,
            desc=desc,
            work_id=work_id,
            harness_session_id=harness_session_id,
            execution_cwd=execution_cwd,
            launch_mode=launch_mode,
            worker_pid=worker_pid,
            runner_pid=runner_pid,
            status=status,
            started_at=started,
            prompt=prompt,
        )
        append_event(
            paths.spawns_jsonl,
            paths.spawns_flock,
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
    runner_pid: int | None = None,
    harness_session_id: str | None = None,
    execution_cwd: str | None = None,
    error: str | None = None,
    desc: str | None = None,
    work_id: str | None = None,
) -> None:
    """Append a non-terminal spawn update event under `spawns.jsonl.flock`."""

    paths = StateRootPaths.from_root_dir(state_root)
    event = SpawnUpdateEvent(
        id=str(spawn_id),
        status=status,
        launch_mode=launch_mode,
        wrapper_pid=wrapper_pid,
        worker_pid=worker_pid,
        runner_pid=runner_pid,
        harness_session_id=harness_session_id,
        execution_cwd=execution_cwd,
        error=error,
        desc=desc,
        work_id=work_id,
    )
    append_event(
        paths.spawns_jsonl,
        paths.spawns_flock,
        event,
        store_name="spawn",
        exclude_none=True,
    )


def record_spawn_exited(
    state_root: Path,
    spawn_id: SpawnId | str,
    *,
    exit_code: int,
    exited_at: str | None = None,
) -> None:
    """Append an exited event — the harness process has exited."""

    paths = StateRootPaths.from_root_dir(state_root)
    event = SpawnExitedEvent(
        id=str(spawn_id),
        exit_code=exit_code,
        exited_at=exited_at or utc_now_iso(),
    )
    append_event(
        paths.spawns_jsonl,
        paths.spawns_flock,
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
    origin: SpawnOrigin,
    duration_secs: float | None = None,
    total_cost_usd: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    finished_at: str | None = None,
    error: str | None = None,
) -> bool:
    """Append a finalize event and return whether this writer set the terminal status.

    Always writes the event so metadata is never lost -- the projection
    merges duration, cost, and token counts from every finalize event.
    Returns True when the spawn was active (queued or running) before
    this call, meaning this writer is the one that moved it to a
    terminal state. Returns False when the spawn was already terminal
    or does not exist.
    """
    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.spawns_flock):
        records = _record_from_events(read_events(paths.spawns_jsonl, _parse_event))
        record = records.get(str(spawn_id))
        was_active = record is not None and is_active_spawn_status(record.status)
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
            origin=origin,
        )
        append_event(
            paths.spawns_jsonl,
            paths.spawns_flock,
            event,
            store_name="spawn",
            exclude_none=True,
        )
        return was_active


def mark_spawn_running(
    state_root: Path,
    spawn_id: SpawnId | str,
    *,
    launch_mode: LaunchMode | None = None,
    wrapper_pid: int | None = None,
    worker_pid: int | None = None,
    runner_pid: int | None = None,
) -> None:
    update_spawn(
        state_root,
        spawn_id,
        status="running",
        launch_mode=launch_mode,
        wrapper_pid=wrapper_pid,
        worker_pid=worker_pid,
        runner_pid=runner_pid,
    )


def _empty_record(spawn_id: str) -> SpawnRecord:
    return SpawnRecord(
        id=spawn_id,
        chat_id=None,
        parent_id=None,
        model=None,
        agent=None,
        agent_path=None,
        skills=(),
        skill_paths=(),
        harness=None,
        kind="child",
        desc=None,
        work_id=None,
        harness_session_id=None,
        execution_cwd=None,
        launch_mode=None,
        wrapper_pid=None,
        worker_pid=None,
        runner_pid=None,
        status="unknown",
        prompt=None,
        started_at=None,
        exited_at=None,
        process_exit_code=None,
        finished_at=None,
        exit_code=None,
        duration_secs=None,
        total_cost_usd=None,
        input_tokens=None,
        output_tokens=None,
        error=None,
        terminal_origin=None,
    )


def _normalized_work_id(work_id: str | None) -> str | None:
    if work_id is None:
        return None
    normalized = work_id.strip()
    return normalized or None


def resolve_finalize_origin(event: SpawnFinalizeEvent) -> SpawnOrigin:
    if event.origin is not None:
        return event.origin
    if event.error in LEGACY_RECONCILER_ERRORS:
        return "reconciler"
    return "runner"


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
                    "parent_id": (
                        event.parent_id if event.parent_id is not None else current.parent_id
                    ),
                    "model": event.model if event.model is not None else current.model,
                    "agent": event.agent if event.agent is not None else current.agent,
                    "agent_path": (
                        event.agent_path if event.agent_path is not None else current.agent_path
                    ),
                    "skills": event.skills if event.skills else current.skills,
                    "skill_paths": event.skill_paths if event.skill_paths else current.skill_paths,
                    "harness": event.harness if event.harness is not None else current.harness,
                    "kind": event.kind if event.kind is not None else current.kind,
                    "desc": event.desc if event.desc is not None else current.desc,
                    "work_id": (
                        _normalized_work_id(event.work_id)
                        if event.work_id is not None
                        else current.work_id
                    ),
                    "harness_session_id": (
                        event.harness_session_id
                        if event.harness_session_id is not None
                        else current.harness_session_id
                    ),
                    "execution_cwd": (
                        event.execution_cwd
                        if event.execution_cwd is not None
                        else current.execution_cwd
                    ),
                    "launch_mode": (
                        event.launch_mode if event.launch_mode is not None else current.launch_mode
                    ),
                    "worker_pid": (
                        event.worker_pid if event.worker_pid is not None else current.worker_pid
                    ),
                    "runner_pid": (
                        event.runner_pid if event.runner_pid is not None else current.runner_pid
                    ),
                    "status": event.status,
                    "prompt": event.prompt if event.prompt is not None else current.prompt,
                    "started_at": event.started_at
                    if event.started_at is not None
                    else current.started_at,
                }
            )
            continue

        if isinstance(event, SpawnUpdateEvent):
            resolved_status = current.status
            if event.status is not None and current.status not in _TERMINAL_SPAWN_STATUSES:
                resolved_status = event.status
            records[spawn_id] = current.model_copy(
                update={
                    "status": resolved_status,
                    "launch_mode": (
                        event.launch_mode if event.launch_mode is not None else current.launch_mode
                    ),
                    "wrapper_pid": (
                        event.wrapper_pid if event.wrapper_pid is not None else current.wrapper_pid
                    ),
                    "worker_pid": (
                        event.worker_pid if event.worker_pid is not None else current.worker_pid
                    ),
                    "runner_pid": (
                        event.runner_pid if event.runner_pid is not None else current.runner_pid
                    ),
                    "harness_session_id": (
                        event.harness_session_id
                        if event.harness_session_id is not None
                        else current.harness_session_id
                    ),
                    "execution_cwd": (
                        event.execution_cwd
                        if event.execution_cwd is not None
                        else current.execution_cwd
                    ),
                    "error": event.error if event.error is not None else current.error,
                    "desc": event.desc if event.desc is not None else current.desc,
                    "work_id": (
                        _normalized_work_id(event.work_id)
                        if event.work_id is not None
                        else current.work_id
                    ),
                }
            )
            continue

        if isinstance(event, SpawnExitedEvent):
            records[spawn_id] = current.model_copy(
                update={
                    "exited_at": event.exited_at
                    if event.exited_at is not None
                    else current.exited_at,
                    "process_exit_code": event.exit_code,
                }
            )
            continue

        incoming_origin = resolve_finalize_origin(event)
        incoming_authoritative = incoming_origin in AUTHORITATIVE_ORIGINS
        already_terminal = current.status in _TERMINAL_SPAWN_STATUSES
        replace_terminal = (
            not already_terminal
            or (current.terminal_origin == "reconciler" and incoming_authoritative)
        )
        if not replace_terminal:
            resolved_status = current.status
            resolved_exit_code = current.exit_code
            resolved_error = current.error
            resolved_terminal_origin = current.terminal_origin
        else:
            event_status = event.status if event.status is not None else current.status
            resolved_status = event_status
            resolved_exit_code = (
                event.exit_code if event.exit_code is not None else current.exit_code
            )
            resolved_error = (
                None
                if event_status == "succeeded"
                else event.error
                if event.error is not None
                else current.error
            )
            resolved_terminal_origin = incoming_origin
        records[spawn_id] = current.model_copy(
            update={
                "status": resolved_status,
                "finished_at": event.finished_at
                if event.finished_at is not None
                else current.finished_at,
                "exit_code": resolved_exit_code,
                "duration_secs": (
                    event.duration_secs
                    if event.duration_secs is not None
                    else current.duration_secs
                ),
                "total_cost_usd": (
                    event.total_cost_usd
                    if event.total_cost_usd is not None
                    else current.total_cost_usd
                ),
                "input_tokens": (
                    event.input_tokens if event.input_tokens is not None else current.input_tokens
                ),
                "output_tokens": (
                    event.output_tokens
                    if event.output_tokens is not None
                    else current.output_tokens
                ),
                "error": resolved_error,
                "terminal_origin": resolved_terminal_origin,
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

    spawns = list_spawns(state_root)
    by_status: dict[str, int] = {}
    by_model: dict[str, int] = {}
    total_duration_secs = 0.0
    total_cost_usd = 0.0
    total_input_tokens = 0
    total_output_tokens = 0

    for spawn in spawns:
        by_status[spawn.status] = by_status.get(spawn.status, 0) + 1
        if spawn.model is not None:
            by_model[spawn.model] = by_model.get(spawn.model, 0) + 1
        if spawn.duration_secs is not None:
            total_duration_secs += spawn.duration_secs
        if spawn.total_cost_usd is not None:
            total_cost_usd += spawn.total_cost_usd
        if spawn.input_tokens is not None:
            total_input_tokens += spawn.input_tokens
        if spawn.output_tokens is not None:
            total_output_tokens += spawn.output_tokens

    return {
        "total_runs": len(spawns),
        "by_status": by_status,
        "by_model": by_model,
        "total_duration_secs": total_duration_secs,
        "total_cost_usd": total_cost_usd,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
    }
