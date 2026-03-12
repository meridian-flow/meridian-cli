"""Directory-backed work item store under `.meridian/work/`."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from coolname.impl import generate_slug

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
    auto_generated: bool = False


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


def _resolve_slug(work_dir: Path, label: str) -> str:
    """Resolve a unique slug within `work_dir` by appending numeric suffixes."""

    base = slugify(label) or "work"
    candidate = base
    counter = 2
    while (work_dir / candidate).exists():
        suffix = f"-{counter}"
        candidate = f"{base[: _MAX_SLUG_LENGTH - len(suffix)].rstrip('-')}{suffix}"
        counter += 1
    return candidate


def generate_auto_name() -> str:
    """Return a random three-word slug for auto-generated work items."""
    return generate_slug(3)


def _work_item_path(state_root: Path, work_id: str) -> Path:
    return state_root / "work" / work_id / "work.json"


def _serialize_work_item(item: WorkItem) -> str:
    return json.dumps(item.model_dump(), indent=2, sort_keys=True) + "\n"


def reconcile_work_store(state_root: Path) -> None:
    """Complete or clear an interrupted work-item rename operation."""

    paths = StateRootPaths.from_root_dir(state_root)
    intent_path = paths.work_rename_intent
    if not intent_path.is_file():
        return

    try:
        intent = WorkRenameIntent.model_validate_json(intent_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, json.JSONDecodeError):
        intent_path.unlink(missing_ok=True)
        return

    old_dir = paths.work_dir / intent.old_work_id
    new_dir = paths.work_dir / intent.new_work_id

    if old_dir.exists() and not new_dir.exists():
        old_dir.rename(new_dir)
        item = get_work_item(state_root, intent.new_work_id)
        if item is not None:
            updated = item.model_copy(update={"name": intent.new_work_id})
            atomic_write_text(new_dir / "work.json", _serialize_work_item(updated))
        intent_path.unlink(missing_ok=True)
        return

    if new_dir.exists():
        # Repair work.json if it still carries the old name (crash between
        # directory rename and JSON rewrite).
        item = get_work_item(state_root, intent.new_work_id)
        if item is not None and item.name != intent.new_work_id:
            updated = item.model_copy(update={"name": intent.new_work_id})
            atomic_write_text(new_dir / "work.json", _serialize_work_item(updated))
        intent_path.unlink(missing_ok=True)
        return

    intent_path.unlink(missing_ok=True)


def create_work_item(state_root: Path, label: str, description: str = "") -> WorkItem:
    """Create a new work item directory and `work.json` payload."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_lock):
        reconcile_work_store(state_root)
        paths.work_dir.mkdir(parents=True, exist_ok=True)

        while True:
            slug = _resolve_slug(paths.work_dir, label)
            item_dir = paths.work_dir / slug
            try:
                item_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                continue

            item = WorkItem(
                name=slug,
                description=description,
                status="open",
                created_at=utc_now_iso(),
            )
            atomic_write_text(item_dir / "work.json", _serialize_work_item(item))
            return item


def create_auto_work_item(state_root: Path) -> WorkItem:
    """Create an auto-generated work item with a random name."""
    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_lock):
        reconcile_work_store(state_root)
        paths.work_dir.mkdir(parents=True, exist_ok=True)

        while True:
            name = generate_auto_name()
            slug = _resolve_slug(paths.work_dir, name)
            item_dir = paths.work_dir / slug
            try:
                item_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                continue

            item = WorkItem(
                name=slug,
                description="",
                status="open",
                created_at=utc_now_iso(),
                auto_generated=True,
            )
            atomic_write_text(item_dir / "work.json", _serialize_work_item(item))
            return item


def get_work_item(state_root: Path, work_id: str) -> WorkItem | None:
    """Load one work item from `.meridian/work/<id>/work.json`."""

    path = _work_item_path(state_root, work_id)
    if not path.is_file():
        return None
    try:
        return WorkItem.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, json.JSONDecodeError):
        return None


def list_work_items(state_root: Path) -> list[WorkItem]:
    """Return all work items sorted by creation time then slug."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_lock):
        reconcile_work_store(state_root)
        if not paths.work_dir.is_dir():
            return []

        items: list[WorkItem] = []
        for child in paths.work_dir.iterdir():
            if not child.is_dir():
                continue
            item = get_work_item(state_root, child.name)
            if item is not None:
                items.append(item)
        return sorted(items, key=lambda item: (item.created_at, item.name))


def rename_work_item(state_root: Path, old_work_id: str, new_name: str) -> WorkItem:
    """Rename a work item: move directory, update work.json, return updated item.

    ``new_name`` must be a valid slug (the target folder name), not a
    human-readable label.  Spaces and special characters are rejected.
    """
    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_lock):
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

        new_dir = paths.work_dir / normalized
        old_dir = paths.work_dir / old_work_id
        if new_dir.exists():
            raise ValueError(f"Work item '{normalized}' already exists.")

        intent = WorkRenameIntent(
            old_work_id=old_work_id,
            new_work_id=normalized,
            started_at=utc_now_iso(),
        )
        atomic_write_text(paths.work_rename_intent, intent.model_dump_json(indent=2) + "\n")

        old_dir.rename(new_dir)
        updated = old_item.model_copy(update={"name": normalized})
        atomic_write_text(new_dir / "work.json", _serialize_work_item(updated))
        paths.work_rename_intent.unlink(missing_ok=True)
        return updated


def update_work_item(
    state_root: Path,
    work_id: str,
    *,
    status: str | None = None,
    description: str | None = None,
    auto_generated: bool | None = None,
) -> WorkItem:
    """Update mutable work-item fields and rewrite `work.json` atomically."""

    paths = StateRootPaths.from_root_dir(state_root)
    with lock_file(paths.work_lock):
        reconcile_work_store(state_root)
        current = get_work_item(state_root, work_id)
        if current is None:
            raise ValueError(f"Work item '{work_id}' not found")

        updated = current.model_copy(
            update={
                "status": current.status if status is None else status,
                "description": current.description if description is None else description,
                "auto_generated": current.auto_generated if auto_generated is None else auto_generated,
            }
        )
        atomic_write_text(_work_item_path(state_root, work_id), _serialize_work_item(updated))
        return updated
