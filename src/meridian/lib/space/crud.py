"""Space CRUD helpers backed by `space.json` files."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from meridian.lib.domain import Space
from meridian.lib.space import space_file
from meridian.lib.space.space_file import SpaceRecord
from meridian.lib.types import SpaceId


def _space_sort_key(record: SpaceRecord) -> tuple[str, int, str]:
    suffix = record.id[1:] if record.id.startswith("s") else ""
    numeric_id = int(suffix) if suffix.isdigit() else -1
    return (record.created_at, numeric_id, record.id)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _to_space(record: SpaceRecord) -> Space:
    return Space(
        space_id=SpaceId(record.id),
        created_at=_parse_iso_datetime(record.created_at) or datetime.now(UTC),
        name=record.name,
    )


def create_space(repo_root: Path, *, name: str | None = None) -> Space:
    """Create one space record."""

    return _to_space(space_file.create_space(repo_root, name=name))


def get_space_or_raise(repo_root: Path, space_id: SpaceId) -> Space:
    """Fetch a space and raise when it does not exist."""

    record = space_file.get_space(repo_root, space_id)
    if record is None:
        raise ValueError(f"Space '{space_id}' not found")
    return _to_space(record)


def resolve_space_for_resume(repo_root: Path, space: str | None) -> SpaceId:
    """Resolve resume target from explicit value or most-recent space."""

    if space is not None and space.strip():
        return SpaceId(space.strip())

    spaces = space_file.list_spaces(repo_root)
    if not spaces:
        raise ValueError("No space available to resume.")
    latest = max(spaces, key=_space_sort_key)
    return SpaceId(latest.id)
