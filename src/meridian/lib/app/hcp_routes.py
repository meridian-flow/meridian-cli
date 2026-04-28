"""HCP chat route handlers for the app server."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.app.agui_replay import (
    PaginationCursor,
    decode_pagination_cursor,
    encode_pagination_cursor,
    replay_events_paginated,
    replay_events_to_agui,
)
from meridian.lib.app.http_types import HTTPExceptionCallable
from meridian.lib.config.project_paths import ProjectConfigPaths
from meridian.lib.core.types import HarnessId, SpawnId
from meridian.lib.harness.connections.base import ConnectionConfig
from meridian.lib.harness.registry import get_default_harness_registry
from meridian.lib.hcp.errors import HcpError, HcpErrorCategory
from meridian.lib.hcp.session_manager import HcpSessionManager
from meridian.lib.launch.context import build_launch_context
from meridian.lib.launch.request import LaunchArgvIntent, LaunchRuntime, SpawnRequest
from meridian.lib.state import session_store, spawn_store
from meridian.lib.state.history import read_history_range
from meridian.lib.state.paths import RuntimePaths

DEFAULT_HISTORY_PAGE_LIMIT = 100


class _FastAPIApp(Protocol):
    """Minimal FastAPI app surface consumed by this module."""

    state: object

    def post(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...
    def get(self, path: str, **kwargs: object) -> Callable[[Callable[..., object]], object]: ...


class ChatCreateRequest(BaseModel):
    """REST payload for creating one HCP chat."""

    model_config = ConfigDict(frozen=True)

    prompt: str
    model: str | None = None
    harness: str = "claude"
    agent: str = ""
    skills: list[str] = Field(default_factory=list)


class ChatDetailResponse(BaseModel):
    """REST projection for one HCP chat."""

    model_config = ConfigDict(frozen=True)

    chat_id: str
    state: str
    harness: str
    model: str
    title: str | None = None
    created_at: str
    updated_at: str | None = None
    active_p_id: str | None = None
    launch_mode: str | None = None
    work_id: str | None = None
    first_message_snippet: str | None = None
    spawns: list[dict[str, object]] = Field(
        default_factory=lambda: list[dict[str, object]]()
    )


class PromptRequest(BaseModel):
    """REST payload for prompting one HCP chat."""

    model_config = ConfigDict(frozen=True)

    text: str


def _http_status_for_hcp_error(category: HcpErrorCategory) -> int:
    mapping = {
        HcpErrorCategory.CONCURRENT_PROMPT: 409,
        HcpErrorCategory.CHAT_NOT_FOUND: 404,
        HcpErrorCategory.HARNESS_CRASHED: 502,
        HcpErrorCategory.RESUME_FAILED: 502,
        HcpErrorCategory.HARNESS_NOT_FOUND: 404,
        HcpErrorCategory.HARNESS_AUTH_FAILED: 401,
        HcpErrorCategory.SESSION_EXPIRED: 410,
        HcpErrorCategory.PERMISSION_DENIED: 403,
        HcpErrorCategory.PROMPT_TOO_LARGE: 413,
        HcpErrorCategory.FAILED_PERSISTENCE: 500,
    }
    return mapping.get(category, 500)


def _agui_event_to_json(event: object) -> dict[str, Any]:
    model_dump = getattr(event, "model_dump", None)
    if callable(model_dump):
        return cast("dict[str, Any]", model_dump(mode="json", by_alias=True, exclude_none=True))
    dict_method = getattr(event, "dict", None)
    if callable(dict_method):
        return cast("dict[str, Any]", dict_method(by_alias=True, exclude_none=True))
    return cast("dict[str, Any]", event)


def _chat_detail(
    *,
    runtime_root: Path,
    manager: HcpSessionManager,
    c_id: str,
    http_exception: HTTPExceptionCallable,
) -> ChatDetailResponse:
    record = session_store.get_session_record(runtime_root, c_id)
    if record is None or record.kind != "primary" or record.stopped_at is not None:
        raise http_exception(status_code=404, detail="chat not found")

    state = manager.get_chat_state(c_id)
    active_spawn_id = manager.get_active_p_id(c_id)
    spawns = _chat_spawns(runtime_root, c_id)
    return ChatDetailResponse(
        chat_id=record.chat_id,
        state=state.value if state is not None else "idle",
        harness=record.harness,
        model=record.model,
        title=None,
        created_at=record.started_at,
        updated_at=None,
        active_p_id=str(active_spawn_id) if active_spawn_id is not None else None,
        launch_mode=_derive_launch_mode(spawns),
        work_id=_derive_work_id(spawns),
        first_message_snippet=_derive_first_message(spawns),
        spawns=[_spawn_summary(spawn) for spawn in spawns],
    )


def _derive_launch_mode(spawns: list[spawn_store.SpawnRecord]) -> str | None:
    """Return app launch mode if present, otherwise the first spawn's launch mode."""
    for spawn in spawns:
        if spawn.launch_mode == "app":
            return "app"
    if spawns:
        return spawns[0].launch_mode
    return None


def _derive_work_id(spawns: list[spawn_store.SpawnRecord]) -> str | None:
    """Return work ID from the most recent spawn that has one."""
    for spawn in reversed(spawns):
        if spawn.work_id:
            return spawn.work_id
    return None


def _derive_first_message(spawns: list[spawn_store.SpawnRecord]) -> str | None:
    """Return the first spawn prompt snippet for sidebar display."""
    if not spawns:
        return None
    prompt = spawns[0].prompt
    if not prompt:
        return None
    return prompt[:120]


def _spawn_summary(record: spawn_store.SpawnRecord) -> dict[str, object]:
    return {
        "spawn_id": record.id,
        "status": record.status,
        "harness": record.harness or "",
        "model": record.model or "",
        "agent": record.agent or "",
        "created_at": record.started_at or "",
        "started_at": record.started_at,
        "finished_at": record.finished_at,
    }


def _chat_spawns(runtime_root: Path, c_id: str) -> list[spawn_store.SpawnRecord]:
    return spawn_store.list_spawns(runtime_root, filters={"chat_id": c_id})


def _replay_spawns_to_agui(
    raw_events_by_spawn: list[tuple[spawn_store.SpawnRecord, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    agui_events: list[dict[str, Any]] = []
    for spawn, raw_events in raw_events_by_spawn:
        if not spawn.harness:
            continue
        for event in replay_events_to_agui(raw_events, HarnessId(spawn.harness), spawn.id):
            agui_events.append(_agui_event_to_json(event))
    return agui_events


def _chat_history_response(
    *,
    agui_events: list[dict[str, Any]],
    start_seq: int,
    limit: int | None,
) -> dict[str, object]:
    bounded_start = max(start_seq, 0)
    bounded_limit = max(limit, 0) if limit is not None else None
    end = None if bounded_limit is None else bounded_start + bounded_limit
    page = agui_events[bounded_start:end]
    return {
        "events": _history_event_response(page, start_seq=bounded_start),
        "has_more": end is not None and end < len(agui_events),
    }


def _history_event_response(
    agui_events: list[dict[str, Any]],
    *,
    start_seq: int = 0,
) -> list[dict[str, Any]]:
    return [
        {
            "seq": start_seq + offset,
            "type": str(event.get("type", "")),
            "data": event,
            "timestamp": str(event.get("timestamp", "")),
        }
        for offset, event in enumerate(agui_events)
    ]


def _paginated_history_response(
    *,
    agui_events: list[dict[str, Any]],
    next_cursor: str | None,
    has_more: bool,
) -> dict[str, object]:
    return {
        "events": _history_event_response(agui_events),
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


def register_hcp_routes(
    app: object,
    hcp_session_manager: HcpSessionManager | None,
    runtime_root: Path,
    http_exception: HTTPExceptionCallable,
    *,
    project_paths: ProjectConfigPaths | None = None,
) -> None:
    """Register HCP chat routes."""

    typed_app = cast("_FastAPIApp", app)
    paths = RuntimePaths.from_root_dir(runtime_root)

    def _manager() -> HcpSessionManager:
        state_manager = getattr(typed_app.state, "hcp_session_manager", None)
        resolved = state_manager or hcp_session_manager
        if resolved is None:
            raise http_exception(status_code=503, detail="HCP session manager is not ready")
        return cast("HcpSessionManager", resolved)

    def _require_chat(c_id: str) -> session_store.SessionRecord:
        record = session_store.get_session_record(runtime_root, c_id)
        if record is None or record.kind != "primary" or record.stopped_at is not None:
            raise http_exception(status_code=404, detail="chat not found")
        return record

    def _handle_hcp_error(error: HcpError) -> NoReturn:
        raise http_exception(
            status_code=_http_status_for_hcp_error(error.category),
            detail=error.message,
        )

    async def create_chat(body: ChatCreateRequest) -> ChatDetailResponse:
        """Create a new HCP chat.

        DS-002: ConnectionConfig.env_overrides projected from LaunchContext.
        """
        prompt = body.prompt.strip()
        if not prompt:
            raise http_exception(status_code=400, detail="prompt is required")

        try:
            harness_id = HarnessId(body.harness.strip().lower())
        except ValueError as exc:
            raise http_exception(
                status_code=400,
                detail=f"unsupported harness '{body.harness}'",
            ) from exc

        resolved_project_paths = project_paths
        if resolved_project_paths is None:
            raise http_exception(status_code=503, detail="project paths are not available")

        model = body.model.strip() if body.model and body.model.strip() else None
        agent = body.agent.strip()
        skills = tuple(skill.strip() for skill in body.skills if skill.strip())
        spawn_id = spawn_store.next_spawn_id(runtime_root)

        # Build launch context FIRST to get resolved metadata and env_overrides
        spawn_req = SpawnRequest(
            prompt=prompt,
            model=model,
            harness=harness_id.value,
            agent=agent or None,
            skills=skills,
        )
        launch_runtime = LaunchRuntime(
            argv_intent=LaunchArgvIntent.SPEC_ONLY,
            unsafe_no_permissions=False,
            runtime_root=runtime_root.as_posix(),
            project_paths_project_root=resolved_project_paths.project_root.as_posix(),
            project_paths_execution_cwd=resolved_project_paths.execution_cwd.as_posix(),
        )
        launch_ctx = build_launch_context(
            spawn_id=str(spawn_id),
            request=spawn_req,
            runtime=launch_runtime,
            harness_registry=get_default_harness_registry(),
        )

        # DS-002: Project ConnectionConfig from LaunchContext (not empty env_overrides)
        config = ConnectionConfig(
            spawn_id=spawn_id,
            harness_id=harness_id,
            prompt=launch_ctx.resolved_request.prompt,
            project_root=launch_ctx.child_cwd,
            env_overrides=dict(launch_ctx.env_overrides),
            system=launch_ctx.resolved_request.agent_metadata.get("appended_system_prompt"),
        )

        # Use resolved values from launch_ctx where available
        resolved_model = (launch_ctx.resolved_request.model or "").strip() or model
        resolved_agent = (launch_ctx.resolved_request.agent or "").strip() or agent

        try:
            c_id, _p_id = await _manager().create_chat(
                prompt,
                model=resolved_model,
                harness=harness_id.value,
                config=config,
                spec=launch_ctx.spec,
                agent=resolved_agent,
                skills=skills,
                execution_cwd=resolved_project_paths.execution_cwd.as_posix(),
            )
        except HcpError as exc:
            _handle_hcp_error(exc)
        return _chat_detail(
            runtime_root=runtime_root,
            manager=_manager(),
            c_id=c_id,
            http_exception=http_exception,
        )

    async def list_chats() -> list[ChatDetailResponse]:
        manager = _manager()
        return [
            _chat_detail(
                runtime_root=runtime_root,
                manager=manager,
                c_id=record.chat_id,
                http_exception=http_exception,
            )
            for record in session_store.list_active_session_records(runtime_root)
            if record.kind == "primary"
        ]

    async def get_chat(c_id: str) -> ChatDetailResponse:
        _require_chat(c_id)
        return _chat_detail(
            runtime_root=runtime_root,
            manager=_manager(),
            c_id=c_id,
            http_exception=http_exception,
        )

    async def prompt_chat(c_id: str, body: PromptRequest) -> ChatDetailResponse:
        _require_chat(c_id)
        text = body.text.strip()
        if not text:
            raise http_exception(status_code=400, detail="text is required")
        try:
            await _manager().prompt(c_id, text)
        except HcpError as exc:
            _handle_hcp_error(exc)
        return _chat_detail(
            runtime_root=runtime_root,
            manager=_manager(),
            c_id=c_id,
            http_exception=http_exception,
        )

    async def cancel_chat(c_id: str) -> dict[str, bool]:
        _require_chat(c_id)
        try:
            await _manager().cancel(c_id)
        except HcpError as exc:
            _handle_hcp_error(exc)
        return {"ok": True}

    async def close_chat(c_id: str) -> dict[str, bool]:
        _require_chat(c_id)
        try:
            await _manager().close_chat(c_id)
        except HcpError as exc:
            _handle_hcp_error(exc)
        return {"ok": True}

    def _chat_history_paginated_response(
        *,
        spawns: list[spawn_store.SpawnRecord],
        page_cursor: PaginationCursor,
        cursor: str | None,
        limit: int,
        http_exception: HTTPExceptionCallable,
    ) -> dict[str, object]:
        if limit <= 0:
            raise http_exception(status_code=400, detail="limit must be positive")
        if page_cursor.spawn_idx >= len(spawns):
            return _paginated_history_response(
                agui_events=[],
                next_cursor=None,
                has_more=False,
            )

        remaining = limit
        collected: list[dict[str, Any]] = []
        spawn_idx = page_cursor.spawn_idx
        inner_cursor = cursor

        while spawn_idx < len(spawns) and remaining > 0:
            spawn = spawns[spawn_idx]
            if not spawn.harness:
                spawn_idx += 1
                inner_cursor = None
                continue

            page = replay_events_paginated(
                paths.spawn_history_path(spawn.id),
                HarnessId(spawn.harness),
                spawn.id,
                limit=remaining,
                cursor=inner_cursor,
            )
            collected.extend(_agui_event_to_json(event) for event in page.events)
            remaining = limit - len(collected)

            if page.has_more:
                if page.next_cursor is None:
                    raise http_exception(status_code=500, detail="missing pagination cursor")
                next_inner = decode_pagination_cursor(page.next_cursor)
                next_cursor = encode_pagination_cursor(
                    PaginationCursor(
                        raw_seq=next_inner.raw_seq,
                        agui_skip=next_inner.agui_skip,
                        checkpoint=next_inner.checkpoint,
                        spawn_idx=spawn_idx,
                    )
                )
                return _paginated_history_response(
                    agui_events=collected,
                    next_cursor=next_cursor,
                    has_more=True,
                )

            spawn_idx += 1
            inner_cursor = None
            if remaining == 0 and spawn_idx < len(spawns):
                next_cursor = encode_pagination_cursor(
                    PaginationCursor(
                        raw_seq=0,
                        agui_skip=0,
                        checkpoint=0,
                        spawn_idx=spawn_idx,
                    )
                )
                return _paginated_history_response(
                    agui_events=collected,
                    next_cursor=next_cursor,
                    has_more=True,
                )

        return _paginated_history_response(
            agui_events=collected,
            next_cursor=None,
            has_more=False,
        )

    async def get_chat_history(
        c_id: str,
        start_seq: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> dict[str, object]:
        _require_chat(c_id)
        if cursor is not None:
            try:
                page_cursor = decode_pagination_cursor(cursor)
            except ValueError as exc:
                raise http_exception(status_code=400, detail="invalid cursor") from exc
            return _chat_history_paginated_response(
                spawns=_chat_spawns(runtime_root, c_id),
                page_cursor=page_cursor,
                cursor=cursor,
                limit=limit if limit is not None else DEFAULT_HISTORY_PAGE_LIMIT,
                http_exception=http_exception,
            )

        if start_seq is None and limit is None:
            return _chat_history_paginated_response(
                spawns=_chat_spawns(runtime_root, c_id),
                page_cursor=PaginationCursor(raw_seq=0, agui_skip=0, checkpoint=0),
                cursor=None,
                limit=DEFAULT_HISTORY_PAGE_LIMIT,
                http_exception=http_exception,
            )

        raw_events_by_spawn = [
            (
                spawn,
                read_history_range(paths.spawn_history_path(spawn.id)),
            )
            for spawn in _chat_spawns(runtime_root, c_id)
        ]
        return _chat_history_response(
            agui_events=_replay_spawns_to_agui(raw_events_by_spawn),
            start_seq=start_seq or 0,
            limit=limit,
        )

    async def list_chat_spawns(c_id: str) -> list[dict[str, object]]:
        _require_chat(c_id)
        return [_spawn_summary(record) for record in _chat_spawns(runtime_root, c_id)]

    async def get_spawn_history(
        p_id: str,
        start_seq: int | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> list[dict[str, Any]] | dict[str, object]:
        record = spawn_store.get_spawn(runtime_root, SpawnId(p_id))
        if record is None:
            raise http_exception(status_code=404, detail="spawn not found")

        if cursor is not None or (start_seq is None and limit is None):
            if cursor is not None:
                try:
                    decode_pagination_cursor(cursor)
                except ValueError as exc:
                    raise http_exception(status_code=400, detail="invalid cursor") from exc
            page_limit = limit if limit is not None else DEFAULT_HISTORY_PAGE_LIMIT
            if page_limit <= 0:
                raise http_exception(status_code=400, detail="limit must be positive")
            page = replay_events_paginated(
                paths.spawn_history_path(p_id),
                HarnessId(record.harness or ""),
                p_id,
                limit=page_limit,
                cursor=cursor,
            )
            return _paginated_history_response(
                agui_events=[_agui_event_to_json(event) for event in page.events],
                next_cursor=page.next_cursor,
                has_more=page.has_more,
            )

        raw_events = read_history_range(paths.spawn_history_path(p_id))
        agui_events = [
            _agui_event_to_json(event)
            for event in replay_events_to_agui(raw_events, HarnessId(record.harness or ""), p_id)
        ]
        bounded_start = max(start_seq or 0, 0)
        bounded_limit = max(limit, 0) if limit is not None else None
        end = None if bounded_limit is None else bounded_start + bounded_limit
        return agui_events[bounded_start:end]



    def _read_inbound_messages(spawn_id: str) -> list[dict[str, object]]:
        """Read user messages from inbound.jsonl for replay interleaving."""
        inbound_path = paths.spawn_history_path(spawn_id).parent / "inbound.jsonl"
        if not inbound_path.exists():
            return []
        
        messages: list[dict[str, object]] = []
        try:
            for line in inbound_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                if not isinstance(record, dict):
                    continue
                typed_record = cast("dict[str, object]", record)
                # Only include user_message actions
                if typed_record.get("action") != "user_message":
                    continue
                raw_data = typed_record.get("data", {})
                data = cast("dict[str, object]", raw_data) if isinstance(raw_data, dict) else {}
                raw_text = data.get("text", "")
                text = raw_text if isinstance(raw_text, str) else ""
                ts = typed_record.get("ts", 0)
                messages.append({
                    "seq": len(messages),
                    "text": text,
                    "ts": ts,
                })
        except Exception:
            pass
        return messages

    async def get_spawn_replay(p_id: str) -> dict[str, object]:
        """Return replay snapshot for Connect-Then-Replay protocol."""
        record = spawn_store.get_spawn(runtime_root, SpawnId(p_id))
        if record is None:
            raise http_exception(status_code=404, detail="spawn not found")

        history_path = paths.spawn_history_path(p_id)
        raw_events = read_history_range(history_path)
        
        # Short-circuit for empty history (EARS-R002)
        if not raw_events:
            return {"cursor": 0, "events": [], "inbound": []}

        # Use replay_events_to_agui (not paginated) per design
        agui_events = [
            _agui_event_to_json(event)
            for event in replay_events_to_agui(
                raw_events,
                HarnessId(record.harness or ""),
                p_id,
            )
        ]

        # Wrap events in the standard envelope
        wrapped_events = [
            {
                "seq": idx,
                "type": str(event.get("type", "")),
                "data": event,
                "timestamp": str(event.get("timestamp", "")),
            }
            for idx, event in enumerate(agui_events)
        ]

        return {
            "cursor": len(raw_events),
            "events": wrapped_events,
            "inbound": _read_inbound_messages(p_id),
        }

    typed_app.post("/api/chats", status_code=201)(create_chat)
    typed_app.get("/api/chats")(list_chats)
    typed_app.get("/api/chats/{c_id}")(get_chat)
    typed_app.post("/api/chats/{c_id}/prompt")(prompt_chat)
    typed_app.post("/api/chats/{c_id}/cancel")(cancel_chat)
    typed_app.post("/api/chats/{c_id}/close")(close_chat)
    typed_app.get("/api/chats/{c_id}/history")(get_chat_history)
    typed_app.get("/api/chats/{c_id}/spawns")(list_chat_spawns)
    typed_app.get("/api/spawns/{p_id}/history")(get_spawn_history)
    typed_app.get("/api/spawns/{p_id}/replay")(get_spawn_replay)


__all__ = [
    "ChatCreateRequest",
    "ChatDetailResponse",
    "PromptRequest",
    "register_hcp_routes",
]
