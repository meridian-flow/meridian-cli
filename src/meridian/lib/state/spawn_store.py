"""File-backed spawn event store for `.meridian/.spaces/<space-id>/spawns.jsonl`."""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from meridian.lib.state.id_gen import next_spawn_id
from meridian.lib.state.paths import SpacePaths
from meridian.lib.types import SpawnId

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
type JSONRow = dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class SpawnRecord:
    """Derived spawn state assembled from spawn JSONL events."""

    id: str
    chat_id: str | None
    model: str | None
    agent: str | None
    harness: str | None
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


def start_spawn(
    space_dir: Path,
    *,
    chat_id: str,
    model: str,
    agent: str,
    harness: str,
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
        event: JSONRow = {
            "v": 1,
            "event": "start",
            "id": str(resolved_spawn_id),
            "chat_id": chat_id,
            "model": model,
            "agent": agent,
            "harness": harness,
            "status": "running",
            "started_at": started,
            "prompt": prompt,
        }
        if harness_session_id is not None:
            event["harness_session_id"] = harness_session_id
        _append_event(paths.spawns_jsonl, event)
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
    event: JSONRow = {
        "v": 1,
        "event": "finalize",
        "id": str(spawn_id),
        "status": status,
        "exit_code": exit_code,
        "finished_at": finished_at or _utc_now_iso(),
    }
    if duration_secs is not None:
        event["duration_secs"] = duration_secs
    if total_cost_usd is not None:
        event["total_cost_usd"] = total_cost_usd
    if input_tokens is not None:
        event["input_tokens"] = input_tokens
    if output_tokens is not None:
        event["output_tokens"] = output_tokens
    if error is not None:
        event["error"] = error

    with _lock_file(paths.spawns_lock):
        _append_event(paths.spawns_jsonl, event)


def _empty_record(spawn_id: str) -> SpawnRecord:
    return SpawnRecord(
        id=spawn_id,
        chat_id=None,
        model=None,
        agent=None,
        harness=None,
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


def _record_from_events(events: list[JSONRow]) -> dict[str, SpawnRecord]:
    records: dict[str, SpawnRecord] = {}

    for event in events:
        spawn_id = str(event.get("id", ""))
        if not spawn_id:
            continue
        current = records.get(spawn_id, _empty_record(spawn_id))
        event_type = event.get("event")

        if event_type == "start":
            records[spawn_id] = SpawnRecord(
                id=spawn_id,
                chat_id=str(event["chat_id"]) if "chat_id" in event else current.chat_id,
                model=str(event["model"]) if "model" in event else current.model,
                agent=str(event["agent"]) if "agent" in event else current.agent,
                harness=str(event["harness"]) if "harness" in event else current.harness,
                harness_session_id=(
                    str(event["harness_session_id"])
                    if "harness_session_id" in event
                    else current.harness_session_id
                ),
                status=str(event.get("status", "running")),
                prompt=str(event["prompt"]) if "prompt" in event else current.prompt,
                started_at=str(event["started_at"]) if "started_at" in event else current.started_at,
                finished_at=current.finished_at,
                exit_code=current.exit_code,
                duration_secs=current.duration_secs,
                total_cost_usd=current.total_cost_usd,
                input_tokens=current.input_tokens,
                output_tokens=current.output_tokens,
                error=current.error,
            )
            continue

        if event_type == "finalize":
            duration_value = current.duration_secs
            if "duration_secs" in event:
                duration_value = float(event["duration_secs"])

            cost_value = current.total_cost_usd
            if "total_cost_usd" in event:
                cost_value = float(event["total_cost_usd"])

            input_tokens = current.input_tokens
            if "input_tokens" in event:
                input_tokens = int(event["input_tokens"])

            output_tokens = current.output_tokens
            if "output_tokens" in event:
                output_tokens = int(event["output_tokens"])

            exit_code = current.exit_code
            if "exit_code" in event:
                exit_code = int(event["exit_code"])

            records[spawn_id] = SpawnRecord(
                id=spawn_id,
                chat_id=current.chat_id,
                model=current.model,
                agent=current.agent,
                harness=current.harness,
                harness_session_id=current.harness_session_id,
                status=str(event.get("status", current.status)),
                prompt=current.prompt,
                started_at=current.started_at,
                finished_at=(
                    str(event["finished_at"]) if "finished_at" in event else current.finished_at
                ),
                exit_code=exit_code,
                duration_secs=duration_value,
                total_cost_usd=cost_value,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                error=str(event["error"]) if "error" in event else current.error,
            )

    return records


def _spawn_sort_key(spawn: SpawnRecord) -> tuple[int, str]:
    if spawn.id.startswith("r") and spawn.id[1:].isdigit():
        return (int(spawn.id[1:]), spawn.id)
    return (10**9, spawn.id)


def list_spawns(space_dir: Path, filters: Mapping[str, Any] | None = None) -> list[SpawnRecord]:
    """List derived spawn records with optional equality filters."""

    paths = SpacePaths.from_space_dir(space_dir)
    spawns = list(_record_from_events(_read_events(paths.spawns_jsonl)).values())

    if filters:
        filtered: list[SpawnRecord] = []
        for spawn in spawns:
            keep = True
            for key, expected in filters.items():
                if expected is None:
                    continue
                if not hasattr(spawn, key):
                    continue
                if getattr(spawn, key) != expected:
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
