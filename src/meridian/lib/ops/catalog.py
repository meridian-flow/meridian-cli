"""Catalog discovery operations for models and skills."""


import re
from datetime import date, timedelta
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_serializer

from meridian.lib.catalog.models import AliasEntry, load_merged_aliases, resolve_model
from meridian.lib.catalog.models import DiscoveredModel, load_discovered_models, refresh_models_cache
from meridian.lib.catalog.models import route_model
from meridian.lib.catalog.agent import scan_agent_profiles
from meridian.lib.catalog.skill import SkillRegistry
from meridian.lib.core.domain import SkillContent, SkillManifest
from meridian.lib.core.util import FormatContext
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.ops.runtime import async_from_sync


class ModelsListInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None
    all: bool = False


class ModelsShowInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = ""
    repo_root: str | None = None


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
        rows = [
            [
                str(model.model_id),
                str(model.harness),
                ",".join(alias.alias for alias in model.aliases),
                model.provider or "",
                model.cost_tier or "",
                model.release_date or "",
            ]
            for model in self.models
        ]
        required_indices = {0, 1}
        keep_indices = [
            index
            for index in range(len(header))
            if index in required_indices or any(row[index] for row in rows)
        ]
        filtered_header = [header[index] for index in keep_indices]
        filtered_rows = [[row[index] for index in keep_indices] for row in rows]
        return tabular([filtered_header] + filtered_rows)


class ModelsRefreshOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    refreshed: int

    def format_text(self, ctx: FormatContext | None = None) -> str:
        return f"Refreshed models.dev cache ({self.refreshed} models)."


class SkillsListInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class SkillsSearchInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    query: str = ""
    repo_root: str | None = None


class SkillsLoadInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = ""
    repo_root: str | None = None


class SkillsQueryOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    skills: tuple[SkillManifest, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """One skill per line: name + description for text output mode."""
        if not self.skills:
            return "(no skills)"
        from meridian.cli.format_helpers import tabular

        return tabular(
            [[skill.name, _truncate(skill.description, max_len=60)] for skill in self.skills]
        )


def _repo_root(repo_root: str | None) -> Path | None:
    if repo_root is None:
        return None
    return Path(repo_root).expanduser().resolve()


def _registry(repo_root: str | None, *, readonly: bool = False) -> SkillRegistry:
    return SkillRegistry(repo_root=_repo_root(repo_root), readonly=readonly)


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


def _truncate(text: str, *, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 3].rstrip()}..."


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


_DEFAULT_RECENCY_DAYS = 180


def _recency_cutoff() -> str:
    """Return YYYY-MM-DD string for the recency cutoff (6 months ago)."""
    return (date.today() - timedelta(days=_DEFAULT_RECENCY_DAYS)).isoformat()


def _is_default_visible(model: CatalogModel, all_model_ids: set[str]) -> bool:
    # Aliased models are always visible. User explicitly configured them.
    if model.aliases:
        return True

    model_id = str(model.model_id)

    # Noise reduction: redundant variants.
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

    if model.release_date and model.release_date < _recency_cutoff():
        return False

    # o-series reasoning models do not work with the codex harness.
    if model_id.startswith(("o1", "o3", "o4")):
        return False

    # Hide expensive models ($$$$+) from the default listing.
    if model.cost_input is not None and model.cost_input >= 10.0:
        return False

    return True


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


def skills_list_sync(payload: SkillsListInput) -> SkillsQueryOutput:
    registry = _registry(payload.repo_root, readonly=True)
    return SkillsQueryOutput(skills=tuple(registry.list_skills()))


def skills_search_sync(payload: SkillsSearchInput) -> SkillsQueryOutput:
    registry = _registry(payload.repo_root, readonly=True)
    return SkillsQueryOutput(skills=tuple(registry.search(payload.query)))


def skills_load_sync(payload: SkillsLoadInput) -> SkillContent:
    name = payload.name.strip()
    if not name:
        raise ValueError("Skill name must not be empty.")
    registry = _registry(payload.repo_root, readonly=True)
    return registry.show(name)


models_list = async_from_sync(models_list_sync)
models_show = async_from_sync(models_show_sync)
models_refresh = async_from_sync(models_refresh_sync)
skills_list = async_from_sync(skills_list_sync)
skills_search = async_from_sync(skills_search_sync)
skills_load = async_from_sync(skills_load_sync)


# ---------------------------------------------------------------------------
# Agents catalog
# ---------------------------------------------------------------------------


class AgentsListInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class AgentListEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    model: str | None
    skills: tuple[str, ...]
    sandbox: str | None


class AgentsListOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    agents: tuple[AgentListEntry, ...]

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """One agent per line: name, model, description for text output mode."""
        if not self.agents:
            return "(no agents)"
        from meridian.cli.format_helpers import tabular

        return tabular(
            [
                [
                    agent.name,
                    agent.model or "-",
                    agent.description,
                ]
                for agent in self.agents
            ]
        )


def agents_list_sync(payload: AgentsListInput) -> AgentsListOutput:
    root = _repo_root(payload.repo_root)
    profiles = scan_agent_profiles(repo_root=root)

    entries = tuple(
        AgentListEntry(
            name=profile.name,
            description=profile.description,
            model=profile.model,
            skills=profile.skills,
            sandbox=profile.sandbox,
        )
        for profile in sorted(profiles, key=lambda p: p.name)
    )
    return AgentsListOutput(agents=entries)


agents_list = async_from_sync(agents_list_sync)
