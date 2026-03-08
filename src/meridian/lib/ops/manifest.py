"""Explicit operation manifest shared by CLI, MCP, and DirectAdapter surfaces."""


from collections.abc import Callable, Coroutine
from typing import Any, Generic, Literal, Self, TypeVar

from pydantic import BaseModel, ConfigDict, model_validator

from meridian.lib.core.domain import SkillContent
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
from meridian.lib.ops.diag import DoctorInput, DoctorOutput, doctor, doctor_sync
from meridian.lib.ops.catalog import (
    CatalogModel,
    ModelsListInput,
    ModelsListOutput,
    ModelsRefreshInput,
    ModelsRefreshOutput,
    ModelsShowInput,
    SkillsListInput,
    SkillsLoadInput,
    SkillsQueryOutput,
    SkillsSearchInput,
    models_list,
    models_list_sync,
    models_refresh,
    models_refresh_sync,
    models_show,
    models_show_sync,
    skills_list,
    skills_list_sync,
    skills_load,
    skills_load_sync,
    skills_search,
    skills_search_sync,
)
from meridian.lib.ops.report import (
    ReportCreateInput,
    ReportCreateOutput,
    ReportSearchInput,
    ReportSearchOutput,
    ReportShowInput,
    ReportShowOutput,
    report_create,
    report_create_sync,
    report_search,
    report_search_sync,
    report_show,
    report_show_sync,
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
    spawn_cancel,
    spawn_cancel_sync,
    spawn_continue,
    spawn_continue_sync,
    spawn_create,
    spawn_create_sync,
    spawn_list,
    spawn_list_sync,
    spawn_show,
    spawn_show_sync,
    spawn_stats,
    spawn_stats_sync,
    spawn_wait,
    spawn_wait_sync,
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
        if "cli" in self.surfaces:
            if not self.cli_group or not self.cli_name:
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
        description="Scaffold .meridian/config.toml with commented defaults.",
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
        description="Set one config key in .meridian/config.toml.",
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
        name="doctor",
        description="Spawn diagnostics checks.",
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
        name="models.show",
        description="Show one model by id or alias.",
        handler=models_show,
        sync_handler=models_show_sync,
        input_type=ModelsShowInput,
        output_type=CatalogModel,
        cli_group="models",
        cli_name="show",
        mcp_name="models_show",
    ),
    _spec(
        name="report.create",
        description="Create or overwrite a spawn report.",
        handler=report_create,
        sync_handler=report_create_sync,
        input_type=ReportCreateInput,
        output_type=ReportCreateOutput,
        cli_group="report",
        cli_name="create",
        mcp_name="report_create",
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
        name="skills.list",
        description="List all indexed skills.",
        handler=skills_list,
        sync_handler=skills_list_sync,
        input_type=SkillsListInput,
        output_type=SkillsQueryOutput,
        cli_group="skills",
        cli_name="list",
        mcp_name="skills_list",
    ),
    _spec(
        name="skills.search",
        description="Search skills by keyword/tag.",
        handler=skills_search,
        sync_handler=skills_search_sync,
        input_type=SkillsSearchInput,
        output_type=SkillsQueryOutput,
        cli_group="skills",
        cli_name="search",
        mcp_name="skills_search",
        surfaces=frozenset({"cli"}),
    ),
    _spec(
        name="skills.show",
        description="Load full SKILL.md content for a skill.",
        handler=skills_load,
        sync_handler=skills_load_sync,
        input_type=SkillsLoadInput,
        output_type=SkillContent,
        cli_group="skills",
        cli_name="show",
        mcp_name="skills_show",
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
        mcp_name="spawn_cancel",
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
        description="List recent spawns. Filter by --status or --model.",
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
        description="Show spawn status, duration, model, and report. Use --report to include report text.",
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
        description="Block until spawn(s) complete. Returns status and report by default.",
        handler=spawn_wait,
        sync_handler=spawn_wait_sync,
        input_type=SpawnWaitInput,
        output_type=SpawnWaitMultiOutput,
        cli_group="spawn",
        cli_name="wait",
        mcp_name="spawn_wait",
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
                raise ValueError(f"Duplicate CLI command '{cli_command[0]}.{cli_command[1]}' in manifest")
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
        spec.mcp_name
        for spec in get_operations_for_surface("mcp")
        if spec.mcp_name is not None
    )


__all__ = [
    "OperationSpec",
    "OperationSurface",
    "get_all_operations",
    "get_mcp_tool_names",
    "get_operation",
    "get_operations_for_surface",
]
