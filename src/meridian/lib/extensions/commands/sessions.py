"""Session-related first-party extension commands."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from meridian.lib.extensions.context import (
    ExtensionCommandServices,
    ExtensionInvocationContext,
)
from meridian.lib.extensions.types import (
    ExtensionCommandSpec,
    ExtensionErrorResult,
    ExtensionJSONResult,
    ExtensionResult,
    ExtensionSurface,
)
from meridian.lib.ops.spawn.models import SpawnStatsOutput


class ArchiveSpawnArgs(BaseModel):
    """Arguments for meridian.sessions.archiveSpawn."""

    spawn_id: str = Field(description="ID of spawn to archive")


class ArchiveSpawnResult(BaseModel):
    """Result payload for meridian.sessions.archiveSpawn."""

    spawn_id: str
    archived: bool
    was_already_archived: bool = False


async def archive_spawn_handler(
    args: dict[str, Any],
    context: ExtensionInvocationContext,
    services: ExtensionCommandServices,
) -> ExtensionResult:
    """Archive a spawn ID in runtime state."""

    _ = context
    if services.runtime_root is None:
        return ExtensionErrorResult(
            code="service_unavailable",
            message="runtime_root not available",
        )

    from meridian.lib.spawn.archive import archive_spawn, is_spawn_archived

    spawn_id = args["spawn_id"]
    if is_spawn_archived(services.runtime_root, spawn_id):
        return ExtensionJSONResult(
            payload={
                "spawn_id": spawn_id,
                "archived": True,
                "was_already_archived": True,
            }
        )

    archive_spawn(services.runtime_root, spawn_id)
    return ExtensionJSONResult(payload={"spawn_id": spawn_id, "archived": True})


ARCHIVE_SPAWN_SPEC = ExtensionCommandSpec(
    extension_id="meridian.sessions",
    command_id="archiveSpawn",
    summary="Archive a completed spawn to hide it from default listings",
    args_schema=ArchiveSpawnArgs,
    result_schema=ArchiveSpawnResult,
    handler=archive_spawn_handler,
    surfaces=frozenset({ExtensionSurface.ALL}),
    first_party=True,
    requires_app_server=True,
)


class GetSpawnStatsArgs(BaseModel):
    """Arguments for meridian.sessions.getSpawnStats."""

    spawn_id: str = Field(description="ID of spawn to get stats for")


async def get_spawn_stats_handler(
    args: dict[str, Any],
    context: ExtensionInvocationContext,
    services: ExtensionCommandServices,
) -> ExtensionResult:
    """Wrap spawn_stats operation output for extension command surface."""

    _ = context
    if services.meridian_dir is None:
        return ExtensionErrorResult(
            code="service_unavailable",
            message="meridian_dir not available",
        )

    from meridian.lib.ops.spawn.api import spawn_stats_sync
    from meridian.lib.ops.spawn.models import SpawnStatsInput

    payload = SpawnStatsInput(
        spawn_id=args["spawn_id"],
        project_root=services.meridian_dir.parent.as_posix(),
    )
    result = spawn_stats_sync(payload)
    return ExtensionJSONResult(payload=result.model_dump())


GET_SPAWN_STATS_SPEC = ExtensionCommandSpec(
    extension_id="meridian.sessions",
    command_id="getSpawnStats",
    summary="Get token usage and cost statistics for a spawn",
    args_schema=GetSpawnStatsArgs,
    result_schema=SpawnStatsOutput,
    handler=get_spawn_stats_handler,
    surfaces=frozenset({ExtensionSurface.ALL}),
    first_party=True,
    requires_app_server=True,
)
