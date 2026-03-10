"""Directory-backed work item store under `.meridian/work/`."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from meridian.lib.state.atomic import atomic_write_text

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


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _work_item_path(state_root: Path, work_id: str) -> Path:
    return state_root / "work" / work_id / "work.json"


def _serialize_work_item(item: WorkItem) -> str:
    return json.dumps(item.model_dump(), indent=2, sort_keys=True) + "\n"


def create_work_item(state_root: Path, label: str, description: str = "") -> WorkItem:
    """Create a new work item directory and `work.json` payload."""

    work_dir = state_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    while True:
        slug = _resolve_slug(work_dir, label)
        item_dir = work_dir / slug
        try:
            item_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            continue

        item = WorkItem(
            name=slug,
            description=description,
            status="open",
            created_at=_utc_now_iso(),
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

    work_dir = state_root / "work"
    if not work_dir.is_dir():
        return []

    items: list[WorkItem] = []
    for child in work_dir.iterdir():
        if not child.is_dir():
            continue
        item = get_work_item(state_root, child.name)
        if item is not None:
            items.append(item)
    return sorted(items, key=lambda item: (item.created_at, item.name))


def update_work_item(
    state_root: Path,
    work_id: str,
    *,
    status: str | None = None,
    description: str | None = None,
) -> WorkItem:
    """Update mutable work-item fields and rewrite `work.json` atomically."""

    current = get_work_item(state_root, work_id)
    if current is None:
        raise KeyError(work_id)

    updated = current.model_copy(
        update={
            "status": current.status if status is None else status,
            "description": current.description if description is None else description,
        }
    )
    atomic_write_text(_work_item_path(state_root, work_id), _serialize_work_item(updated))
    return updated
