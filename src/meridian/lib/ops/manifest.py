"""Explicit operation manifest shared by CLI and MCP surfaces."""

from collections.abc import Callable, Coroutine
from typing import Any, Generic, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from meridian.lib.ops.catalog import (
    ModelsListInput,
    ModelsListOutput,
    ModelsRefreshInput,
    ModelsRefreshOutput,
    models_list,
    models_list_sync,
    models_refresh,
    models_refresh_sync,
)
from meridian.lib.ops.config import (
    ConfigGetInput,
    ConfigGetOutput,
    ConfigInitInput,
    ConfigInitOutput,
    ConfigResetInput,
    ConfigResetOutput,
    ConfigSetInput,
    ConfigSetOutput,
    ConfigShowInput,
    ConfigShowOutput,
    config_get,
    config_get_sync,
    config_init,
    config_init_sync,
    config_reset,
    config_reset_sync,
    config_set,
    config_set_sync,
    config_show,
    config_show_sync,
)
from meridian.lib.ops.context import (
    ContextInput,
    ContextOutput,
    WorkCurrentInput,
    WorkCurrentOutput,
    context,
    context_sync,
    work_current,
    work_current_sync,
)
from meridian.lib.ops.diag import DoctorInput, DoctorOutput, doctor, doctor_sync
from meridian.lib.ops.report import (
    ReportSearchInput,
    ReportSearchOutput,
    ReportShowInput,
    ReportShowOutput,
    report_search,
    report_search_sync,
    report_show,
    report_show_sync,
)
from meridian.lib.ops.session_log import (
    SessionLogInput,
    SessionLogOutput,
    session_log,
    session_log_sync,
)
from meridian.lib.ops.session_search import (
    SessionSearchInput,
    SessionSearchOutput,
    session_search,
    session_search_sync,
)
from meridian.lib.ops.spawn.api import (
    SpawnActionOutput,
    SpawnCancelInput,
    SpawnContinueInput,
    SpawnCreateInput,
    SpawnDetailOutput,
    SpawnListInput,
    SpawnListOutput,
    SpawnShowInput,
    SpawnStatsInput,
    SpawnStatsOutput,
    SpawnWaitInput,
    SpawnWaitMultiOutput,
    SpawnWrittenFilesInput,
    SpawnWrittenFilesOutput,
    spawn_cancel,
    spawn_cancel_sync,
    spawn_continue,
    spawn_continue_sync,
    spawn_create,
    spawn_create_sync,
    spawn_files,
    spawn_files_sync,
    spawn_list,
    spawn_list_sync,
    spawn_show,
    spawn_show_sync,
    spawn_stats,
    spawn_stats_sync,
    spawn_wait,
    spawn_wait_sync,
)
from meridian.lib.ops.spawn.log import (
    SpawnLogInput,
    SpawnLogOutput,
    spawn_log,
    spawn_log_sync,
)
from meridian.lib.ops.work_dashboard import (
    WorkListInput,
    WorkListOutput,
    WorkSessionsInput,
    WorkSessionsOutput,
    WorkShowInput,
    WorkShowOutput,
    work_list,
    work_list_sync,
    work_sessions,
    work_sessions_sync,
    work_show,
    work_show_sync,
)
from meridian.lib.ops.work_lifecycle import (
    WorkClearInput,
    WorkClearOutput,
    WorkDeleteInput,
    WorkDeleteOutput,
    WorkDoneInput,
    WorkRenameInput,
    WorkRenameOutput,
    WorkReopenInput,
    WorkReopenOutput,
    WorkStartInput,
    WorkStartOutput,
    WorkSwitchInput,
    WorkSwitchOutput,
    WorkUpdateInput,
    WorkUpdateOutput,
    work_clear,
    work_clear_sync,
    work_delete,
    work_delete_sync,
    work_done,
    work_done_sync,
    work_rename,
    work_rename_sync,
    work_reopen,
    work_reopen_sync,
    work_start,
    work_start_sync,
    work_switch,
    work_switch_sync,
    work_update,
    work_update_sync,
)
from meridian.lib.ops.workspace import (
    WorkspaceInitInput,
    WorkspaceInitOutput,
    workspace_init,
    workspace_init_sync,
)

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
OperationSurface = Literal["cli", "mcp"]


class OperationSpec(BaseModel, Generic[InputT, OutputT]):
    """Single explicit definition for one Meridian operation."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    description: str
    handler: Callable[[InputT], Coroutine[Any, Any, OutputT]]
    input_type: type[InputT]
    output_type: type[OutputT]
    cli_group: str | None = None
    cli_name: str | None = None
    mcp_name: str | None = None
    version: str = "1"
    sync_handler: Callable[[InputT], OutputT] | None = None
    surfaces: frozenset[OperationSurface] = frozenset({"cli", "mcp"})

    @model_validator(mode="after")
    def _validate_surface_metadata(self) -> Self:
        if not self.surfaces:
            raise ValueError(f"Operation '{self.name}' must expose at least one surface")
        if "cli" in self.surfaces and (not self.cli_group or not self.cli_name):
            raise ValueError(f"Operation '{self.name}' is missing CLI metadata")
        if "mcp" in self.surfaces and not self.mcp_name:
            raise ValueError(f"Operation '{self.name}' is missing MCP metadata")
        return self

    def enabled_on(self, surface: OperationSurface) -> bool:
        return surface in self.surfaces

    @property
    def cli_only(self) -> bool:
        return self.surfaces == frozenset({"cli"})

    @property
    def mcp_only(self) -> bool:
        return self.surfaces == frozenset({"mcp"})


OperationSpec.model_rebuild()


def _spec(
    *,
    name: str,
    description: str,
    handler: Callable[[InputT], Coroutine[Any, Any, OutputT]],
    sync_handler: Callable[[InputT], OutputT] | None,
    input_type: type[InputT],
    output_type: type[OutputT],
    cli_group: str | None,
    cli_name: str | None,
    mcp_name: str | None,
    surfaces: frozenset[OperationSurface] = frozenset({"cli", "mcp"}),
) -> OperationSpec[InputT, OutputT]:
    return OperationSpec(
        name=name,
        description=description,
        handler=handler,
        sync_handler=sync_handler,
        input_type=input_type,
        output_type=output_type,
        cli_group=cli_group,
        cli_name=cli_name,
        mcp_name=mcp_name,
        surfaces=surfaces,
    )


_OPERATIONS: tuple[OperationSpec[Any, Any], ...] = (
    _spec(
        name="config.get",
        description="Get one resolved config key with source annotation.",
        handler=config_get,
        sync_handler=config_get_sync,
        input_type=ConfigGetInput,
        output_type=ConfigGetOutput,
        cli_group="config",
        cli_name="get",
        mcp_name="config_get",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="config.init",
        description="Scaffold meridian.toml with commented defaults.",
        handler=config_init,
        sync_handler=config_init_sync,
        input_type=ConfigInitInput,
        output_type=ConfigInitOutput,
        cli_group="config",
        cli_name="init",
        mcp_name="config_init",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="config.reset",
        description="Remove one config key from file overrides.",
        handler=config_reset,
        sync_handler=config_reset_sync,
        input_type=ConfigResetInput,
        output_type=ConfigResetOutput,
        cli_group="config",
        cli_name="reset",
        mcp_name="config_reset",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="config.set",
        description="Set one config key in meridian.toml.",
        handler=config_set,
        sync_handler=config_set_sync,
        input_type=ConfigSetInput,
        output_type=ConfigSetOutput,
        cli_group="config",
        cli_name="set",
        mcp_name="config_set",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="config.show",
        description="Show resolved config values with source annotations.",
        handler=config_show,
        sync_handler=config_show_sync,
        input_type=ConfigShowInput,
        output_type=ConfigShowOutput,
        cli_group="config",
        cli_name="show",
        mcp_name="config_show",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="workspace.init",
        description="Create local workspace.local.toml with commented examples.",
        handler=workspace_init,
        sync_handler=workspace_init_sync,
        input_type=WorkspaceInitInput,
        output_type=WorkspaceInitOutput,
        cli_group="workspace",
        cli_name="init",
        mcp_name="workspace_init",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="doctor",
        description="Health check and orphan reconciliation.",
        handler=doctor,
        sync_handler=doctor_sync,
        input_type=DoctorInput,
        output_type=DoctorOutput,
        cli_group="doctor",
        cli_name="doctor",
        mcp_name="doctor",
    ),
    _spec(
        name="models.list",
        description="List catalog models with routing guidance.",
        handler=models_list,
        sync_handler=models_list_sync,
        input_type=ModelsListInput,
        output_type=ModelsListOutput,
        cli_group="models",
        cli_name="list",
        mcp_name="models_list",
    ),
    _spec(
        name="models.refresh",
        description="Force-refresh the models.dev cache.",
        handler=models_refresh,
        sync_handler=models_refresh_sync,
        input_type=ModelsRefreshInput,
        output_type=ModelsRefreshOutput,
        cli_group="models",
        cli_name="refresh",
        mcp_name="models_refresh",
    ),
    _spec(
        name="report.search",
        description="Search spawn reports by keyword.",
        handler=report_search,
        sync_handler=report_search_sync,
        input_type=ReportSearchInput,
        output_type=ReportSearchOutput,
        cli_group="report",
        cli_name="search",
        mcp_name="report_search",
    ),
    _spec(
        name="report.show",
        description="Show one spawn report.",
        handler=report_show,
        sync_handler=report_show_sync,
        input_type=ReportShowInput,
        output_type=ReportShowOutput,
        cli_group="report",
        cli_name="show",
        mcp_name="report_show",
    ),
    _spec(
        name="session.log",
        description="Show readable messages from a harness session JSONL.",
        handler=session_log,
        sync_handler=session_log_sync,
        input_type=SessionLogInput,
        output_type=SessionLogOutput,
        cli_group="session",
        cli_name="log",
        mcp_name="session_log",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="session.search",
        description="Search a session transcript for case-insensitive text matches.",
        handler=session_search,
        sync_handler=session_search_sync,
        input_type=SessionSearchInput,
        output_type=SessionSearchOutput,
        cli_group="session",
        cli_name="search",
        mcp_name="session_search",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="spawn.cancel",
        description="Cancel a running spawn.",
        handler=spawn_cancel,
        sync_handler=spawn_cancel_sync,
        input_type=SpawnCancelInput,
        output_type=SpawnActionOutput,
        cli_group="spawn",
        cli_name="cancel",
        mcp_name=None,
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="spawn.files",
        description="List edited files for a spawn, one per line. Pipe to git add or xargs.",
        handler=spawn_files,
        sync_handler=spawn_files_sync,
        input_type=SpawnWrittenFilesInput,
        output_type=SpawnWrittenFilesOutput,
        cli_group="spawn",
        cli_name="files",
        mcp_name="spawn_files",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="spawn.log",
        description="Show recent assistant messages extracted from a spawn's output.jsonl.",
        handler=spawn_log,
        sync_handler=spawn_log_sync,
        input_type=SpawnLogInput,
        output_type=SpawnLogOutput,
        cli_group="spawn",
        cli_name="log",
        mcp_name="spawn_log",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="spawn.children",
        description="List child spawns for a parent spawn id.",
        handler=spawn_list,
        sync_handler=spawn_list_sync,
        input_type=SpawnListInput,
        output_type=SpawnListOutput,
        cli_group="spawn",
        cli_name="children",
        mcp_name="spawn_children",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="spawn.continue",
        description="Continue a previous spawn.",
        handler=spawn_continue,
        sync_handler=spawn_continue_sync,
        input_type=SpawnContinueInput,
        output_type=SpawnActionOutput,
        cli_group="spawn",
        cli_name="continue",
        mcp_name="spawn_continue",
        surfaces=frozenset({"mcp"}),
    ),
    _spec(
        name="spawn.create",
        description="Create and start a spawn.",
        handler=spawn_create,
        sync_handler=spawn_create_sync,
        input_type=SpawnCreateInput,
        output_type=SpawnActionOutput,
        cli_group="spawn",
        cli_name="create",
        mcp_name="spawn_create",
        surfaces=frozenset({"mcp"}),
    ),
    _spec(
        name="spawn.list",
        description="List recent spawns (default: active). Filter by --view, --status, or --model.",
        handler=spawn_list,
        sync_handler=spawn_list_sync,
        input_type=SpawnListInput,
        output_type=SpawnListOutput,
        cli_group="spawn",
        cli_name="list",
        mcp_name="spawn_list",
    ),
    _spec(
        name="spawn.show",
        description=(
            "Show spawn status, duration, model, report path, and report text by default. "
            "Use --no-report to omit report text."
        ),
        handler=spawn_show,
        sync_handler=spawn_show_sync,
        input_type=SpawnShowInput,
        output_type=SpawnDetailOutput,
        cli_group="spawn",
        cli_name="show",
        mcp_name="spawn_show",
    ),
    _spec(
        name="spawn.stats",
        description="Show total runs, success/fail counts, cost, and duration.",
        handler=spawn_stats,
        sync_handler=spawn_stats_sync,
        input_type=SpawnStatsInput,
        output_type=SpawnStatsOutput,
        cli_group="spawn",
        cli_name="stats",
        mcp_name="spawn_stats",
    ),
    _spec(
        name="spawn.wait",
        description="Block until spawn(s) complete and return terminal status details.",
        handler=spawn_wait,
        sync_handler=spawn_wait_sync,
        input_type=SpawnWaitInput,
        output_type=SpawnWaitMultiOutput,
        cli_group="spawn",
        cli_name="wait",
        mcp_name="spawn_wait",
    ),
    _spec(
        name="work.clear",
        description="Clear the active work item for the current session when available.",
        handler=work_clear,
        sync_handler=work_clear_sync,
        input_type=WorkClearInput,
        output_type=WorkClearOutput,
        cli_group="work",
        cli_name="clear",
        mcp_name="work_clear",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.done",
        description="Mark a work item as done and archive its scratch directory when present.",
        handler=work_done,
        sync_handler=work_done_sync,
        input_type=WorkDoneInput,
        output_type=WorkUpdateOutput,
        cli_group="work",
        cli_name="done",
        mcp_name="work_done",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.delete",
        description=(
            "Delete a work item. Fails when scratch artifacts exist unless --force is provided."
        ),
        handler=work_delete,
        sync_handler=work_delete_sync,
        input_type=WorkDeleteInput,
        output_type=WorkDeleteOutput,
        cli_group="work",
        cli_name="delete",
        mcp_name="work_delete",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.reopen",
        description=(
            "Reopen a done work item and restore its archived scratch directory when present."
        ),
        handler=work_reopen,
        sync_handler=work_reopen_sync,
        input_type=WorkReopenInput,
        output_type=WorkReopenOutput,
        cli_group="work",
        cli_name="reopen",
        mcp_name="work_reopen",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.list",
        description=(
            'List work items. Use --done / --no-done to control whether'
            ' items with status "done" are shown.'
        ),
        handler=work_list,
        sync_handler=work_list_sync,
        input_type=WorkListInput,
        output_type=WorkListOutput,
        cli_group="work",
        cli_name="list",
        mcp_name="work_list",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.rename",
        description="Rename a work item. Updates the slug, directory, and all spawn associations.",
        handler=work_rename,
        sync_handler=work_rename_sync,
        input_type=WorkRenameInput,
        output_type=WorkRenameOutput,
        cli_group="work",
        cli_name="rename",
        mcp_name="work_rename",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.show",
        description="Show one work item, its directory, and associated spawns.",
        handler=work_show,
        sync_handler=work_show_sync,
        input_type=WorkShowInput,
        output_type=WorkShowOutput,
        cli_group="work",
        cli_name="show",
        mcp_name="work_show",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.sessions",
        description=(
            "List sessions associated with a work item. "
            "Default shows active sessions; use --all for historical."
        ),
        handler=work_sessions,
        sync_handler=work_sessions_sync,
        input_type=WorkSessionsInput,
        output_type=WorkSessionsOutput,
        cli_group="work",
        cli_name="sessions",
        mcp_name="work_sessions",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.start",
        description=(
            "Create a work item if missing, or switch to it if it already exists and is active."
        ),
        handler=work_start,
        sync_handler=work_start_sync,
        input_type=WorkStartInput,
        output_type=WorkStartOutput,
        cli_group="work",
        cli_name="start",
        mcp_name="work_start",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.switch",
        description="Set the active work item for the current session when available.",
        handler=work_switch,
        sync_handler=work_switch_sync,
        input_type=WorkSwitchInput,
        output_type=WorkSwitchOutput,
        cli_group="work",
        cli_name="switch",
        mcp_name="work_switch",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.update",
        description="Update a work item's status and/or description.",
        handler=work_update,
        sync_handler=work_update_sync,
        input_type=WorkUpdateInput,
        output_type=WorkUpdateOutput,
        cli_group="work",
        cli_name="update",
        mcp_name="work_update",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="context",
        description=(
            "Query runtime context: work_dir, fs_dir, repo_root, "
            "state_root, depth, context_roots."
        ),
        handler=context,
        sync_handler=context_sync,
        input_type=ContextInput,
        output_type=ContextOutput,
        cli_group="context",
        cli_name="context",
        mcp_name="context",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="work.current",
        description="Return the current work directory path (or empty if none attached).",
        handler=work_current,
        sync_handler=work_current_sync,
        input_type=WorkCurrentInput,
        output_type=WorkCurrentOutput,
        cli_group="work",
        cli_name="current",
        mcp_name="work_current",
        surfaces=frozenset({"cli"}),
    ),
)


def _build_operation_index() -> dict[str, OperationSpec[Any, Any]]:
    by_name: dict[str, OperationSpec[Any, Any]] = {}
    cli_commands: set[tuple[str, str]] = set()
    mcp_names: set[str] = set()
    for spec in _OPERATIONS:
        if spec.name in by_name:
            raise ValueError(f"Duplicate operation name '{spec.name}' in manifest")
        by_name[spec.name] = spec
        if spec.enabled_on("cli"):
            cli_command = (spec.cli_group or "", spec.cli_name or "")
            if cli_command in cli_commands:
                raise ValueError(
                    f"Duplicate CLI command '{cli_command[0]}.{cli_command[1]}' in manifest"
                )
            cli_commands.add(cli_command)
        if spec.enabled_on("mcp"):
            if spec.mcp_name in mcp_names:
                raise ValueError(f"Duplicate MCP tool name '{spec.mcp_name}' in manifest")
            if spec.mcp_name is not None:
                mcp_names.add(spec.mcp_name)
    return by_name


_OPERATIONS_BY_NAME = _build_operation_index()


def get_all_operations() -> list[OperationSpec[Any, Any]]:
    """Return all operations sorted by canonical name."""

    return [_OPERATIONS_BY_NAME[name] for name in sorted(_OPERATIONS_BY_NAME)]


def get_operation(name: str) -> OperationSpec[Any, Any]:
    """Fetch one operation spec by canonical name."""

    return _OPERATIONS_BY_NAME[name]


def get_operations_for_surface(surface: OperationSurface) -> list[OperationSpec[Any, Any]]:
    """Return operations exposed on one surface, sorted by canonical name."""

    return [spec for spec in get_all_operations() if spec.enabled_on(surface)]


def get_mcp_tool_names() -> frozenset[str]:
    """Return MCP tool names declared in the manifest."""

    return frozenset(
        spec.mcp_name for spec in get_operations_for_surface("mcp") if spec.mcp_name is not None
    )


__all__ = [
    "OperationSpec",
    "OperationSurface",
    "get_all_operations",
    "get_mcp_tool_names",
    "get_operation",
    "get_operations_for_surface",
]
