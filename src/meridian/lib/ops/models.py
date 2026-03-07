"""Model alias and discovery operations."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from meridian.lib.config.aliases import AliasEntry, load_merged_aliases, resolve_model
from meridian.lib.config.discovery import DiscoveredModel, load_discovered_models, refresh_models_cache
from meridian.lib.config.routing import route_model
from meridian.lib.ops.registry import OperationSpec, operation
from meridian.lib.types import HarnessId, ModelId

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
class CatalogModel:
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
    is_latest: bool = False

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
            ("Capabilities", capabilities),
            ("Released", self.release_date),
            ("Cost input", _format_float(self.cost_input)),
            ("Cost output", _format_float(self.cost_output)),
            ("Context limit", _format_int(self.context_limit)),
            ("Output limit", _format_int(self.output_limit)),
        ]
        return kv_block(pairs)


@dataclass(frozen=True, slots=True)
class ModelsListOutput:
    models: tuple[CatalogModel, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Columnar model table for text output mode."""
        if not self.models:
            return "(no models)"
        from meridian.cli.format_helpers import tabular

        rows = [
            [
                str(model.model_id),
                str(model.harness),
                ",".join(alias.alias for alias in model.aliases),
                model.provider or "",
                f"{model.name or ''} (latest)" if model.is_latest else (model.name or ""),
                model.release_date or "",
            ]
            for model in self.models
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


def _format_float(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:g}"


def _format_int(value: int | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _format_alias_detail(alias: AliasEntry) -> str:
    details: list[str] = [alias.alias]
    if alias.role:
        details.append(f"role={alias.role}")
    if alias.strengths:
        details.append(f"strengths={alias.strengths}")
    return " ".join(details)


def _build_catalog_model(
    *,
    model_id: str,
    discovered: DiscoveredModel | None,
    aliases: list[AliasEntry],
) -> CatalogModel:
    if discovered is not None:
        harness = discovered.harness
    elif aliases:
        harness = aliases[0].harness
    else:
        harness = route_model(model_id).harness_id

    sorted_aliases = tuple(sorted(aliases, key=lambda entry: entry.alias))

    return CatalogModel(
        model_id=ModelId(model_id),
        harness=harness,
        aliases=sorted_aliases,
        name=discovered.name if discovered is not None else None,
        family=discovered.family if discovered is not None else None,
        provider=discovered.provider if discovered is not None else None,
        cost_input=discovered.cost_input if discovered is not None else None,
        cost_output=discovered.cost_output if discovered is not None else None,
        context_limit=discovered.context_limit if discovered is not None else None,
        output_limit=discovered.output_limit if discovered is not None else None,
        capabilities=discovered.capabilities if discovered is not None else (),
        release_date=discovered.release_date if discovered is not None else None,
    )


_DATE_SUFFIX_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^(?P<base>.+)-(?P<date>\d{8})$"),
    re.compile(r"^(?P<base>.+)-(?P<date>\d{4}-\d{2}-\d{2})$"),
    re.compile(r"^(?P<base>.+)-(?P<date>\d{2}-\d{2})$"),
    re.compile(r"^(?P<base>.+)-(?P<date>\d{2}-\d{4})$"),
)


def _date_variant_bases(model_id: str) -> tuple[str, ...]:
    for pattern in _DATE_SUFFIX_PATTERNS:
        match = pattern.match(model_id)
        if match is None:
            continue
        base = match.group("base")
        candidates: list[str] = [base]
        # Anthropic uses `claude-opus-4-0` as canonical but the date-stamped
        # variant is `claude-opus-4-20250514` (base = `claude-opus-4`).
        # Also check `{base}-0` so the variant gets filtered.
        candidates.append(f"{base}-0")
        if base.endswith("-preview"):
            candidates.append(base.removesuffix("-preview"))
        return tuple(candidates)
    return ()


def _is_default_visible(model: CatalogModel, all_model_ids: set[str]) -> bool:
    if model.aliases:
        return True

    model_id = str(model.model_id)

    if model_id == "gpt-4" or model_id.startswith(("gpt-4-", "gpt-4o")):
        return False
    if model_id.startswith(("o1", "o3", "o4")):
        return False
    if model_id.startswith("codex-mini"):
        return False
    if model_id.startswith(("gemini-1.", "gemini-2.0")):
        return False
    if model_id.startswith("claude-3-"):
        return False

    if model_id.endswith("-latest"):
        return False
    if "-chat-latest" in model_id:
        return False
    if "-deep-research" in model_id:
        return False
    if model_id.startswith("gemini-live-"):
        return False

    variant_bases = _date_variant_bases(model_id)
    if variant_bases and any(base in all_model_ids for base in variant_bases):
        return False

    return True


def _tag_latest_per_provider(models: list[CatalogModel]) -> list[CatalogModel]:
    """Mark the most recently released model per provider with ``is_latest``."""
    latest_date_by_provider: dict[str, str] = {}
    for model in models:
        provider = model.provider or str(model.harness)
        if model.release_date and (
            provider not in latest_date_by_provider
            or model.release_date > latest_date_by_provider[provider]
        ):
            latest_date_by_provider[provider] = model.release_date

    return [
        replace(model, is_latest=True)
        if (
            model.release_date is not None
            and model.release_date == latest_date_by_provider.get(model.provider or str(model.harness))
        )
        else model
        for model in models
    ]


def models_list_sync(payload: ModelsListInput) -> ModelsListOutput:
    root = _repo_root(payload.repo_root)
    aliases = load_merged_aliases(repo_root=root)
    discovered = load_discovered_models()

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
        )
        for model_id in sorted(model_ids)
    ]
    if not payload.all:
        all_model_ids = {str(model.model_id) for model in merged_models}
        merged_models = [
            model for model in merged_models if _is_default_visible(model, all_model_ids)
        ]
    merged_models = _tag_latest_per_provider(merged_models)
    return ModelsListOutput(models=tuple(merged_models))


def models_show_sync(payload: ModelsShowInput) -> CatalogModel:
    model_name = payload.model.strip()
    if not model_name:
        raise ValueError("Model identifier must not be empty.")

    root = _repo_root(payload.repo_root)
    aliases = load_merged_aliases(repo_root=root)
    discovered = load_discovered_models()
    discovered_by_model_id = {model.id: model for model in discovered}

    by_alias = {entry.alias: entry for entry in aliases}
    resolved_alias = by_alias.get(model_name)
    if resolved_alias is not None:
        target_model_id = str(resolved_alias.model_id)
        model_aliases = [entry for entry in aliases if str(entry.model_id) == target_model_id]
        return _build_catalog_model(
            model_id=target_model_id,
            discovered=discovered_by_model_id.get(target_model_id),
            aliases=model_aliases,
        )

    discovered_match = discovered_by_model_id.get(model_name)
    if discovered_match is not None:
        model_aliases = [entry for entry in aliases if str(entry.model_id) == model_name]
        return _build_catalog_model(
            model_id=model_name,
            discovered=discovered_match,
            aliases=model_aliases,
        )

    resolved = resolve_model(model_name, repo_root=root)
    target_model_id = str(resolved.model_id)
    model_aliases = [entry for entry in aliases if str(entry.model_id) == target_model_id]
    return _build_catalog_model(
        model_id=target_model_id,
        discovered=discovered_by_model_id.get(target_model_id),
        aliases=model_aliases,
    )


def models_refresh_sync(payload: ModelsRefreshInput) -> ModelsRefreshOutput:
    _ = payload
    refreshed = refresh_models_cache()
    return ModelsRefreshOutput(refreshed=len(refreshed))


async def models_list(payload: ModelsListInput) -> ModelsListOutput:
    return models_list_sync(payload)


async def models_show(payload: ModelsShowInput) -> CatalogModel:
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
    OperationSpec[ModelsShowInput, CatalogModel](
        name="models.show",
        handler=models_show,
        sync_handler=models_show_sync,
        input_type=ModelsShowInput,
        output_type=CatalogModel,
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
