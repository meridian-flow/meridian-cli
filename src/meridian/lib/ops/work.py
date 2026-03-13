"""Work item operations for CLI dashboards and coordination."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.context import RuntimeContext
from meridian.lib.core.spawn_lifecycle import is_active_spawn_status
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import async_from_sync, resolve_chat_id, resolve_roots, runtime_context
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


def _annotate_primary_spawn(state_root: Path, *, chat_id: str, work_id: str) -> None:
    """Tag the active primary spawn for this session with the work item."""
    for spawn in spawn_store.list_spawns(
        state_root, filters={"kind": "primary", "chat_id": chat_id}
    ):
        if is_active_spawn_status(spawn.status):
            spawn_store.update_spawn(state_root, spawn.id, work_id=work_id)
            break


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
            lines.append("  (no work items)")
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


class WorkRenameInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    work_id: str
    new_name: str
    chat_id: str = ""
    repo_root: str | None = None


class WorkRenameOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    old_name: str
    new_name: str
    changed: bool = True

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        if not self.changed:
            return f"Already named '{self.old_name}', nothing to rename."
        return f"Renamed {self.old_name} -> {self.new_name}"


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
    state_root = resolve_roots(payload.repo_root).state_root
    items_by_name = {item.name: item for item in work_store.list_work_items(state_root)}
    grouped: dict[str, list[WorkDashboardSpawn]] = {}
    ungrouped: list[WorkDashboardSpawn] = []

    from meridian.lib.state.reaper import reconcile_spawns
    for spawn in reconcile_spawns(state_root, spawn_store.list_spawns(state_root)):
        if not is_active_spawn_status(spawn.status):
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
    roots = resolve_roots(payload.repo_root)
    repo_root = roots.repo_root
    state_root = roots.state_root
    chat_id = resolve_chat_id(payload_chat_id=payload.chat_id, ctx=runtime_context(ctx))

    # Check if current work item is auto-generated — rename instead of creating new
    current_work_id = session_store.get_session_active_work_id(state_root, chat_id)
    if current_work_id:
        current_item = work_store.get_work_item(state_root, current_work_id)
        if current_item is not None and current_item.auto_generated:
            # Rename auto-generated item to user's chosen name
            new_slug = work_store.slugify(payload.label)
            renamed = work_store.rename_work_item(state_root, current_work_id, new_slug)
            # Clear auto_generated flag
            cleared = work_store.update_work_item(
                state_root, renamed.name, auto_generated=False,
                description=payload.description.strip() or renamed.description,
            )
            # Update spawn references
            for spawn in spawn_store.list_spawns(
                state_root, filters={"work_id": current_work_id}
            ):
                spawn_store.update_spawn(state_root, spawn.id, work_id=cleared.name)
            # Update session
            _set_active_work_id(state_root, chat_id=chat_id, work_id=cleared.name)
            _annotate_primary_spawn(state_root, chat_id=chat_id, work_id=cleared.name)
            return WorkStartOutput(
                name=cleared.name,
                status=cleared.status,
                description=cleared.description,
                created_at=cleared.created_at,
                work_dir=_display_path(repo_root, state_root / "work" / cleared.name),
            )

    # Normal path: create new work item
    item = work_store.create_work_item(state_root, payload.label, payload.description.strip())
    _set_active_work_id(state_root, chat_id=chat_id, work_id=item.name)
    _annotate_primary_spawn(state_root, chat_id=chat_id, work_id=item.name)
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
    state_root = resolve_roots(payload.repo_root).state_root
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
    roots = resolve_roots(payload.repo_root)
    repo_root = roots.repo_root
    state_root = roots.state_root
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
    state_root = resolve_roots(payload.repo_root).state_root
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
    state_root = resolve_roots(payload.repo_root).state_root
    item = _require_work_item(state_root, payload.work_id)
    chat_id = resolve_chat_id(payload_chat_id=payload.chat_id, ctx=runtime_context(ctx))
    updated = _set_active_work_id(state_root, chat_id=chat_id, work_id=item.name)
    _annotate_primary_spawn(state_root, chat_id=chat_id, work_id=item.name)
    message = (
        f"Active work item: {item.name}"
        if updated
        else f"Work item ready: {item.name} (no active session to update)"
    )
    return WorkSwitchOutput(work_id=item.name, message=message)


def work_rename_sync(
    payload: WorkRenameInput,
    ctx: RuntimeContext | None = None,
) -> WorkRenameOutput:
    state_root = resolve_roots(payload.repo_root).state_root
    old_name = payload.work_id
    _require_work_item(state_root, old_name)
    item = work_store.rename_work_item(state_root, old_name, payload.new_name)

    # Clear auto_generated flag if it was set — user has explicitly named it
    if item.auto_generated:
        item = work_store.update_work_item(state_root, item.name, auto_generated=False)

    # Update all spawns that reference the old work_id
    for spawn in spawn_store.list_spawns(state_root, filters={"work_id": old_name}):
        spawn_store.update_spawn(state_root, spawn.id, work_id=item.name)

    # Only update session active_work_id if it currently points to the old name
    chat_id = resolve_chat_id(payload_chat_id=payload.chat_id, ctx=runtime_context(ctx))
    current_work_id = session_store.get_session_active_work_id(state_root, chat_id)
    if current_work_id == old_name:
        _set_active_work_id(state_root, chat_id=chat_id, work_id=item.name)

    return WorkRenameOutput(old_name=old_name, new_name=item.name, changed=old_name != item.name)


def work_clear_sync(
    payload: WorkClearInput,
    ctx: RuntimeContext | None = None,
) -> WorkClearOutput:
    state_root = resolve_roots(payload.repo_root).state_root
    updated = _set_active_work_id(
        state_root,
        chat_id=resolve_chat_id(payload_chat_id=payload.chat_id, ctx=runtime_context(ctx)),
        work_id=None,
    )
    message = "Cleared active work item." if updated else "No active session; nothing to clear."
    return WorkClearOutput(message=message)


work_dashboard = async_from_sync(work_dashboard_sync)
work_start = async_from_sync(work_start_sync)
work_list = async_from_sync(work_list_sync)
work_show = async_from_sync(work_show_sync)
work_update = async_from_sync(work_update_sync)
work_done = async_from_sync(work_done_sync)
work_switch = async_from_sync(work_switch_sync)
work_rename = async_from_sync(work_rename_sync)
work_clear = async_from_sync(work_clear_sync)


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
    "WorkRenameInput",
    "WorkRenameOutput",
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
    "work_rename",
    "work_rename_sync",
    "work_show",
    "work_show_sync",
    "work_start",
    "work_start_sync",
    "work_switch",
    "work_switch_sync",
    "work_update",
    "work_update_sync",
]
