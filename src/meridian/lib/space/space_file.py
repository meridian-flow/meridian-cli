"""File-backed space metadata CRUD for `.meridian/.spaces/<space-id>/space.json`."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from meridian.lib.state.id_gen import next_space_id
from meridian.lib.state.paths import SpacePaths, ensure_gitignore, resolve_all_spaces_dir, resolve_space_dir
from meridian.lib.types import SpaceId

_SPACE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SpaceRecord:
    """Serialized form of one space record."""

    schema_version: int
    id: str
    name: str | None
    created_at: str


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@contextmanager
def _lock_file(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_space_json(path: Path, record: SpaceRecord) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(asdict(record), handle, separators=(",", ":"), sort_keys=True)
        handle.write("\n")
    os.replace(tmp_path, path)


def _read_space_json(path: Path) -> SpaceRecord | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None

    raw_id = payload.get("id")
    raw_created = payload.get("created_at")
    if not isinstance(raw_id, str) or not raw_id.strip():
        return None
    if not isinstance(raw_created, str) or not raw_created.strip():
        return None

    return SpaceRecord(
        schema_version=int(payload.get("schema_version", _SPACE_SCHEMA_VERSION)),
        id=raw_id,
        name=payload.get("name") if payload.get("name") is None else str(payload.get("name")),
        created_at=raw_created,
    )


def create_space(repo_root: Path, name: str | None = None) -> SpaceRecord:
    """Create one new space and write `space.json`."""

    spaces_dir = resolve_all_spaces_dir(repo_root)
    spaces_dir.mkdir(parents=True, exist_ok=True)
    with _lock_file(spaces_dir / ".lock"):
        space_id = next_space_id(repo_root)
        space_dir = resolve_space_dir(repo_root, space_id)
        paths = SpacePaths.from_space_dir(space_dir)
        paths.fs_dir.mkdir(parents=True, exist_ok=False)

        record = SpaceRecord(
            schema_version=_SPACE_SCHEMA_VERSION,
            id=str(space_id),
            name=name,
            created_at=_utc_now_iso(),
        )
        _write_space_json(paths.space_json, record)

    ensure_gitignore(repo_root)
    return record


def get_space(repo_root: Path, space_id: SpaceId | str) -> SpaceRecord | None:
    """Load one `space.json` record."""

    path = SpacePaths.from_space_dir(resolve_space_dir(repo_root, space_id)).space_json
    return _read_space_json(path)


def list_spaces(repo_root: Path) -> list[SpaceRecord]:
    """Load all valid spaces from `.meridian/.spaces/*/space.json`."""

    spaces_dir = resolve_all_spaces_dir(repo_root)
    if not spaces_dir.exists():
        return []

    records: list[SpaceRecord] = []
    for child in sorted(spaces_dir.iterdir(), key=lambda path: path.name):
        if not child.is_dir():
            continue
        record = _read_space_json(SpacePaths.from_space_dir(child).space_json)
        if record is not None:
            records.append(record)
    return records
