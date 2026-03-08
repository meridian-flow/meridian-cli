"""Space operations."""


import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from meridian.lib.core.domain import Space
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import build_runtime
from meridian.lib.space.launch import SpaceLaunchRequest, launch_primary
from meridian.lib.state.space_store import (
    SpaceRecord,
    create_space as create_space_record,
    get_space as get_space_record,
    list_spaces as list_space_records,
)
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.core.types import SpaceId


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

    return _to_space(create_space_record(repo_root, name=name))


def get_space_or_raise(repo_root: Path, space_id: SpaceId) -> Space:
    """Fetch a space and raise when it does not exist."""

    record = get_space_record(repo_root, space_id)
    if record is None:
        raise ValueError(f"Space '{space_id}' not found")
    return _to_space(record)


def resolve_space_for_resume(repo_root: Path, space: str | None) -> SpaceId:
    """Resolve resume target from explicit value or most-recent space."""

    if space is not None and space.strip():
        return SpaceId(space.strip())

    spaces = list_space_records(repo_root)
    if not spaces:
        raise ValueError("No space available to resume.")
    latest = max(spaces, key=_space_sort_key)
    return SpaceId(latest.id)


class SpaceStartInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str | None = None
    model: str = ""
    agent: str | None = None
    autocompact: int | None = None
    harness_args: tuple[str, ...] = ()
    dry_run: bool = False
    repo_root: str | None = None
    permission_tier: str | None = None
    approval: str = "confirm"


class SpaceResumeInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    space: str | None = None
    fresh: bool = False
    model: str = ""
    agent: str | None = None
    autocompact: int | None = None
    harness_args: tuple[str, ...] = ()
    repo_root: str | None = None
    permission_tier: str | None = None
    approval: str = "confirm"


class SpaceListInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    limit: int = 10
    repo_root: str | None = None


class SpaceShowInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    space: str
    repo_root: str | None = None


class SpaceActionOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    space_id: str
    message: str
    exit_code: int | None = None
    command: tuple[str, ...] = ()
    lock_path: str | None = None
    continue_ref: str | None = None
    resume_command: str | None = None
    warning: str | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Single-line action summary for text output mode."""
        summary = f"\n{self.message.rstrip('.')} (space {self.space_id})"
        if self.command:
            # Show the full command for dry-run so it can be copy-pasted.
            import shlex
            details = f"{summary}\n{shlex.join(self.command)}"
            if self.warning:
                return f"warning: {self.warning}\n{details}"
            return details
        if self.resume_command:
            details = f"{summary}\nContinue via meridian:\n{self.resume_command}"
            if self.warning:
                return f"warning: {self.warning}\n{details}"
            return details
        # Show the full command for dry-run so it can be copy-pasted.
        if self.warning:
            return f"warning: {self.warning}\n{summary}"
        return summary


class SpaceListEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    space_id: str
    name: str | None

    def as_row(self) -> list[str]:
        """Return columnar cells for tabular alignment."""
        return [self.space_id, self.name if self.name is not None else "-"]


class SpaceListOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    spaces: tuple[SpaceListEntry, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Columnar list of spaces for text output mode."""
        if not self.spaces:
            return "(no spaces)"
        from meridian.cli.format_helpers import tabular

        return tabular([entry.as_row() for entry in self.spaces])


class SpaceDetailOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    space_id: str
    name: str | None
    pinned_files: tuple[str, ...]
    spawn_ids: tuple[str, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Key-value detail view for text output mode. Omits None/empty fields."""
        from meridian.cli.format_helpers import kv_block

        pairs: list[tuple[str, str | None]] = [
            ("Space", self.space_id),
            ("Name", self.name),
            ("Pinned", ", ".join(self.pinned_files) if self.pinned_files else None),
            ("Runs", ", ".join(self.spawn_ids) if self.spawn_ids else None),
        ]
        return kv_block(pairs)


def space_start_sync(payload: SpaceStartInput) -> SpaceActionOutput:
    runtime = build_runtime(payload.repo_root)
    space = create_space_record(runtime.repo_root, name=payload.name)

    launch_result = launch_primary(
        repo_root=runtime.repo_root,
        request=SpaceLaunchRequest(
            space_id=SpaceId(space.id),
            model=payload.model,
            agent=payload.agent,
            autocompact=payload.autocompact,
            passthrough_args=payload.harness_args,
            fresh=True,
            pinned_context="",
            dry_run=payload.dry_run,
            permission_tier=payload.permission_tier,
            approval=payload.approval,
        ),
        harness_registry=runtime.harness_registry,
    )
    return SpaceActionOutput(
        space_id=space.id,
        message=("Launch dry-run." if payload.dry_run else "Session finished."),
        exit_code=launch_result.exit_code,
        command=launch_result.command if payload.dry_run else (),
        lock_path=launch_result.lock_path.as_posix(),
        continue_ref=launch_result.continue_ref,
        resume_command=(
            f"meridian --continue {launch_result.continue_ref}"
            if launch_result.continue_ref is not None
            else None
        ),
    )


async def space_start(payload: SpaceStartInput) -> SpaceActionOutput:
    return await asyncio.to_thread(space_start_sync, payload)


def space_resume_sync(payload: SpaceResumeInput) -> SpaceActionOutput:
    runtime = build_runtime(payload.repo_root)
    space_id = resolve_space_for_resume(runtime.repo_root, payload.space)
    space = get_space_or_raise(runtime.repo_root, space_id)

    launch_result = launch_primary(
        repo_root=runtime.repo_root,
        request=SpaceLaunchRequest(
            space_id=space.space_id,
            model=payload.model,
            agent=payload.agent,
            autocompact=payload.autocompact,
            passthrough_args=payload.harness_args,
            fresh=payload.fresh,
            pinned_context="",
            permission_tier=payload.permission_tier,
            approval=payload.approval,
        ),
        harness_registry=runtime.harness_registry,
    )

    return SpaceActionOutput(
        space_id=str(space.space_id),
        message=("Session resumed (fresh)." if payload.fresh else "Session resumed."),
        exit_code=launch_result.exit_code,
        command=(),
        lock_path=launch_result.lock_path.as_posix(),
        continue_ref=launch_result.continue_ref,
        resume_command=(
            f"meridian --continue {launch_result.continue_ref}"
            if launch_result.continue_ref is not None
            else None
        ),
    )


async def space_resume(payload: SpaceResumeInput) -> SpaceActionOutput:
    return await asyncio.to_thread(space_resume_sync, payload)


def space_list_sync(payload: SpaceListInput) -> SpaceListOutput:
    runtime = build_runtime(payload.repo_root)
    summaries = sorted(
        list_space_records(runtime.repo_root),
        key=lambda item: item.created_at,
        reverse=True,
    )
    limit = payload.limit if payload.limit > 0 else 10
    return SpaceListOutput(
        spaces=tuple(
            SpaceListEntry(
                space_id=space.id,
                name=space.name,
            )
            for space in summaries[:limit]
        )
    )


async def space_list(payload: SpaceListInput) -> SpaceListOutput:
    return await asyncio.to_thread(space_list_sync, payload)


def space_show_sync(payload: SpaceShowInput) -> SpaceDetailOutput:
    runtime = build_runtime(payload.repo_root)
    space_id = SpaceId(payload.space.strip())
    space = get_space_record(runtime.repo_root, space_id)
    if space is None:
        raise ValueError(f"Space '{space_id}' not found")

    space_dir = resolve_space_dir(runtime.repo_root, space_id)
    spawns = spawn_store.list_spawns(space_dir)

    return SpaceDetailOutput(
        space_id=space.id,
        name=space.name,
        pinned_files=(),
        spawn_ids=tuple(run.id for run in spawns),
    )


async def space_show(payload: SpaceShowInput) -> SpaceDetailOutput:
    return await asyncio.to_thread(space_show_sync, payload)
