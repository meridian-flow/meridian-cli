"""Work item dashboard and projection operations."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.spawn_lifecycle import is_active_spawn_status
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import async_from_sync, resolve_roots, runtime_context
from meridian.lib.state import session_store, spawn_store, work_store


def _display_path(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def _spawn_id_sort_key(spawn_id: str) -> tuple[int, str]:
    if len(spawn_id) >= 2 and spawn_id[0] in {"p", "r"} and spawn_id[1:].isdigit():
        return (int(spawn_id[1:]), spawn_id)
    return (10**9, spawn_id)


def _spawn_desc(spawn: spawn_store.SpawnRecord) -> str:
    desc = (spawn.desc or "").strip()
    if desc:
        return " ".join(desc.split())
    if spawn.kind == "primary":
        return "(primary)"
    return ""


class WorkDashboardSpawn(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    model: str
    status: str
    desc: str = ""


def _dashboard_spawn(spawn: spawn_store.SpawnRecord) -> WorkDashboardSpawn:
    return WorkDashboardSpawn(
        id=spawn.id,
        model=(spawn.model or "").strip() or "-",
        status=spawn.status,
        desc=_spawn_desc(spawn),
    )


def _format_spawn_rows(spawns: tuple[WorkDashboardSpawn, ...], *, indent: str) -> list[str]:
    if not spawns:
        return [f"{indent}(no spawns)"]

    from meridian.cli.format_helpers import tabular

    table = tabular([[spawn.id, spawn.model, spawn.status, spawn.desc] for spawn in spawns])
    return [f"{indent}{line}" for line in table.splitlines()]


class WorkSessionItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    chat_id: str
    harness: str
    harness_session_id: str
    status: str
    model: str
    agent: str


def _format_session_rows(sessions: tuple[WorkSessionItem, ...], *, indent: str) -> list[str]:
    if not sessions:
        return [f"{indent}(no sessions)"]

    from meridian.cli.format_helpers import tabular

    rows = [["chat_id", "harness", "status", "model", "harness_session_id"]]
    rows.extend(
        [
            [
                session.chat_id,
                session.harness,
                session.status,
                session.model,
                session.harness_session_id,
            ]
            for session in sessions
        ]
    )
    return [f"{indent}{line}" for line in tabular(rows).splitlines()]


def _active_session_work_ids(state_root: Path) -> dict[str, str]:
    attached: dict[str, str] = {}
    for record in session_store.list_active_session_records(state_root):
        active_work_id = record.active_work_id
        if active_work_id:
            attached[record.chat_id] = active_work_id
    return attached


def _effective_work_id(
    spawn: spawn_store.SpawnRecord,
    *,
    active_session_work_ids: dict[str, str],
) -> str | None:
    if spawn.kind == "primary":
        chat_id = (spawn.chat_id or "").strip()
        if not chat_id:
            return None
        return active_session_work_ids.get(chat_id)
    normalized = (spawn.work_id or "").strip()
    return normalized or None


def _associated_with_work_item(
    spawn: spawn_store.SpawnRecord,
    *,
    work_id: str,
    active_session_work_ids: dict[str, str],
) -> bool:
    if spawn.kind == "primary":
        chat_id = (spawn.chat_id or "").strip()
        return (
            bool(chat_id)
            and is_active_spawn_status(spawn.status)
            and active_session_work_ids.get(chat_id) == work_id
        )
    return (spawn.work_id or "").strip() == work_id


def work_dir_display(repo_root: Path, state_root: Path, work_id: str) -> str:
    return _display_path(repo_root, work_store.work_scratch_dir(state_root, work_id))


class WorkDashboardItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: str
    spawns: tuple[WorkDashboardSpawn, ...] = ()


class WorkDashboardInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class WorkDashboardOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[WorkDashboardItem, ...] = ()
    ungrouped_spawns: tuple[WorkDashboardSpawn, ...] = ()

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines = ["ACTIVE ACTIVITY"]
        if not self.items and not self.ungrouped_spawns:
            lines.append("  (no active spawns)")
            return "\n".join(lines)

        has_spawns = False

        for item in self.items:
            lines.append(f"  {item.name}  {item.status}")
            lines.extend(_format_spawn_rows(item.spawns, indent="    "))
            if item.spawns:
                has_spawns = True
            lines.append("")

        if self.ungrouped_spawns:
            lines.append("  (no work)")
            lines.extend(_format_spawn_rows(self.ungrouped_spawns, indent="    "))
            has_spawns = True
            lines.append("")

        if lines[-1] == "":
            lines.pop()
        if has_spawns:
            lines.append("")
            lines.append("Run `meridian spawn show <id>` for details.")
        return "\n".join(lines)


class WorkListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: str
    description: str
    created_at: str


class WorkListInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    done_only: bool = False
    repo_root: str | None = None


class WorkListOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: tuple[WorkListItem, ...] = ()

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        if not self.items:
            return "(no work items)"

        from meridian.cli.format_helpers import tabular

        rows = [["name", "status", "created"]]
        rows.extend([[item.name, item.status, item.created_at] for item in self.items])
        return tabular(rows)


class WorkShowInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    work_id: str
    repo_root: str | None = None


class WorkShowOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: str
    description: str
    created_at: str
    work_dir: str
    spawns: tuple[WorkDashboardSpawn, ...] = ()
    sessions: tuple[WorkSessionItem, ...] = ()

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx

        from meridian.cli.format_helpers import kv_block

        lines = [
            kv_block(
                [
                    ("Work", self.name),
                    ("Status", self.status),
                    ("Description", self.description or "(none)"),
                    ("Created", self.created_at),
                    ("Dir", self.work_dir),
                ]
            )
        ]
        if self.spawns:
            lines.append("")
            lines.append("Spawns:")
            lines.extend(_format_spawn_rows(self.spawns, indent="  "))
        lines.append("")
        lines.append("Sessions:")
        lines.extend(_format_session_rows(self.sessions, indent="  "))
        return "\n".join(lines)


class WorkSessionsInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    work_id: str = ""
    all: bool = False
    repo_root: str | None = None


class WorkSessionsOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    work_id: str
    sessions: tuple[WorkSessionItem, ...] = ()
    all: bool = False

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines = _format_session_rows(self.sessions, indent="")
        if not self.all:
            lines.append("")
            lines.append("Use --all to include historical sessions.")
        return "\n".join(lines)


def _resolve_work_id(
    *,
    payload_work_id: str,
    state_root: Path,
    ctx: RuntimeContext | None,
) -> str:
    normalized = payload_work_id.strip()
    if normalized:
        return normalized

    resolved_ctx = runtime_context(ctx)
    if resolved_ctx.work_id is not None and resolved_ctx.work_id.strip():
        return resolved_ctx.work_id.strip()

    chat_id = resolved_ctx.chat_id.strip()
    if chat_id:
        attached_work_id = session_store.get_session_active_work_id(state_root, chat_id)
        if attached_work_id is not None and attached_work_id.strip():
            return attached_work_id.strip()

    raise ValueError(
        "No work item resolved. Pass `meridian work sessions <work_id>`, "
        "Use `--work-id` or run from a session attached to a work item."
    )


def _work_session_chat_ids(
    state_root: Path,
    work_id: str,
    *,
    include_all: bool,
) -> set[str]:
    normalized_work_id = work_id.strip()
    if not normalized_work_id:
        return set()

    from meridian.lib.state.reaper import reconcile_spawns

    chat_ids: set[str] = set()
    if include_all:
        chat_ids.update(
            session_store.chat_ids_ever_attached_to_work(state_root, normalized_work_id)
        )
        for spawn in reconcile_spawns(state_root, spawn_store.list_spawns(state_root)):
            if (spawn.work_id or "").strip() != normalized_work_id:
                continue
            chat_id = (spawn.chat_id or "").strip()
            if chat_id:
                chat_ids.add(chat_id)
        return chat_ids

    for record in session_store.list_active_session_records(state_root):
        if record.active_work_id == normalized_work_id:
            chat_ids.add(record.chat_id)
    for spawn in reconcile_spawns(state_root, spawn_store.list_spawns(state_root)):
        if spawn.kind == "primary":
            continue
        if not is_active_spawn_status(spawn.status):
            continue
        if (spawn.work_id or "").strip() != normalized_work_id:
            continue
        chat_id = (spawn.chat_id or "").strip()
        if chat_id:
            chat_ids.add(chat_id)
    return chat_ids


def _work_sessions_for_work_id(
    state_root: Path,
    work_id: str,
    *,
    include_all: bool,
) -> tuple[WorkSessionItem, ...]:
    active_chat_ids = set(session_store.list_active_sessions(state_root))
    chat_ids = _work_session_chat_ids(state_root, work_id, include_all=include_all)
    records = session_store.get_session_records(state_root, chat_ids)
    records.sort(key=lambda record: (record.started_at, record.chat_id))
    return tuple(
        WorkSessionItem(
            chat_id=record.chat_id,
            harness=(record.harness or "").strip() or "-",
            harness_session_id=(record.harness_session_id or "").strip() or "-",
            status="active" if record.chat_id in active_chat_ids else "stopped",
            model=(record.model or "").strip() or "-",
            agent=(record.agent or "").strip() or "-",
        )
        for record in records
    )


def work_dashboard_sync(
    payload: WorkDashboardInput,
    ctx: RuntimeContext | None = None,
) -> WorkDashboardOutput:
    _ = ctx
    state_root = resolve_roots(payload.repo_root).state_root
    items_by_name = {item.name: item for item in work_store.list_work_items(state_root)}
    active_session_work_ids = _active_session_work_ids(state_root)
    grouped: dict[str, list[WorkDashboardSpawn]] = {}
    ungrouped: list[WorkDashboardSpawn] = []

    from meridian.lib.state.reaper import reconcile_spawns

    for spawn in reconcile_spawns(state_root, spawn_store.list_spawns(state_root)):
        if not is_active_spawn_status(spawn.status):
            continue
        row = _dashboard_spawn(spawn)
        work_id = _effective_work_id(spawn, active_session_work_ids=active_session_work_ids)
        if work_id:
            grouped.setdefault(work_id, []).append(row)
        else:
            ungrouped.append(row)

    items: list[WorkDashboardItem] = []
    for work_id in sorted(
        grouped,
        key=lambda name: (
            items_by_name[name].created_at if name in items_by_name else "9999",
            name,
        ),
    ):
        item = items_by_name.get(work_id)
        items.append(
            WorkDashboardItem(
                name=work_id,
                status=item.status if item is not None else "missing",
                spawns=tuple(
                    sorted(grouped[work_id], key=lambda spawn: _spawn_id_sort_key(spawn.id))
                ),
            )
        )

    return WorkDashboardOutput(
        items=tuple(items),
        ungrouped_spawns=tuple(sorted(ungrouped, key=lambda spawn: _spawn_id_sort_key(spawn.id))),
    )


def work_list_sync(
    payload: WorkListInput,
    ctx: RuntimeContext | None = None,
) -> WorkListOutput:
    _ = ctx
    state_root = resolve_roots(payload.repo_root).state_root
    items = work_store.list_work_items(state_root)
    if payload.done_only:
        items = [item for item in items if item.status == "done"]
    else:
        items = [item for item in items if item.status != "done"]
    return WorkListOutput(
        items=tuple(
            WorkListItem(
                name=item.name,
                status=item.status,
                description=item.description,
                created_at=item.created_at,
            )
            for item in items
        )
    )


def work_show_sync(
    payload: WorkShowInput,
    ctx: RuntimeContext | None = None,
) -> WorkShowOutput:
    _ = ctx
    roots = resolve_roots(payload.repo_root)
    repo_root = roots.repo_root
    state_root = roots.state_root

    from meridian.lib.state.reaper import reconcile_spawns

    item = work_store.get_work_item(state_root, payload.work_id)
    if item is None:
        raise ValueError(f"Work item '{payload.work_id}' not found")

    active_session_work_ids = _active_session_work_ids(state_root)
    associated_spawns = [
        _dashboard_spawn(spawn)
        for spawn in reconcile_spawns(state_root, spawn_store.list_spawns(state_root))
        if _associated_with_work_item(
            spawn,
            work_id=item.name,
            active_session_work_ids=active_session_work_ids,
        )
    ]
    associated_spawns.sort(key=lambda spawn: _spawn_id_sort_key(spawn.id))

    return WorkShowOutput(
        name=item.name,
        status=item.status,
        description=item.description,
        created_at=item.created_at,
        work_dir=work_dir_display(repo_root, state_root, item.name),
        spawns=tuple(associated_spawns),
        sessions=_work_sessions_for_work_id(state_root, item.name, include_all=False),
    )


def work_sessions_sync(
    payload: WorkSessionsInput,
    ctx: RuntimeContext | None = None,
) -> WorkSessionsOutput:
    state_root = resolve_roots(payload.repo_root).state_root
    resolved_work_id = _resolve_work_id(
        payload_work_id=payload.work_id,
        state_root=state_root,
        ctx=ctx,
    )

    item = work_store.get_work_item(state_root, resolved_work_id)
    if item is None:
        raise ValueError(f"Work item '{resolved_work_id}' not found")

    return WorkSessionsOutput(
        work_id=item.name,
        sessions=_work_sessions_for_work_id(state_root, item.name, include_all=payload.all),
        all=payload.all,
    )


work_dashboard = async_from_sync(work_dashboard_sync)
work_list = async_from_sync(work_list_sync)
work_show = async_from_sync(work_show_sync)
work_sessions = async_from_sync(work_sessions_sync)


__all__ = [
    "WorkDashboardInput",
    "WorkDashboardItem",
    "WorkDashboardOutput",
    "WorkDashboardSpawn",
    "WorkListInput",
    "WorkListItem",
    "WorkListOutput",
    "WorkSessionItem",
    "WorkSessionsInput",
    "WorkSessionsOutput",
    "WorkShowInput",
    "WorkShowOutput",
    "work_dashboard",
    "work_dashboard_sync",
    "work_dir_display",
    "work_list",
    "work_list_sync",
    "work_sessions",
    "work_sessions_sync",
    "work_show",
    "work_show_sync",
]
