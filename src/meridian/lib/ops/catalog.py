"""Catalog discovery operations for models and skills."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_serializer

from meridian.lib.catalog.model_aliases import (
    load_mars_descriptions,
)
from meridian.lib.catalog.model_policy import DEFAULT_MODEL_VISIBILITY, ModelVisibilityConfig
from meridian.lib.catalog.models import (
    AliasEntry,
    DiscoveredModel,
    compute_superseded_ids,
    is_default_visible_model,
    load_discovered_models,
    load_merged_aliases,
    refresh_models_cache,
    resolve_model,
)
from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.core.util import FormatContext
from meridian.lib.ops.runtime import async_from_sync


class ModelsListInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None
    all: bool = False
    show_superseded: bool = False


class ModelsRefreshInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class CatalogModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    model_id: ModelId
    harness: HarnessId
    aliases: tuple[AliasEntry, ...] = ()
    name: str | None = None
    family: str | None = None
    provider: str | None = None
    cost_input: float | None = None
    cost_output: float | None = None
    context_limit: int | None = None
    output_limit: int | None = None
    capabilities: tuple[str, ...] = ()
    release_date: str | None = None
    cost_tier: str | None = None
    description: str | None = None
    pinned: bool = False

    def to_wire(self) -> dict[str, object]:
        """Compact JSON projection for model listings."""
        wire: dict[str, object] = {
            "model_id": str(self.model_id),
            "harness": str(self.harness),
        }

        aliases = [alias.model_dump(exclude_none=True) for alias in self.aliases]
        if aliases:
            wire["aliases"] = aliases

        if self.name and self.name.strip():
            wire["name"] = self.name
        if self.family and self.family.strip():
            wire["family"] = self.family
        if self.provider and self.provider.strip():
            wire["provider"] = self.provider
        if self.cost_input is not None:
            wire["cost_input"] = self.cost_input
        if self.cost_output is not None:
            wire["cost_output"] = self.cost_output
        if self.context_limit is not None:
            wire["context_limit"] = self.context_limit
        if self.output_limit is not None:
            wire["output_limit"] = self.output_limit
        if self.capabilities:
            wire["capabilities"] = list(self.capabilities)
        if self.release_date and self.release_date.strip():
            wire["release_date"] = self.release_date
        if self.cost_tier and self.cost_tier.strip():
            wire["cost_tier"] = self.cost_tier
        if self.description and self.description.strip():
            wire["description"] = self.description
        if self.pinned:
            wire["pinned"] = True

        return wire

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        from meridian.cli.format_helpers import kv_block

        alias_names = ", ".join(alias.alias for alias in self.aliases) or None
        alias_details = ", ".join(_format_alias_detail(alias) for alias in self.aliases) or None
        capabilities = ", ".join(self.capabilities) or None
        pairs: list[tuple[str, str | None]] = [
            ("Model", str(self.model_id)),
            ("Harness", str(self.harness)),
            ("Name", self.name),
            ("Family", self.family),
            ("Provider", self.provider),
            ("Aliases", alias_names),
            ("Alias details", alias_details),
            ("Description", self.description),
            ("Capabilities", capabilities),
            ("Released", self.release_date),
            ("Cost", self.cost_tier),
            ("Cost input", _format_float(self.cost_input)),
            ("Cost output", _format_float(self.cost_output)),
            ("Context limit", _format_int(self.context_limit)),
            ("Output limit", _format_int(self.output_limit)),
        ]
        return kv_block(pairs)


class ModelsListOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    models: tuple[CatalogModel, ...]

    @model_serializer(mode="plain")
    def _serialize(self) -> dict[str, object]:
        return {"models": [model.to_wire() for model in self.models]}

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Columnar model table for text output mode."""
        if not self.models:
            return "(no models)"
        from meridian.cli.format_helpers import tabular

        header = ["MODEL", "HARNESS", "ALIAS", "PROVIDER", "COST", "RELEASED"]
        rows: list[list[str]] = []
        for model in self.models:
            rows.append([
                str(model.model_id),
                str(model.harness),
                ",".join(alias.alias for alias in model.aliases),
                model.provider or "",
                model.cost_tier or "",
                model.release_date or "",
            ])
        required_indices = {0, 1}
        keep_indices = [
            index
            for index in range(len(header))
            if index in required_indices or any(row[index] for row in rows)
        ]
        filtered_header = [header[index] for index in keep_indices]
        filtered_rows = [[row[index] for index in keep_indices] for row in rows]
        table = tabular([filtered_header, *filtered_rows])

        # Add description sub-lines
        table_lines = table.split("\n")
        result_lines: list[str] = []
        # First line is header
        if table_lines:
            result_lines.append(table_lines[0])
        # Remaining lines correspond to models
        for i, model in enumerate(self.models):
            line_index = i + 1
            if line_index < len(table_lines):
                result_lines.append(table_lines[line_index])
            if model.description:
                # Indent description under the model line
                result_lines.append(f"  {model.description}")
        return "\n".join(result_lines)


class ModelsRefreshOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    refreshed: int

    def format_text(self, ctx: FormatContext | None = None) -> str:
        return f"Refreshed models.dev cache ({self.refreshed} models)."


def _repo_root(repo_root: str | None) -> Path | None:
    explicit = Path(repo_root).expanduser().resolve() if repo_root is not None else None
    return resolve_repo_root(explicit)


def _format_float(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:g}"


def _format_int(value: int | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _format_alias_detail(alias: AliasEntry) -> str:
    return alias.alias


def _build_catalog_model(
    *,
    model_id: str,
    discovered: DiscoveredModel | None,
    aliases: list[AliasEntry],
    repo_root: Path | None,
    description: str | None = None,
    pinned: bool = False,
) -> CatalogModel:
    try:
        harness = resolve_model(model_id, repo_root=repo_root).harness
    except ValueError:
        if discovered is not None:
            harness = discovered.harness
        elif aliases:
            harness = aliases[0].harness
        else:
            raise

    sorted_aliases = tuple(sorted(aliases, key=lambda entry: entry.alias))

    cost_input = discovered.cost_input if discovered is not None else None

    return CatalogModel(
        model_id=ModelId(model_id),
        harness=harness,
        aliases=sorted_aliases,
        name=discovered.name if discovered is not None else None,
        family=discovered.family if discovered is not None else None,
        provider=discovered.provider if discovered is not None else None,
        cost_input=cost_input,
        cost_output=discovered.cost_output if discovered is not None else None,
        context_limit=discovered.context_limit if discovered is not None else None,
        output_limit=discovered.output_limit if discovered is not None else None,
        capabilities=discovered.capabilities if discovered is not None else (),
        release_date=discovered.release_date if discovered is not None else None,
        cost_tier=_cost_tier(cost_input),
        description=description,
        pinned=pinned,
    )

def _is_default_visible(
    model: CatalogModel,
    all_model_ids: set[str],
    *,
    visibility: ModelVisibilityConfig,
    superseded_model_ids: frozenset[str] = frozenset(),
) -> bool:
    return is_default_visible_model(
        model_id=str(model.model_id),
        pinned=model.pinned or bool(model.aliases),
        release_date=model.release_date,
        cost_input=model.cost_input,
        all_model_ids=all_model_ids,
        visibility=visibility,
        superseded_model_ids=superseded_model_ids,
    )


def _cost_tier(cost_input: float | None) -> str | None:
    """Map input cost ($/M tokens) to a human-readable tier."""
    if cost_input is None:
        return None
    if cost_input < 1.0:
        return "$"
    if cost_input < 5.0:
        return "$$"
    extra_dollar_count = int((cost_input - 5.0) // 5.0)
    return "$" * (3 + extra_dollar_count)


def models_list_sync(payload: ModelsListInput) -> ModelsListOutput:
    root = _repo_root(payload.repo_root)
    aliases = load_merged_aliases(repo_root=root)
    visibility = DEFAULT_MODEL_VISIBILITY
    discovered = load_discovered_models()

    # Load descriptions from mars aliases and alias entries
    mars_descs = load_mars_descriptions(root)
    alias_descs: dict[str, str] = {}
    pinned_ids: set[str] = set()
    for alias in aliases:
        if alias.description:
            alias_descs[str(alias.model_id)] = alias.description
    descriptions = {**mars_descs, **alias_descs}

    aliases_by_model_id: dict[str, list[AliasEntry]] = {}
    for alias in aliases:
        aliases_by_model_id.setdefault(str(alias.model_id), []).append(alias)

    discovered_by_model_id = {model.id: model for model in discovered}
    model_ids = set(aliases_by_model_id) | set(discovered_by_model_id)

    merged_models = [
        _build_catalog_model(
            model_id=model_id,
            discovered=discovered_by_model_id.get(model_id),
            aliases=aliases_by_model_id.get(model_id, []),
            repo_root=root,
            description=descriptions.get(model_id),
            pinned=model_id in pinned_ids,
        )
        for model_id in sorted(model_ids)
    ]
    if not payload.all:
        all_model_ids = {str(model.model_id) for model in merged_models}

        effective_visibility = visibility
        if payload.show_superseded:
            effective_visibility = visibility.model_copy(
                update={"hide_superseded": False}
            )

        superseded: frozenset[str] = frozenset()
        if effective_visibility.hide_superseded:
            superseded = compute_superseded_ids([
                (str(m.model_id), m.provider or "", m.release_date)
                for m in merged_models
            ])

        merged_models = [
            model
            for model in merged_models
            if _is_default_visible(
                model,
                all_model_ids,
                visibility=effective_visibility,
                superseded_model_ids=superseded,
            )
        ]
    return ModelsListOutput(models=tuple(merged_models))


def models_refresh_sync(payload: ModelsRefreshInput) -> ModelsRefreshOutput:
    _ = payload
    refreshed = refresh_models_cache()
    return ModelsRefreshOutput(refreshed=len(refreshed))


models_list = async_from_sync(models_list_sync)
models_refresh = async_from_sync(models_refresh_sync)
