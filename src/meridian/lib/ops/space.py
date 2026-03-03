"""Space operations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from meridian.lib.ops._runtime import build_runtime
from meridian.lib.ops.registry import OperationSpec, operation
from meridian.lib.space import crud as space_crud
from meridian.lib.space import space_file
from meridian.lib.space.launch import SpaceLaunchRequest, launch_primary
from meridian.lib.space.summary import generate_space_summary
from meridian.lib.state import spawn_store
from meridian.lib.state.paths import resolve_space_dir
from meridian.lib.types import SpaceId

if TYPE_CHECKING:
    from meridian.lib.formatting import FormatContext


@dataclass(frozen=True, slots=True)
class SpaceStartInput:
    name: str | None = None
    model: str = ""
    agent: str | None = None
    autocompact: int | None = None
    harness_args: tuple[str, ...] = ()
    dry_run: bool = False
    repo_root: str | None = None
    permission_tier: str | None = None
    unsafe: bool = False


@dataclass(frozen=True, slots=True)
class SpaceResumeInput:
    space: str | None = None
    fresh: bool = False
    model: str = ""
    agent: str | None = None
    autocompact: int | None = None
    harness_args: tuple[str, ...] = ()
    repo_root: str | None = None
    permission_tier: str | None = None
    unsafe: bool = False


@dataclass(frozen=True, slots=True)
class SpaceListInput:
    limit: int = 10
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class SpaceShowInput:
    space: str
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class SpaceCloseInput:
    space: str
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class SpaceActionOutput:
    space_id: str
    state: str
    message: str
    exit_code: int | None = None
    command: tuple[str, ...] = ()
    lock_path: str | None = None
    summary_path: str | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Single-line action summary for text output mode."""
        summary = f"Space {self.space_id} {self.state} ({self.message.rstrip('.')})"
        if not self.command:
            return summary
        # Show the full command for dry-run so it can be copy-pasted.
        import shlex
        return f"{summary}\n{shlex.join(self.command)}"


@dataclass(frozen=True, slots=True)
class SpaceListEntry:
    space_id: str
    state: str
    name: str | None

    def as_row(self) -> list[str]:
        """Return columnar cells for tabular alignment."""
        return [self.space_id, self.state, self.name if self.name is not None else "-"]


@dataclass(frozen=True, slots=True)
class SpaceListOutput:
    spaces: tuple[SpaceListEntry, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Columnar list of spaces for text output mode."""
        if not self.spaces:
            return "(no spaces)"
        from meridian.cli.format_helpers import tabular

        return tabular([entry.as_row() for entry in self.spaces])


@dataclass(frozen=True, slots=True)
class SpaceDetailOutput:
    space_id: str
    state: str
    name: str | None
    summary_path: str | None
    pinned_files: tuple[str, ...]
    spawn_ids: tuple[str, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Key-value detail view for text output mode. Omits None/empty fields."""
        from meridian.cli.format_helpers import kv_block

        pairs: list[tuple[str, str | None]] = [
            ("Space", self.space_id),
            ("State", self.state),
            ("Name", self.name),
            ("Pinned", ", ".join(self.pinned_files) if self.pinned_files else None),
            ("Runs", ", ".join(self.spawn_ids) if self.spawn_ids else None),
        ]
        return kv_block(pairs)


def space_start_sync(payload: SpaceStartInput) -> SpaceActionOutput:
    runtime = build_runtime(payload.repo_root)
    space = space_file.create_space(runtime.repo_root, name=payload.name)

    summary_path = generate_space_summary(
        repo_root=runtime.repo_root,
        space_id=SpaceId(space.id),
    )

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
            unsafe=payload.unsafe,
        ),
    )
    transitioned = space_file.update_space_status(
        runtime.repo_root,
        space.id,
        launch_result.final_state,
    )

    return SpaceActionOutput(
        space_id=space.id,
        state=transitioned.status,
        message=("Space launch dry-run." if payload.dry_run else "Space session finished."),
        exit_code=launch_result.exit_code,
        command=launch_result.command if payload.dry_run else (),
        lock_path=launch_result.lock_path.as_posix(),
        summary_path=summary_path.as_posix(),
    )


async def space_start(payload: SpaceStartInput) -> SpaceActionOutput:
    return await asyncio.to_thread(space_start_sync, payload)


def space_resume_sync(payload: SpaceResumeInput) -> SpaceActionOutput:
    runtime = build_runtime(payload.repo_root)
    space_id = space_crud.resolve_space_for_resume(runtime.repo_root, payload.space)
    space = space_crud.get_space_or_raise(runtime.repo_root, space_id)

    # Resume reopens a closed space — only reject truly invalid states.
    # (Currently the only states are "active" and "closed", so no rejection needed.)

    summary_path = generate_space_summary(
        repo_root=runtime.repo_root,
        space_id=space.space_id,
    )

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
            unsafe=payload.unsafe,
        ),
    )

    transitioned = space_file.update_space_status(
        runtime.repo_root,
        space.space_id,
        launch_result.final_state,
    )

    return SpaceActionOutput(
        space_id=str(space.space_id),
        state=transitioned.status,
        message=("Space resumed (fresh)." if payload.fresh else "Space resumed."),
        exit_code=launch_result.exit_code,
        command=(),
        lock_path=launch_result.lock_path.as_posix(),
        summary_path=summary_path.as_posix(),
    )


async def space_resume(payload: SpaceResumeInput) -> SpaceActionOutput:
    return await asyncio.to_thread(space_resume_sync, payload)


def space_list_sync(payload: SpaceListInput) -> SpaceListOutput:
    runtime = build_runtime(payload.repo_root)
    summaries = sorted(
        space_file.list_spaces(runtime.repo_root),
        key=lambda item: item.created_at,
        reverse=True,
    )
    limit = payload.limit if payload.limit > 0 else 10
    return SpaceListOutput(
        spaces=tuple(
            SpaceListEntry(
                space_id=space.id,
                state=space.status,
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
    space = space_file.get_space(runtime.repo_root, space_id)
    if space is None:
        raise ValueError(f"Space '{space_id}' not found")

    space_dir = resolve_space_dir(runtime.repo_root, space_id)
    spawns = spawn_store.list_spawns(space_dir)
    summary_candidate = generate_space_summary(repo_root=runtime.repo_root, space_id=space_id)
    summary_path: str | None = summary_candidate.as_posix() if summary_candidate.is_file() else None

    return SpaceDetailOutput(
        space_id=space.id,
        state=space.status,
        name=space.name,
        summary_path=summary_path,
        pinned_files=(),
        spawn_ids=tuple(run.id for run in spawns),
    )


async def space_show(payload: SpaceShowInput) -> SpaceDetailOutput:
    return await asyncio.to_thread(space_show_sync, payload)


def space_close_sync(payload: SpaceCloseInput) -> SpaceActionOutput:
    runtime = build_runtime(payload.repo_root)
    space_id = SpaceId(payload.space.strip())

    transitioned = space_file.update_space_status(runtime.repo_root, space_id, "closed")
    summary_path = generate_space_summary(
        repo_root=runtime.repo_root,
        space_id=space_id,
    )
    return SpaceActionOutput(
        space_id=str(space_id),
        state=transitioned.status,
        message="Space closed.",
        summary_path=summary_path.as_posix(),
    )


async def space_close(payload: SpaceCloseInput) -> SpaceActionOutput:
    return await asyncio.to_thread(space_close_sync, payload)


operation(
    OperationSpec[SpaceStartInput, SpaceActionOutput](
        name="space.start",
        handler=space_start,
        sync_handler=space_start_sync,
        input_type=SpaceStartInput,
        output_type=SpaceActionOutput,
        cli_group="space",
        cli_name="start",
        mcp_name="space_start",
        description="Create a space and launch the primary agent harness.",
        cli_only=True,
    )
)

operation(
    OperationSpec[SpaceResumeInput, SpaceActionOutput](
        name="space.resume",
        handler=space_resume,
        sync_handler=space_resume_sync,
        input_type=SpaceResumeInput,
        output_type=SpaceActionOutput,
        cli_group="space",
        cli_name="resume",
        mcp_name="space_resume",
        description="Resume a space.",
        cli_only=True,
    )
)

operation(
    OperationSpec[SpaceListInput, SpaceListOutput](
        name="space.list",
        handler=space_list,
        sync_handler=space_list_sync,
        input_type=SpaceListInput,
        output_type=SpaceListOutput,
        cli_group="space",
        cli_name="list",
        mcp_name="space_list",
        description="List spaces.",
        cli_only=True,
    )
)

operation(
    OperationSpec[SpaceShowInput, SpaceDetailOutput](
        name="space.show",
        handler=space_show,
        sync_handler=space_show_sync,
        input_type=SpaceShowInput,
        output_type=SpaceDetailOutput,
        cli_group="space",
        cli_name="show",
        mcp_name="space_show",
        description="Show one space.",
        cli_only=True,
    )
)

operation(
    OperationSpec[SpaceCloseInput, SpaceActionOutput](
        name="space.close",
        handler=space_close,
        sync_handler=space_close_sync,
        input_type=SpaceCloseInput,
        output_type=SpaceActionOutput,
        cli_group="space",
        cli_name="close",
        mcp_name="space_close",
        description="Close a space.",
        cli_only=True,
    )
)
