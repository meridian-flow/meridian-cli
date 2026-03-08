"""File-backed spawn event store for `.meridian/.spaces/<space-id>/spawns.jsonl`.

Also includes file-backed ID generation for spaces, spawns, and sessions.
"""


import fcntl
import json
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Mapping, cast

from pydantic import BaseModel, ConfigDict

from meridian.lib.state.paths import SpacePaths
from meridian.lib.core.types import SpaceId, SpawnId


# ---------------------------------------------------------------------------
# ID generation (absorbed from state/id_gen.py)
# ---------------------------------------------------------------------------


def _count_start_events(path: Path) -> int:
    if not path.exists():
        return 0

    count = 0
    with path.open("r", encoding="utf-8") as handle:
        lines = handle.readlines()

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            # Self-heal truncated trailing line from interrupted append.
            if index == len(lines) - 1:
                continue
            continue
        if isinstance(payload, dict):
            row = cast("dict[str, object]", payload)
            event = row.get("event")
            if isinstance(event, str) and event == "start":
                count += 1
    return count


def next_space_id(repo_root: Path) -> SpaceId:
    """Return the next monotonic space ID (`s1`, `s2`, ...)."""

    spaces_dir = repo_root / ".meridian" / ".spaces"
    if not spaces_dir.exists():
        return SpaceId("s1")

    max_suffix = 0
    for child in spaces_dir.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if not name.startswith("s"):
            continue
        suffix = name[1:]
        if suffix.isdigit():
            max_suffix = max(max_suffix, int(suffix))
    return SpaceId(f"s{max_suffix + 1}")


def next_spawn_id(space_dir: Path) -> SpawnId:
    """Return the next spawn ID (`p1`, `p2`, ...) for a space."""

    starts = _count_start_events(space_dir / "spawns.jsonl")
    return SpawnId(f"p{starts + 1}")


def next_chat_id(space_dir: Path) -> str:
    """Return the next session/chat ID (`c1`, `c2`, ...) for a space."""

    starts = _count_start_events(space_dir / "sessions.jsonl")
    return f"c{starts + 1}"


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
    harness_session_id: str | None
    status: str
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
    harness_session_id: str | None = None
    status: str = "running"
    prompt: str | None = None
    started_at: str | None = None


class SpawnFinalizeEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    v: int = 1
    event: Literal["finalize"] = "finalize"
    id: str = ""
    status: str | None = None
    exit_code: int | None = None
    finished_at: str | None = None
    duration_secs: float | None = None
    total_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None


type SpawnEvent = SpawnStartEvent | SpawnFinalizeEvent


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


def _parse_event(payload: dict[str, Any]) -> SpawnEvent | None:
    event_type = payload.get("event")
    if event_type == "start":
        return SpawnStartEvent.model_validate(payload)
    if event_type == "finalize":
        return SpawnFinalizeEvent.model_validate(payload)
    return None


def _read_events(path: Path) -> list[SpawnEvent]:
    if not path.exists():
        return []

    rows: list[SpawnEvent] = []
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


def start_spawn(
    space_dir: Path,
    *,
    chat_id: str,
    model: str,
    agent: str,
    harness: str,
    kind: str = "child",
    prompt: str,
    spawn_id: SpawnId | str | None = None,
    harness_session_id: str | None = None,
    started_at: str | None = None,
) -> SpawnId:
    """Append a spawn start event under `spawns.lock` and return the spawn ID."""

    paths = SpacePaths.from_space_dir(space_dir)
    started = started_at or _utc_now_iso()

    with _lock_file(paths.spawns_lock):
        resolved_spawn_id = SpawnId(str(spawn_id)) if spawn_id is not None else next_spawn_id(space_dir)
        event = SpawnStartEvent(
            id=str(resolved_spawn_id),
            chat_id=chat_id,
            model=model,
            agent=agent,
            harness=harness,
            kind=kind,
            harness_session_id=harness_session_id,
            status="running",
            started_at=started,
            prompt=prompt,
        )
        _append_event(paths.spawns_jsonl, event.model_dump(exclude_none=True))
        return resolved_spawn_id


def finalize_spawn(
    space_dir: Path,
    spawn_id: SpawnId | str,
    status: str,
    exit_code: int,
    *,
    duration_secs: float | None = None,
    total_cost_usd: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    finished_at: str | None = None,
    error: str | None = None,
) -> None:
    """Append a spawn finalize event under `spawns.lock`."""

    paths = SpacePaths.from_space_dir(space_dir)
    event = SpawnFinalizeEvent(
        id=str(spawn_id),
        status=status,
        exit_code=exit_code,
        finished_at=finished_at or _utc_now_iso(),
        duration_secs=duration_secs,
        total_cost_usd=total_cost_usd,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        error=error,
    )

    with _lock_file(paths.spawns_lock):
        _append_event(paths.spawns_jsonl, event.model_dump(exclude_none=True))


def _empty_record(spawn_id: str) -> SpawnRecord:
    return SpawnRecord(
        id=spawn_id,
        chat_id=None,
        model=None,
        agent=None,
        harness=None,
        kind="child",
        harness_session_id=None,
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
                    "harness_session_id": (
                        event.harness_session_id
                        if event.harness_session_id is not None
                        else current.harness_session_id
                    ),
                    "status": event.status,
                    "prompt": event.prompt if event.prompt is not None else current.prompt,
                    "started_at": event.started_at if event.started_at is not None else current.started_at,
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
                "error": event.error if event.error is not None else current.error,
            }
        )

    return records


def _spawn_sort_key(spawn: SpawnRecord) -> tuple[int, str]:
    if len(spawn.id) >= 2 and spawn.id[0] in {"p", "r"} and spawn.id[1:].isdigit():
        return (int(spawn.id[1:]), spawn.id)
    return (10**9, spawn.id)


def list_spawns(space_dir: Path, filters: Mapping[str, Any] | None = None) -> list[SpawnRecord]:
    """List derived spawn records with optional equality filters."""

    paths = SpacePaths.from_space_dir(space_dir)
    spawns = list(_record_from_events(_read_events(paths.spawns_jsonl)).values())

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


def get_spawn(space_dir: Path, spawn_id: SpawnId | str) -> SpawnRecord | None:
    """Return one spawn by ID."""

    wanted = str(spawn_id)
    for spawn in list_spawns(space_dir):
        if spawn.id == wanted:
            return spawn
    return None


def spawn_stats(space_dir: Path) -> dict[str, Any]:
    """Aggregate high-level spawn stats from JSONL-derived records."""

    spawns = list_spawns(space_dir)
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
