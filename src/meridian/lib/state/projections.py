"""In-memory state projections built from file-authoritative stores."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from meridian.lib.state.event_store import read_events
from meridian.lib.state.paths import StateRootPaths
from meridian.lib.state.session_store import (
    SessionRecord,
    _records_by_session,
)
from meridian.lib.state.session_store import (
    _parse_event as _parse_session_event,
)
from meridian.lib.state.spawn_store import (
    SpawnEvent,
    SpawnRecord,
    _record_from_events,
    _spawn_sort_key,
)
from meridian.lib.state.spawn_store import (
    _parse_event as _parse_spawn_event,
)
from meridian.lib.state.work_store import WorkItem, list_work_items


class SpawnStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_runs: int
    by_status: dict[str, int]
    by_model: dict[str, int]
    total_duration_secs: float
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int


class SpawnIndex:
    def __init__(self) -> None:
        self._by_id: dict[str, SpawnRecord] = {}
        self._by_status: dict[str, set[str]] = {}
        self._by_work_id: dict[str, set[str]] = {}
        self._stats_cache: SpawnStats | None = None

    def rebuild(self, state_root: Path) -> None:
        paths = StateRootPaths.from_root_dir(state_root)
        events = read_events(paths.spawns_jsonl, _parse_spawn_event)
        records = _record_from_events(events)

        self._by_id = records
        self._by_status = {}
        self._by_work_id = {}
        for record in records.values():
            self._index_record(record)
        self._stats_cache = None

    def on_event(self, store_name: str, payload: dict[str, Any]) -> None:
        if store_name != "spawn":
            return

        event = _parse_spawn_event(payload)
        if event is None:
            return

        self._apply_event(event)

    def get(self, spawn_id: str) -> SpawnRecord | None:
        return self._by_id.get(spawn_id)

    def list_spawns(
        self,
        *,
        status: str | None = None,
        work_id: str | None = None,
    ) -> list[SpawnRecord]:
        ids: set[str] | None = None

        if status is not None:
            ids = set(self._by_status.get(status, set()))
        if work_id is not None:
            work_ids = self._by_work_id.get(work_id, set())
            if ids is None:
                ids = set(work_ids)
            else:
                ids.intersection_update(work_ids)

        if ids is None:
            spawns = list(self._by_id.values())
        else:
            spawns = [self._by_id[spawn_id] for spawn_id in ids if spawn_id in self._by_id]

        return sorted(spawns, key=_spawn_sort_key)

    def stats(self) -> SpawnStats:
        if self._stats_cache is not None:
            return self._stats_cache

        by_status: dict[str, int] = {}
        by_model: dict[str, int] = {}
        total_duration_secs = 0.0
        total_cost_usd = 0.0
        total_input_tokens = 0
        total_output_tokens = 0

        for spawn in self._by_id.values():
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

        computed = SpawnStats(
            total_runs=len(self._by_id),
            by_status=by_status,
            by_model=by_model,
            total_duration_secs=total_duration_secs,
            total_cost_usd=total_cost_usd,
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )
        self._stats_cache = computed
        return computed

    def _normalized_work_id(self, work_id: str | None) -> str | None:
        if work_id is None:
            return None
        normalized = work_id.strip()
        return normalized or None

    def _apply_event(self, event: SpawnEvent) -> None:
        spawn_id = event.id
        if not spawn_id:
            return

        old_record = self._by_id.get(spawn_id)
        current = old_record if old_record is not None else _empty_spawn_record(spawn_id)

        if event.event == "start":
            updated = current.model_copy(
                update={
                    "chat_id": event.chat_id if event.chat_id is not None else current.chat_id,
                    "model": event.model if event.model is not None else current.model,
                    "agent": event.agent if event.agent is not None else current.agent,
                    "harness": event.harness if event.harness is not None else current.harness,
                    "kind": event.kind if event.kind is not None else current.kind,
                    "desc": event.desc if event.desc is not None else current.desc,
                    "work_id": (
                        self._normalized_work_id(event.work_id)
                        if event.work_id is not None
                        else current.work_id
                    ),
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
                    "started_at": event.started_at
                    if event.started_at is not None
                    else current.started_at,
                }
            )
        elif event.event == "update":
            updated = current.model_copy(
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
                    "harness_session_id": (
                        event.harness_session_id
                        if event.harness_session_id is not None
                        else current.harness_session_id
                    ),
                    "error": event.error if event.error is not None else current.error,
                    "desc": event.desc if event.desc is not None else current.desc,
                    "work_id": (
                        self._normalized_work_id(event.work_id)
                        if event.work_id is not None
                        else current.work_id
                    ),
                }
            )
        else:
            updated = current.model_copy(
                update={
                    "status": event.status if event.status is not None else current.status,
                    "finished_at": event.finished_at
                    if event.finished_at is not None
                    else current.finished_at,
                    "exit_code": event.exit_code
                    if event.exit_code is not None
                    else current.exit_code,
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
                        event.input_tokens
                        if event.input_tokens is not None
                        else current.input_tokens
                    ),
                    "output_tokens": (
                        event.output_tokens
                        if event.output_tokens is not None
                        else current.output_tokens
                    ),
                    "error": (
                        None
                        if event.status == "succeeded"
                        else event.error
                        if event.error is not None
                        else current.error
                    ),
                }
            )

        self._update_indexes(old_record, updated)
        self._by_id[spawn_id] = updated
        self._stats_cache = None

    def _index_record(self, record: SpawnRecord) -> None:
        self._by_status.setdefault(record.status, set()).add(record.id)
        if record.work_id is not None:
            self._by_work_id.setdefault(record.work_id, set()).add(record.id)

    def _remove_record_indexes(self, record: SpawnRecord) -> None:
        self._remove_from_index(self._by_status, record.status, record.id)
        if record.work_id is not None:
            self._remove_from_index(self._by_work_id, record.work_id, record.id)

    def _update_indexes(self, old_record: SpawnRecord | None, new_record: SpawnRecord) -> None:
        if old_record is not None:
            self._remove_record_indexes(old_record)
        self._index_record(new_record)

    @staticmethod
    def _remove_from_index(index: dict[str, set[str]], key: str, spawn_id: str) -> None:
        values = index.get(key)
        if values is None:
            return
        values.discard(spawn_id)
        if not values:
            index.pop(key, None)


class SessionIndex:
    def __init__(self) -> None:
        self._by_chat_id: dict[str, SessionRecord] = {}

    def rebuild(self, state_root: Path) -> None:
        self._by_chat_id = _records_by_session(state_root)

    def on_event(self, store_name: str, payload: dict[str, Any]) -> None:
        if store_name != "session":
            return

        event = _parse_session_event(payload)
        if event is None:
            return

        if event.event == "start":
            self._by_chat_id[event.chat_id] = SessionRecord(
                chat_id=event.chat_id,
                harness=event.harness,
                harness_session_id=event.harness_session_id,
                harness_session_ids=(event.harness_session_id,),
                model=event.model,
                agent=event.agent,
                agent_path=event.agent_path,
                agent_source=event.agent_source,
                skills=event.skills,
                skill_paths=event.skill_paths,
                skill_sources=event.skill_sources,
                bootstrap_required_items=event.bootstrap_required_items,
                bootstrap_missing_items=event.bootstrap_missing_items,
                params=event.params,
                started_at=event.started_at,
                stopped_at=None,
                session_instance_id=event.session_instance_id,
                active_work_id=None,
            )
            return

        existing = self._by_chat_id.get(event.chat_id)
        if existing is None:
            return

        if not _session_generation_matches(existing.session_instance_id, event.session_instance_id):
            return

        if event.event == "stop":
            self._by_chat_id[event.chat_id] = existing.model_copy(
                update={
                    "stopped_at": event.stopped_at
                    if event.stopped_at is not None
                    else existing.stopped_at,
                    "session_instance_id": event.session_instance_id
                    or existing.session_instance_id,
                }
            )
            return

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

        self._by_chat_id[event.chat_id] = existing.model_copy(
            update={
                "harness_session_id": harness_session_id,
                "harness_session_ids": session_ids,
                "session_instance_id": session_instance_id,
                "active_work_id": updated_work_id,
            }
        )

    def active_chat_ids(self) -> frozenset[str]:
        return frozenset(
            chat_id for chat_id, record in self._by_chat_id.items() if record.stopped_at is None
        )

    def get(self, chat_id: str) -> SessionRecord | None:
        return self._by_chat_id.get(chat_id)


class WorkIndex:
    def __init__(self) -> None:
        self._by_slug: dict[str, WorkItem] = {}

    def rebuild(self, state_root: Path) -> None:
        self._by_slug = {item.name: item for item in list_work_items(state_root)}

    def get(self, slug: str) -> WorkItem | None:
        return self._by_slug.get(slug)

    def list_items(self, *, active_only: bool = False) -> list[WorkItem]:
        items = sorted(self._by_slug.values(), key=lambda item: (item.created_at, item.name))
        if active_only:
            return [item for item in items if item.status != "done"]
        return items


def spawn_stats(state_root: Path) -> SpawnStats:
    """Convenience: rebuild + compute stats in one call."""

    index = SpawnIndex()
    index.rebuild(state_root)
    return index.stats()


def _empty_spawn_record(spawn_id: str) -> SpawnRecord:
    return SpawnRecord(
        id=spawn_id,
        chat_id=None,
        model=None,
        agent=None,
        agent_path=None,
        agent_source=None,
        skills=(),
        skill_paths=(),
        skill_sources={},
        bootstrap_required_items=(),
        bootstrap_missing_items=(),
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


def _session_generation_matches(expected: str, actual: str) -> bool:
    normalized_expected = expected.strip()
    normalized_actual = actual.strip()
    if not normalized_expected and not normalized_actual:
        return True
    return normalized_expected == normalized_actual
