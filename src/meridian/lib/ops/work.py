"""Work item operations for CLI dashboards and coordination."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import resolve_runtime_root_and_config
from meridian.lib.state import session_store, spawn_store, work_store
from meridian.lib.state.paths import resolve_state_paths

_ACTIVE_SPAWN_STATUSES = frozenset({"queued", "running"})


def _runtime_context(ctx: RuntimeContext | None) -> RuntimeContext:
    if ctx is not None:
        return ctx
    return RuntimeContext.from_environment()


def _resolve_roots(repo_root: str | None) -> tuple[Path, Path]:
    resolved_repo_root, _ = resolve_runtime_root_and_config(repo_root)
    return resolved_repo_root, resolve_state_paths(resolved_repo_root).root_dir


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
    if not desc:
        return ""
    return " ".join(desc.split())


def _dashboard_spawn(spawn: spawn_store.SpawnRecord) -> "WorkDashboardSpawn":
    return WorkDashboardSpawn(
        id=spawn.id,
        model=(spawn.model or "").strip() or "-",
        status=spawn.status,
        desc=_spawn_desc(spawn),
    )


def _format_spawn_rows(spawns: tuple["WorkDashboardSpawn", ...], *, indent: str) -> list[str]:
    if not spawns:
        return [f"{indent}(no spawns)"]

    from meridian.cli.format_helpers import tabular

    table = tabular([[spawn.id, spawn.model, spawn.status, spawn.desc] for spawn in spawns])
    return [f"{indent}{line}" for line in table.splitlines()]


def _resolve_chat_id(*, payload_chat_id: str = "", ctx: RuntimeContext | None = None) -> str:
    normalized = payload_chat_id.strip()
    if normalized:
        return normalized
    return _runtime_context(ctx).chat_id.strip()


def _session_exists(state_root: Path, chat_id: str) -> bool:
    normalized = chat_id.strip()
    if not normalized:
        return False
    return session_store.get_session_harness_id(state_root, normalized) is not None


def _set_active_work_id(
    state_root: Path,
    *,
    chat_id: str,
    work_id: str | None,
) -> bool:
    normalized = chat_id.strip()
    if not _session_exists(state_root, normalized):
        return False
    session_store.update_session_work_id(state_root, normalized, work_id)
    return True


def _require_work_item(state_root: Path, work_id: str) -> work_store.WorkItem:
    item = work_store.get_work_item(state_root, work_id)
    if item is None:
        raise ValueError(f"Work item '{work_id}' not found")
    return item


class WorkDashboardSpawn(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    model: str
    status: str
    desc: str = ""


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
        lines = ["ACTIVE"]
        if not self.items and not self.ungrouped_spawns:
            lines.append("  (none)")
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


class WorkStartInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    description: str = ""
    chat_id: str = ""
    repo_root: str | None = None


class WorkStartOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: str
    description: str
    created_at: str
    work_dir: str

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return f"Created work item: {self.name}\nDir: {self.work_dir}"


class WorkListItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: str
    description: str
    created_at: str


class WorkListInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    active: bool = False
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
        return "\n".join(lines)


class WorkUpdateInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    work_id: str
    status: str | None = None
    description: str | None = None
    repo_root: str | None = None


class WorkUpdateOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: str

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return f"Updated {self.name}: {self.status}"


class WorkDoneInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    work_id: str
    repo_root: str | None = None


class WorkSwitchInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    work_id: str
    chat_id: str = ""
    repo_root: str | None = None


class WorkSwitchOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    work_id: str
    message: str

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return self.message


class WorkClearInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    chat_id: str = ""
    repo_root: str | None = None


class WorkClearOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return self.message


def work_dashboard_sync(
    payload: WorkDashboardInput,
    ctx: RuntimeContext | None = None,
) -> WorkDashboardOutput:
    _ = ctx
    _, state_root = _resolve_roots(payload.repo_root)
    items_by_name = {item.name: item for item in work_store.list_work_items(state_root)}
    grouped: dict[str, list[WorkDashboardSpawn]] = {}
    ungrouped: list[WorkDashboardSpawn] = []

    from meridian.lib.state.reaper import reconcile_spawns
    for spawn in reconcile_spawns(state_root, spawn_store.list_spawns(state_root)):
        if spawn.status not in _ACTIVE_SPAWN_STATUSES:
            continue
        row = _dashboard_spawn(spawn)
        if spawn.work_id:
            grouped.setdefault(spawn.work_id, []).append(row)
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
                spawns=tuple(sorted(grouped[work_id], key=lambda spawn: _spawn_id_sort_key(spawn.id))),
            )
        )

    return WorkDashboardOutput(
        items=tuple(items),
        ungrouped_spawns=tuple(sorted(ungrouped, key=lambda spawn: _spawn_id_sort_key(spawn.id))),
    )


def work_start_sync(
    payload: WorkStartInput,
    ctx: RuntimeContext | None = None,
) -> WorkStartOutput:
    repo_root, state_root = _resolve_roots(payload.repo_root)
    item = work_store.create_work_item(state_root, payload.label, payload.description.strip())
    _set_active_work_id(
        state_root,
        chat_id=_resolve_chat_id(payload_chat_id=payload.chat_id, ctx=ctx),
        work_id=item.name,
    )
    return WorkStartOutput(
        name=item.name,
        status=item.status,
        description=item.description,
        created_at=item.created_at,
        work_dir=_display_path(repo_root, state_root / "work" / item.name),
    )


def work_list_sync(
    payload: WorkListInput,
    ctx: RuntimeContext | None = None,
) -> WorkListOutput:
    _ = ctx
    _, state_root = _resolve_roots(payload.repo_root)
    items = work_store.list_work_items(state_root)
    if payload.active:
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
    repo_root, state_root = _resolve_roots(payload.repo_root)
    from meridian.lib.state.reaper import reconcile_spawns
    item = _require_work_item(state_root, payload.work_id)
    return WorkShowOutput(
        name=item.name,
        status=item.status,
        description=item.description,
        created_at=item.created_at,
        work_dir=_display_path(repo_root, state_root / "work" / item.name),
        spawns=tuple(
            _dashboard_spawn(spawn)
            for spawn in reconcile_spawns(state_root, spawn_store.list_spawns(state_root, filters={"work_id": item.name}))
        ),
    )


def work_update_sync(
    payload: WorkUpdateInput,
    ctx: RuntimeContext | None = None,
) -> WorkUpdateOutput:
    _ = ctx
    if payload.status is None and payload.description is None:
        raise ValueError("Nothing to update. Pass --status and/or --description.")
    _, state_root = _resolve_roots(payload.repo_root)
    item = work_store.update_work_item(
        state_root,
        payload.work_id,
        status=payload.status,
        description=payload.description,
    )
    return WorkUpdateOutput(name=item.name, status=item.status)


def work_done_sync(
    payload: WorkDoneInput,
    ctx: RuntimeContext | None = None,
) -> WorkUpdateOutput:
    return work_update_sync(
        WorkUpdateInput(work_id=payload.work_id, status="done", repo_root=payload.repo_root),
        ctx=ctx,
    )


def work_switch_sync(
    payload: WorkSwitchInput,
    ctx: RuntimeContext | None = None,
) -> WorkSwitchOutput:
    _, state_root = _resolve_roots(payload.repo_root)
    item = _require_work_item(state_root, payload.work_id)
    updated = _set_active_work_id(
        state_root,
        chat_id=_resolve_chat_id(payload_chat_id=payload.chat_id, ctx=ctx),
        work_id=item.name,
    )
    message = (
        f"Active work item: {item.name}"
        if updated
        else f"Work item ready: {item.name} (no active session to update)"
    )
    return WorkSwitchOutput(work_id=item.name, message=message)


def work_clear_sync(
    payload: WorkClearInput,
    ctx: RuntimeContext | None = None,
) -> WorkClearOutput:
    _, state_root = _resolve_roots(payload.repo_root)
    updated = _set_active_work_id(
        state_root,
        chat_id=_resolve_chat_id(payload_chat_id=payload.chat_id, ctx=ctx),
        work_id=None,
    )
    message = "Cleared active work item." if updated else "No active session; nothing to clear."
    return WorkClearOutput(message=message)


async def work_dashboard(
    payload: WorkDashboardInput,
    ctx: RuntimeContext | None = None,
) -> WorkDashboardOutput:
    return work_dashboard_sync(payload, ctx=ctx)


async def work_start(
    payload: WorkStartInput,
    ctx: RuntimeContext | None = None,
) -> WorkStartOutput:
    return work_start_sync(payload, ctx=ctx)


async def work_list(
    payload: WorkListInput,
    ctx: RuntimeContext | None = None,
) -> WorkListOutput:
    return work_list_sync(payload, ctx=ctx)


async def work_show(
    payload: WorkShowInput,
    ctx: RuntimeContext | None = None,
) -> WorkShowOutput:
    return work_show_sync(payload, ctx=ctx)


async def work_update(
    payload: WorkUpdateInput,
    ctx: RuntimeContext | None = None,
) -> WorkUpdateOutput:
    return work_update_sync(payload, ctx=ctx)


async def work_done(
    payload: WorkDoneInput,
    ctx: RuntimeContext | None = None,
) -> WorkUpdateOutput:
    return work_done_sync(payload, ctx=ctx)


async def work_switch(
    payload: WorkSwitchInput,
    ctx: RuntimeContext | None = None,
) -> WorkSwitchOutput:
    return work_switch_sync(payload, ctx=ctx)


async def work_clear(
    payload: WorkClearInput,
    ctx: RuntimeContext | None = None,
) -> WorkClearOutput:
    return work_clear_sync(payload, ctx=ctx)


__all__ = [
    "WorkClearInput",
    "WorkClearOutput",
    "WorkDashboardInput",
    "WorkDashboardItem",
    "WorkDashboardOutput",
    "WorkDashboardSpawn",
    "WorkDoneInput",
    "WorkListInput",
    "WorkListItem",
    "WorkListOutput",
    "WorkShowInput",
    "WorkShowOutput",
    "WorkStartInput",
    "WorkStartOutput",
    "WorkSwitchInput",
    "WorkSwitchOutput",
    "WorkUpdateInput",
    "WorkUpdateOutput",
    "work_clear",
    "work_clear_sync",
    "work_dashboard",
    "work_dashboard_sync",
    "work_done",
    "work_done_sync",
    "work_list",
    "work_list_sync",
    "work_show",
    "work_show_sync",
    "work_start",
    "work_start_sync",
    "work_switch",
    "work_switch_sync",
    "work_update",
    "work_update_sync",
]
