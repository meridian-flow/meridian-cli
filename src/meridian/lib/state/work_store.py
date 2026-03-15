"""Metadata-backed work item store under `.meridian/work-items/`."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.event_store import lock_file, utc_now_iso
from meridian.lib.state.paths import StateRootPaths

_MAX_SLUG_LENGTH = 64
_NON_ALNUM_HYPHEN = re.compile(r"[^a-z0-9-]+")
_WHITESPACE_OR_UNDERSCORE = re.compile(r"[\s_]+")
_REPEATED_HYPHENS = re.compile(r"-+")


class WorkItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    status: str
    created_at: str


class WorkRenameIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    old_work_id: str
    new_work_id: str
    started_at: str


def slugify(label: str) -> str:
    """Return a normalized work-item slug."""

    normalized = label.strip().lower()
    normalized = _WHITESPACE_OR_UNDERSCORE.sub("-", normalized)
    normalized = _NON_ALNUM_HYPHEN.sub("", normalized)
    normalized = _REPEATED_HYPHENS.sub("-", normalized)
    normalized = normalized.strip("-")
    normalized = normalized[:_MAX_SLUG_LENGTH].strip("-")
    return normalized


def _work_item_path(state_root: Path, work_id: str) -> Path:
    return StateRootPaths.from_root_dir(state_root).work_items_dir / f"{work_id}.json"


def _work_scratch_dir(paths: StateRootPaths, work_id: str) -> Path:
    return paths.work_dir / work_id


def _archived_work_scratch_dir(paths: StateRootPaths, work_id: str) -> Path:
    return paths.work_archive_dir / work_id


def _locate_work_scratch_dir(paths: StateRootPaths, work_id: str) -> Path | None:
    active_dir = _work_scratch_dir(paths, work_id)
    archived_dir = _archived_work_scratch_dir(paths, work_id)
    if active_dir.exists() and archived_dir.exists():
        raise ValueError(
            f"Work item '{work_id}' has scratch dirs in both active and archive locations."
        )
    if active_dir.exists():
        return active_dir
    if archived_dir.exists():
        return archived_dir
    return None


def _serialize_work_item(item: WorkItem) -> str:
    return json.dumps(item.model_dump(), indent=2, sort_keys=True) + "\n"


def _read_work_item(path: Path) -> WorkItem | None:
    try:
        return WorkItem.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, json.JSONDecodeError):
        return None


def _ensure_work_item_metadata_locked(
    *,
    paths: StateRootPaths,
    work_id: str,
    description: str = "",
    status: str = "open",
) -> WorkItem:
    item_path = paths.work_items_dir / f"{work_id}.json"
    existing = _read_work_item(item_path)
    if existing is not None:
        return existing

    paths.work_items_dir.mkdir(parents=True, exist_ok=True)
    item = WorkItem(
        name=work_id,
        description=description,
        status=status,
        created_at=utc_now_iso(),
    )
    atomic_write_text(item_path, _serialize_work_item(item))
    return item


def reconcile_work_store(state_root: Path) -> None:
    """Complete or clear an interrupted work-item rename operation."""

    paths = StateRootPaths.from_root_dir(state_root)
    intent_path = paths.work_items_rename_intent
    if not intent_path.is_file():
        return

    try:
        intent = WorkRenameIntent.model_validate_json(intent_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, json.JSONDecodeError):
        intent_path.unlink(missing_ok=True)
        return

    old_item_path = paths.work_items_dir / f"{intent.old_work_id}.json"
    new_item_path = paths.work_items_dir / f"{intent.new_work_id}.json"
    old_scratch_dir = _work_scratch_dir(paths, intent.old_work_id)
    new_scratch_dir = _work_scratch_dir(paths, intent.new_work_id)
    old_archived_dir = _archived_work_scratch_dir(paths, intent.old_work_id)
    new_archived_dir = _archived_work_scratch_dir(paths, intent.new_work_id)

    if old_item_path.exists() and not new_item_path.exists():
        new_item_path.parent.mkdir(parents=True, exist_ok=True)
        old_item_path.rename(new_item_path)

    if new_item_path.exists():
        # Repair metadata if a crash happened after renaming the file but before
        # rewriting the payload with the new slug.
        item = _read_work_item(new_item_path)
        if item is not None and item.name != intent.new_work_id:
            updated = item.model_copy(update={"name": intent.new_work_id})
            atomic_write_text(new_item_path, _serialize_work_item(updated))

        if old_scratch_dir.exists() and not new_scratch_dir.exists():
            new_scratch_dir.parent.mkdir(parents=True, exist_ok=True)
            old_scratch_dir.rename(new_scratch_dir)
        if old_archived_dir.exists() and not new_archived_dir.exists():
            new_archived_dir.parent.mkdir(parents=True, exist_ok=True)
            old_archived_dir.rename(new_archived_dir)

        intent_path.unlink(missing_ok=True)
        return

    intent_path.unlink(missing_ok=True)


def create_work_item(state_root: Path, label: str, description: str = "") -> WorkItem:
    """Create a new work item metadata record under `.meridian/work-items/`."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_items_flock):
        reconcile_work_store(state_root)
        paths.work_items_dir.mkdir(parents=True, exist_ok=True)
        slug = slugify(label)
        if not slug:
            raise ValueError("Work item label must contain at least one letter or number.")
        if get_work_item(state_root, slug) is not None:
            raise ValueError(f"Work item '{slug}' already exists. Use `meridian work switch {slug}`.")

        item = WorkItem(
            name=slug,
            description=description,
            status="open",
            created_at=utc_now_iso(),
        )
        atomic_write_text(paths.work_items_dir / f"{slug}.json", _serialize_work_item(item))
        return item


def ensure_work_item_metadata(
    state_root: Path,
    work_id: str,
    *,
    description: str = "",
    status: str = "open",
) -> WorkItem:
    """Ensure an exact work item slug exists on disk and return its metadata."""

    normalized = slugify(work_id)
    if not normalized or normalized != work_id:
        raise ValueError(
            f"Invalid work item name '{work_id}'. "
            f"Use a slug (lowercase, hyphens, no spaces) — e.g. '{normalized or 'my-feature'}'."
        )

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_items_flock):
        reconcile_work_store(state_root)
        return _ensure_work_item_metadata_locked(
            paths=paths,
            work_id=normalized,
            description=description,
            status=status,
        )


def get_work_item(state_root: Path, work_id: str) -> WorkItem | None:
    """Load one work item from `.meridian/work-items/<id>.json`."""

    path = _work_item_path(state_root, work_id)
    if not path.is_file():
        return None
    return _read_work_item(path)


def work_scratch_dir(state_root: Path, work_id: str) -> Path:
    """Return the current scratch location for a work item."""

    paths = StateRootPaths.from_root_dir(state_root)
    return _locate_work_scratch_dir(paths, work_id) or _work_scratch_dir(paths, work_id)


def list_work_items(state_root: Path) -> list[WorkItem]:
    """Return all work items sorted by creation time then slug."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_items_flock):
        reconcile_work_store(state_root)
        if not paths.work_items_dir.is_dir():
            return []

        items: list[WorkItem] = []
        for child in paths.work_items_dir.glob("*.json"):
            item = _read_work_item(child)
            if item is not None:
                items.append(item)
        return sorted(items, key=lambda item: (item.created_at, item.name))


def rename_work_item(state_root: Path, old_work_id: str, new_name: str) -> WorkItem:
    """Rename work metadata and move scratch dir if it exists."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_items_flock):
        reconcile_work_store(state_root)

        old_item = get_work_item(state_root, old_work_id)
        if old_item is None:
            raise ValueError(f"Work item '{old_work_id}' not found")

        normalized = slugify(new_name)
        if not normalized or normalized != new_name:
            raise ValueError(
                f"Invalid work item name '{new_name}'. "
                f"Use a slug (lowercase, hyphens, no spaces) — e.g. '{normalized or 'my-feature'}'."
            )
        if normalized == old_work_id:
            return old_item

        old_item_path = paths.work_items_dir / f"{old_work_id}.json"
        new_item_path = paths.work_items_dir / f"{normalized}.json"
        if new_item_path.exists():
            raise ValueError(f"Work item '{normalized}' already exists.")

        old_scratch_dir = _work_scratch_dir(paths, old_work_id)
        new_scratch_dir = _work_scratch_dir(paths, normalized)
        old_archived_dir = _archived_work_scratch_dir(paths, old_work_id)
        new_archived_dir = _archived_work_scratch_dir(paths, normalized)
        if old_scratch_dir.exists() and new_scratch_dir.exists():
            raise ValueError(
                f"Cannot rename work item '{old_work_id}' to '{normalized}': "
                f"scratch dir '{new_scratch_dir.as_posix()}' already exists."
            )
        if old_archived_dir.exists() and new_archived_dir.exists():
            raise ValueError(
                f"Cannot rename work item '{old_work_id}' to '{normalized}': "
                f"archived scratch dir '{new_archived_dir.as_posix()}' already exists."
            )

        intent = WorkRenameIntent(
            old_work_id=old_work_id,
            new_work_id=normalized,
            started_at=utc_now_iso(),
        )
        atomic_write_text(paths.work_items_rename_intent, intent.model_dump_json(indent=2) + "\n")

        old_item_path.rename(new_item_path)
        if old_scratch_dir.exists():
            new_scratch_dir.parent.mkdir(parents=True, exist_ok=True)
            old_scratch_dir.rename(new_scratch_dir)
        if old_archived_dir.exists():
            new_archived_dir.parent.mkdir(parents=True, exist_ok=True)
            old_archived_dir.rename(new_archived_dir)
        updated = old_item.model_copy(update={"name": normalized})
        atomic_write_text(new_item_path, _serialize_work_item(updated))
        paths.work_items_rename_intent.unlink(missing_ok=True)
        return updated


def update_work_item(
    state_root: Path,
    work_id: str,
    *,
    status: str | None = None,
    description: str | None = None,
) -> WorkItem:
    """Update mutable work-item fields and rewrite metadata atomically."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_items_flock):
        reconcile_work_store(state_root)
        current = get_work_item(state_root, work_id)
        if current is None:
            raise ValueError(f"Work item '{work_id}' not found")

        updated = current.model_copy(
            update={
                "status": current.status if status is None else status,
                "description": current.description if description is None else description,
            }
        )
        atomic_write_text(_work_item_path(state_root, work_id), _serialize_work_item(updated))
        return updated


def archive_work_item(state_root: Path, work_id: str) -> WorkItem:
    """Mark a work item done and move its scratch dir into `.meridian/work-archive/`."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_items_flock):
        reconcile_work_store(state_root)
        current = get_work_item(state_root, work_id)
        if current is None:
            raise ValueError(f"Work item '{work_id}' not found")

        active_dir = _work_scratch_dir(paths, work_id)
        archived_dir = _archived_work_scratch_dir(paths, work_id)
        if active_dir.exists() and archived_dir.exists():
            raise ValueError(
                f"Work item '{work_id}' has scratch dirs in both active and archive locations."
            )
        if active_dir.exists():
            archived_dir.parent.mkdir(parents=True, exist_ok=True)
            active_dir.rename(archived_dir)

        updated = current.model_copy(update={"status": "done"})
        atomic_write_text(_work_item_path(state_root, work_id), _serialize_work_item(updated))
        return updated


def reopen_work_item(state_root: Path, work_id: str, *, status: str = "open") -> WorkItem:
    """Reopen a work item and restore its scratch dir to `.meridian/work/`."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_items_flock):
        reconcile_work_store(state_root)
        current = get_work_item(state_root, work_id)
        if current is None:
            raise ValueError(f"Work item '{work_id}' not found")

        active_dir = _work_scratch_dir(paths, work_id)
        archived_dir = _archived_work_scratch_dir(paths, work_id)
        if active_dir.exists() and archived_dir.exists():
            raise ValueError(
                f"Work item '{work_id}' has scratch dirs in both active and archive locations."
            )
        if archived_dir.exists():
            active_dir.parent.mkdir(parents=True, exist_ok=True)
            archived_dir.rename(active_dir)

        updated = current.model_copy(update={"status": status})
        atomic_write_text(_work_item_path(state_root, work_id), _serialize_work_item(updated))
        return updated
