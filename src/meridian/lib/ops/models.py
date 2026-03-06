"""Model alias and discovery operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.config.catalog import AliasEntry, load_merged_aliases, resolve_model
from meridian.lib.config.discovery import DiscoveredModel, load_discovered_models, refresh_cache
from meridian.lib.ops.registry import OperationSpec, operation
from meridian.lib.types import ModelId

if TYPE_CHECKING:
    from meridian.lib.formatting import FormatContext


@dataclass(frozen=True, slots=True)
class ModelsListInput:
    repo_root: str | None = None
    all: bool = False


@dataclass(frozen=True, slots=True)
class ModelsShowInput:
    model: str = ""
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ModelsRefreshInput:
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ModelsListOutput:
    models: tuple[AliasEntry, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Columnar model table for text output mode."""
        if not self.models:
            return "(no models)"
        from meridian.cli.format_helpers import tabular

        rows = [
            [
                str(m.model_id),
                m.harness,
                f"({m.alias})" if m.alias else "",
                m.role,
            ]
            for m in self.models
        ]
        return tabular(rows)


@dataclass(frozen=True, slots=True)
class ModelsRefreshOutput:
    refreshed: int

    def format_text(self, ctx: FormatContext | None = None) -> str:
        return f"Refreshed models.dev cache ({self.refreshed} models)."


def _repo_root(repo_root: str | None) -> Path | None:
    if repo_root is None:
        return None
    return Path(repo_root).expanduser().resolve()


def _cost_tier(model: DiscoveredModel) -> str:
    costs = [cost for cost in (model.cost_input, model.cost_output) if cost is not None]
    if not costs:
        return ""
    highest_cost = max(costs)
    if highest_cost <= 1:
        return "$"
    if highest_cost <= 10:
        return "$$"
    return "$$$"


def _entry_from_discovered(model: DiscoveredModel) -> AliasEntry:
    return AliasEntry(
        model_id=ModelId(model.id),
        alias="",
        role=f"Discovered ({model.provider})",
        strengths=model.name,
        cost_tier=_cost_tier(model),
        harness=model.harness_id,
    )


def models_list_sync(payload: ModelsListInput) -> ModelsListOutput:
    root = _repo_root(payload.repo_root)
    aliases = load_merged_aliases(repo_root=root)
    if not payload.all:
        return ModelsListOutput(models=tuple(aliases))

    merged = list(aliases)
    known_model_ids = {str(entry.model_id) for entry in aliases}
    discovered = sorted(load_discovered_models(), key=lambda model: model.id)
    for model in discovered:
        if model.id in known_model_ids:
            continue
        merged.append(_entry_from_discovered(model))
    return ModelsListOutput(models=tuple(merged))


def models_show_sync(payload: ModelsShowInput) -> AliasEntry:
    model_name = payload.model.strip()
    if not model_name:
        raise ValueError("Model identifier must not be empty.")

    root = _repo_root(payload.repo_root)
    aliases = load_merged_aliases(repo_root=root)
    for entry in aliases:
        if model_name == entry.alias or model_name == str(entry.model_id):
            return entry

    for model in load_discovered_models():
        if model.id == model_name:
            return _entry_from_discovered(model)

    return resolve_model(model_name, repo_root=root)


def models_refresh_sync(payload: ModelsRefreshInput) -> ModelsRefreshOutput:
    _ = payload
    refreshed = refresh_cache()
    return ModelsRefreshOutput(refreshed=len(refreshed))


async def models_list(payload: ModelsListInput) -> ModelsListOutput:
    return models_list_sync(payload)


async def models_show(payload: ModelsShowInput) -> AliasEntry:
    return models_show_sync(payload)


async def models_refresh(payload: ModelsRefreshInput) -> ModelsRefreshOutput:
    return models_refresh_sync(payload)


operation(
    OperationSpec[ModelsListInput, ModelsListOutput](
        name="models.list",
        handler=models_list,
        sync_handler=models_list_sync,
        input_type=ModelsListInput,
        output_type=ModelsListOutput,
        cli_group="models",
        cli_name="list",
        mcp_name="models_list",
        description="List catalog models with routing guidance.",
    )
)

operation(
    OperationSpec[ModelsShowInput, AliasEntry](
        name="models.show",
        handler=models_show,
        sync_handler=models_show_sync,
        input_type=ModelsShowInput,
        output_type=AliasEntry,
        cli_group="models",
        cli_name="show",
        mcp_name="models_show",
        description="Show one model by id or alias.",
    )
)

operation(
    OperationSpec[ModelsRefreshInput, ModelsRefreshOutput](
        name="models.refresh",
        handler=models_refresh,
        sync_handler=models_refresh_sync,
        input_type=ModelsRefreshInput,
        output_type=ModelsRefreshOutput,
        cli_group="models",
        cli_name="refresh",
        mcp_name="models_refresh",
        description="Force-refresh the models.dev cache.",
    )
)
