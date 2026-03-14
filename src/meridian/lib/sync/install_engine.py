"""Managed install reconciler for repo-local `.agents/` content."""

from __future__ import annotations

import hashlib
import shutil
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from meridian.lib.sync.install_config import ManagedSourceConfig
from meridian.lib.sync.install_hash import compute_install_item_hash
from meridian.lib.sync.install_lock import LockedInstalledItem, LockedSourceItem, LockedSourceRecord
from meridian.lib.sync.install_lock import ManagedInstallLock, write_install_lock
from meridian.lib.sync.source_adapter import default_source_adapters
from meridian.lib.sync.source_manifest import ExportedSourceItem

ItemKind = Literal["agent", "skill"]
InstallAction = Literal[
    "installed",
    "updated",
    "skipped",
    "reinstalled",
    "conflict",
    "removed",
    "kept",
]


class InstallItemAction(BaseModel):
    """One managed install action."""

    model_config = ConfigDict(frozen=True)

    item_key: str
    item_kind: ItemKind
    source_name: str
    action: InstallAction
    reason: str
    dest_path: str


class InstallResult(BaseModel):
    """Aggregate install reconciliation result."""

    model_config = ConfigDict(frozen=True)

    actions: tuple[InstallItemAction, ...]
    errors: tuple[str, ...]


class PlannedSourceItem(BaseModel):
    """One source item plus its resolved destination."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    item: ExportedSourceItem
    destination_name: str
    destination_path: Path

    @property
    def item_key(self) -> str:
        return self.item.item_id

    @property
    def item_kind(self) -> ItemKind:
        return self.item.kind


def reconcile_managed_sources(
    *,
    repo_root: Path,
    agents_lock_path: Path,
    sources: tuple[ManagedSourceConfig, ...] | list[ManagedSourceConfig],
    lock: ManagedInstallLock,
    agents_cache_dir: Path,
    upgrade: bool = False,
    force: bool = False,
    dry_run: bool = False,
    source_filter: str | None = None,
) -> InstallResult:
    """Resolve and reconcile managed sources into `.agents/`."""

    adapters = default_source_adapters()
    selected_sources = list(sources)
    if source_filter is not None:
        selected_sources = [source for source in selected_sources if source.name == source_filter]
        if not selected_sources:
            raise ValueError(f"Managed source '{source_filter}' not found.")

    actions: list[InstallItemAction] = []
    errors: list[str] = []
    planned_by_source: dict[str, tuple[list[PlannedSourceItem], Path, LockedSourceRecord]] = {}
    other_destinations = {
        entry.destination_path: item_key
        for item_key, entry in lock.items.items()
        if entry.source_name not in {source.name for source in selected_sources}
    }

    for source in selected_sources:
        try:
            adapter = adapters[source.kind]
            locked_source = lock.sources.get(source.name)
            resolved = adapter.resolve(
                source,
                cache_dir=agents_cache_dir,
                repo_root=repo_root,
                locked_identity=None if upgrade else (
                    locked_source.resolved_identity if locked_source is not None else None
                ),
                upgrade=upgrade,
            )
            tree_path = adapter.fetch(resolved)
            manifest = adapter.describe(tree_path)
            planned_items = plan_source_items(
                repo_root=repo_root,
                source=source,
                manifest_items=manifest.items,
            )
            _check_destination_collisions(
                source=source,
                planned_items=planned_items,
                other_destinations=other_destinations,
            )
            source_record = LockedSourceRecord(
                kind=source.kind,
                locator=source.url if source.url is not None else source.path or "",
                requested_ref=source.ref,
                resolved_identity=resolved.resolved_identity,
                items={
                    item.item_key: LockedSourceItem(
                        path=item.item.path,
                        managed=item.item.managed,
                        system=item.item.system,
                        depends_on=tuple(dep.item_id for dep in item.item.depends_on),
                        bundle_requires=tuple(dep.item_id for dep in item.item.bundle_requires),
                    )
                    for item in planned_items
                },
                realized_closure=tuple(item.item_key for item in planned_items),
            )
            planned_by_source[source.name] = (planned_items, tree_path, source_record)
        except Exception as exc:
            errors.append(f"Source '{source.name}' could not be prepared: {exc}")

    for source_name, (planned_items, tree_path, source_record) in planned_by_source.items():
        content_hashes: list[str] = []
        for planned in planned_items:
            try:
                action, content_hash = _apply_planned_item(
                    repo_root=repo_root,
                    planned=planned,
                    tree_path=tree_path,
                    lock=lock,
                    force=force,
                    dry_run=dry_run,
                )
                actions.append(action)
                if action.action not in {"conflict", "kept"}:
                    content_hashes.append(content_hash)
            except Exception as exc:
                errors.append(
                    f"Item '{planned.item_key}' from source '{source_name}' could not be installed: {exc}"
                )

        actions.extend(
            _prune_stale_source_items(
                repo_root=repo_root,
                lock=lock,
                source_name=source_name,
                desired_item_keys={planned.item_key for planned in planned_items},
                force=force,
                dry_run=dry_run,
            )
        )

        if not dry_run:
            lock.sources[source_name] = source_record.model_copy(
                update={"installed_tree_hash": _source_tree_hash(content_hashes)}
            )

    if not dry_run:
        write_install_lock(agents_lock_path, lock)

    return InstallResult(actions=tuple(actions), errors=tuple(errors))


def plan_source_items(
    *,
    repo_root: Path,
    source: ManagedSourceConfig,
    manifest_items: tuple[ExportedSourceItem, ...],
) -> list[PlannedSourceItem]:
    """Resolve selected items plus dependency closure for one source."""

    items_by_id = {item.item_id: item for item in manifest_items}
    if source.items is None:
        root_ids = {item_id for item_id in items_by_id}
    else:
        root_ids = {item.item_id for item in source.items}
    excluded_ids = {item.item_id for item in source.exclude_items}

    missing = sorted(item_id for item_id in root_ids | excluded_ids if item_id not in items_by_id)
    if missing:
        raise ValueError(f"Unknown manifest items requested: {', '.join(missing)}")

    selected_ids = _expand_closure(
        root_ids=root_ids,
        excluded_ids=excluded_ids,
        items_by_id=items_by_id,
    )

    planned: list[PlannedSourceItem] = []
    seen_destinations: set[tuple[str, str]] = set()
    for item_id in sorted(selected_ids):
        item = items_by_id[item_id]
        destination_name = source.rename.get(item_id, item.name)
        destination_key = (item.kind, destination_name)
        if destination_key in seen_destinations:
            raise ValueError(
                f"Source '{source.name}' maps multiple items to {item.kind}:{destination_name}."
            )
        seen_destinations.add(destination_key)
        planned.append(
            PlannedSourceItem(
                source_name=source.name,
                item=item,
                destination_name=destination_name,
                destination_path=_destination_path(repo_root, item.kind, destination_name),
            )
        )
    return planned


def remove_managed_source(
    *,
    repo_root: Path,
    agents_lock_path: Path,
    lock: ManagedInstallLock,
    source_name: str,
    force: bool = False,
    dry_run: bool = False,
) -> InstallResult:
    """Remove one managed source and its owned installed items."""

    if source_name not in lock.sources:
        raise ValueError(f"Managed source '{source_name}' not found in lock.")

    actions: list[InstallItemAction] = []
    item_keys = sorted(
        item_key for item_key, entry in lock.items.items() if entry.source_name == source_name
    )
    for item_key in item_keys:
        entry = lock.items[item_key]
        item_kind = "skill" if item_key.startswith("skill:") else "agent"
        dest_path = repo_root / entry.destination_path
        action_name = "removed"
        reason = "Removed managed item."
        if _path_exists(dest_path):
            local_hash = compute_install_item_hash(dest_path, item_kind)
            if local_hash != entry.content_hash and not force:
                action_name = "kept"
                reason = "Kept locally modified item."
            elif not dry_run:
                _remove_destination(dest_path)
        actions.append(
            InstallItemAction(
                item_key=item_key,
                item_kind=item_kind,
                source_name=source_name,
                action=action_name,
                reason=reason,
                dest_path=entry.destination_path,
            )
        )
        if not dry_run and action_name == "removed":
            del lock.items[item_key]

    if not dry_run:
        del lock.sources[source_name]
        write_install_lock(agents_lock_path, lock)

    return InstallResult(actions=tuple(actions), errors=())


def install_status(repo_root: Path, lock: ManagedInstallLock) -> list[dict[str, object]]:
    """Compare lockfile state against on-disk installed content."""

    payload: list[dict[str, object]] = []
    for item_key, entry in sorted(lock.items.items()):
        item_kind = "skill" if item_key.startswith("skill:") else "agent"
        dest_path = repo_root / entry.destination_path
        if entry.source_name not in lock.sources:
            status = "orphaned"
            reason = "Source is no longer present in the lock."
        elif not _path_exists(dest_path):
            status = "missing"
            reason = "Managed item is missing locally."
        else:
            local_hash = compute_install_item_hash(dest_path, item_kind)
            if local_hash == entry.content_hash:
                status = "in-sync"
                reason = "Local content matches the lock file."
            else:
                status = "locally-modified"
                reason = "Local content differs from the lock file."
        payload.append(
            {
                "key": item_key,
                "status": status,
                "reason": reason,
                "source_name": entry.source_name,
                "item_kind": item_kind,
                "dest_path": entry.destination_path,
            }
        )
    return payload


def _expand_closure(
    *,
    root_ids: set[str],
    excluded_ids: set[str],
    items_by_id: dict[str, ExportedSourceItem],
) -> set[str]:
    selected: set[str] = set()
    pending = list(sorted(root_ids))
    while pending:
        item_id = pending.pop()
        if item_id in selected:
            continue
        if item_id in excluded_ids:
            raise ValueError(f"Excluded item '{item_id}' is required by the selected closure.")
        selected.add(item_id)
        item = items_by_id[item_id]
        pending.extend(dep.item_id for dep in item.depends_on)
        pending.extend(dep.item_id for dep in item.bundle_requires)
    return selected


def _check_destination_collisions(
    *,
    source: ManagedSourceConfig,
    planned_items: list[PlannedSourceItem],
    other_destinations: dict[str, str],
) -> None:
    for planned in planned_items:
        dest_key = planned.destination_path.as_posix()
        existing = other_destinations.get(dest_key)
        if existing is None:
            other_destinations[dest_key] = planned.item_key
            continue
        raise ValueError(
            f"Source '{source.name}' collides at {dest_key} with existing item '{existing}'."
        )


def _apply_planned_item(
    *,
    repo_root: Path,
    planned: PlannedSourceItem,
    tree_path: Path,
    lock: ManagedInstallLock,
    force: bool,
    dry_run: bool,
) -> tuple[InstallItemAction, str]:
    source_path = _source_path(tree_path, planned.item)
    source_hash = compute_install_item_hash(source_path, planned.item.kind)
    existing = lock.items.get(planned.item_key)
    dest_exists = _path_exists(planned.destination_path)
    local_hash = (
        compute_install_item_hash(planned.destination_path, planned.item.kind)
        if dest_exists
        else None
    )

    action_name, reason = _decide_action(
        dest_exists=dest_exists,
        existing=existing,
        local_hash=local_hash,
        source_hash=source_hash,
        force=force,
    )
    action = InstallItemAction(
        item_key=planned.item_key,
        item_kind=planned.item.kind,
        source_name=planned.source_name,
        action=action_name,
        reason=reason,
        dest_path=planned.destination_path.relative_to(repo_root).as_posix(),
    )
    if dry_run or action_name in {"skipped", "conflict", "kept"}:
        return action, source_hash

    staged_path = _stage_source(
        source_path=source_path,
        item_kind=planned.item.kind,
        dest_path=planned.destination_path,
    )
    _atomic_swap(staged_path=staged_path, dest_path=planned.destination_path)
    lock.items[planned.item_key] = LockedInstalledItem(
        source_name=planned.source_name,
        source_item_id=planned.item_key,
        destination_path=planned.destination_path.relative_to(repo_root).as_posix(),
        content_hash=source_hash,
    )
    return action, source_hash


def _prune_stale_source_items(
    *,
    repo_root: Path,
    lock: ManagedInstallLock,
    source_name: str,
    desired_item_keys: set[str],
    force: bool,
    dry_run: bool,
) -> list[InstallItemAction]:
    actions: list[InstallItemAction] = []
    stale_keys = sorted(
        item_key
        for item_key, entry in lock.items.items()
        if entry.source_name == source_name and item_key not in desired_item_keys
    )
    for item_key in stale_keys:
        entry = lock.items[item_key]
        item_kind = "skill" if item_key.startswith("skill:") else "agent"
        dest_path = repo_root / entry.destination_path
        action_name = "removed"
        reason = "Removed item no longer selected from the source."
        if _path_exists(dest_path):
            local_hash = compute_install_item_hash(dest_path, item_kind)
            if local_hash != entry.content_hash and not force:
                action_name = "kept"
                reason = "Kept locally modified item no longer selected from the source."
            elif not dry_run:
                _remove_destination(dest_path)
        actions.append(
            InstallItemAction(
                item_key=item_key,
                item_kind=item_kind,
                source_name=source_name,
                action=action_name,
                reason=reason,
                dest_path=entry.destination_path,
            )
        )
        if not dry_run and action_name == "removed":
            del lock.items[item_key]
    return actions


def _decide_action(
    *,
    dest_exists: bool,
    existing: LockedInstalledItem | None,
    local_hash: str | None,
    source_hash: str,
    force: bool,
) -> tuple[InstallAction, str]:
    if not dest_exists:
        return "installed", "Installed managed item."
    if existing is None:
        if force:
            return "reinstalled", "Replaced unmanaged item due to --force."
        return "conflict", "Unmanaged destination already exists."
    if local_hash is not None and local_hash != existing.content_hash and not force:
        return "kept", "Kept locally modified item."
    if source_hash == existing.content_hash and local_hash == source_hash:
        return "skipped", "Local content already matches the locked source."
    if local_hash is not None and local_hash != existing.content_hash and force:
        return "reinstalled", "Replaced locally modified item due to --force."
    return "updated", "Updated managed item from source."


def _destination_path(repo_root: Path, item_kind: ItemKind, destination_name: str) -> Path:
    if item_kind == "agent":
        return repo_root / ".agents" / "agents" / f"{destination_name}.md"
    return repo_root / ".agents" / "skills" / destination_name


def _source_path(tree_path: Path, item: ExportedSourceItem) -> Path:
    resolved = tree_path / item.path
    if item.kind == "skill":
        return resolved.parent
    return resolved


def _stage_source(*, source_path: Path, item_kind: ItemKind, dest_path: Path) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_root = dest_path.parent / f".meridian-install-{uuid.uuid4().hex}"
    if item_kind == "agent":
        tmp_root.write_bytes(source_path.read_bytes())
        return tmp_root
    shutil.copytree(source_path, tmp_root)
    return tmp_root


def _atomic_swap(*, staged_path: Path, dest_path: Path) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_backup = dest_path.parent / f".meridian-backup-{uuid.uuid4().hex}"
    try:
        if _path_exists(dest_path):
            dest_path.replace(tmp_backup)
        staged_path.replace(dest_path)
    except Exception:
        if tmp_backup.exists() and not dest_path.exists():
            tmp_backup.replace(dest_path)
        raise
    finally:
        if tmp_backup.exists():
            _remove_destination(tmp_backup)


def _remove_destination(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return
    path.unlink(missing_ok=True)


def _path_exists(path: Path) -> bool:
    return path.exists() or path.is_symlink()


def _source_tree_hash(content_hashes: list[str]) -> str | None:
    if not content_hashes:
        return None
    digest = hashlib.sha256("\n".join(sorted(content_hashes)).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
