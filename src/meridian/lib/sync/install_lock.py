"""Resolved install lock models and JSON I/O."""

from __future__ import annotations

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.sync.install_types import SourceKind, normalize_required_string, parse_item_id
from meridian.lib.sync.install_types import validate_source_name


class LockedSourceItem(BaseModel):
    """One exported item snapshot recorded in `.meridian/agents.lock`."""

    model_config = ConfigDict(frozen=True)

    path: str

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str) -> str:
        return normalize_required_string(value, source="path")


class LockedSourceRecord(BaseModel):
    """One locked source resolution and exported snapshot."""

    model_config = ConfigDict(frozen=True)

    kind: SourceKind
    locator: str
    requested_ref: str | None = None
    resolved_identity: dict[str, object] = Field(default_factory=dict)
    items: dict[str, LockedSourceItem] = Field(default_factory=dict)
    realized_closure: tuple[str, ...] = ()
    installed_tree_hash: str | None = None
    installed_at: str | None = None

    @field_validator("locator")
    @classmethod
    def _validate_locator(cls, value: str) -> str:
        return normalize_required_string(value, source="locator")

    @field_validator("requested_ref", "installed_tree_hash", "installed_at")
    @classmethod
    def _validate_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_required_string(value, source="lock")

    @field_validator("realized_closure")
    @classmethod
    def _validate_realized_closure(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item_id in value:
            parse_item_id(item_id)
        return value

    @model_validator(mode="after")
    def _validate_item_keys(self) -> "LockedSourceRecord":
        for item_id in self.items:
            parse_item_id(item_id)
        return self


class LockedInstalledItem(BaseModel):
    """One installed destination ownership record."""

    model_config = ConfigDict(frozen=True)

    source_name: str
    source_item_id: str
    destination_path: str
    content_hash: str

    @field_validator("source_name")
    @classmethod
    def _validate_source_name(cls, value: str) -> str:
        return validate_source_name(value)

    @field_validator("source_item_id")
    @classmethod
    def _validate_source_item_id(cls, value: str) -> str:
        parse_item_id(value)
        return value

    @field_validator("destination_path", "content_hash")
    @classmethod
    def _validate_required_strings(cls, value: str) -> str:
        return normalize_required_string(value, source="lock")


class ManagedInstallLock(BaseModel):
    """Serialized `.meridian/agents.lock` content."""

    model_config = ConfigDict(frozen=True)

    version: int = 1
    sources: dict[str, LockedSourceRecord] = Field(default_factory=dict)
    items: dict[str, LockedInstalledItem] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_keys(self) -> "ManagedInstallLock":
        for source_name in self.sources:
            validate_source_name(source_name)
        for item_id in self.items:
            parse_item_id(item_id)
        return self


def read_install_lock(lock_path: Path) -> ManagedInstallLock:
    """Read `.meridian/agents.lock`."""

    try:
        raw = lock_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ManagedInstallLock()

    payload_obj = json.loads(raw)
    payload = cast("dict[str, object]", payload_obj)
    return ManagedInstallLock.model_validate(payload)


def write_install_lock(lock_path: Path, lock: ManagedInstallLock) -> None:
    """Write `.meridian/agents.lock` atomically."""

    atomic_write_text(
        lock_path,
        json.dumps(lock.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
    )


def _flock_path(lock_path: Path) -> Path:
    return lock_path.with_name(f"{lock_path.name}.flock")


@contextmanager
def lock_file_guard(lock_path: Path) -> Iterator[None]:
    """Acquire an exclusive advisory lock for an install state file."""

    flock_path = _flock_path(lock_path)
    flock_path.parent.mkdir(parents=True, exist_ok=True)
    with flock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
