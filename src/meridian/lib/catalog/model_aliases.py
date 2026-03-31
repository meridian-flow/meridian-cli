"""Alias parsing and merge helpers for the model catalog."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, cast

from pydantic import BaseModel, ConfigDict, Field

from meridian.lib.catalog.model_policy import DEFAULT_HARNESS_PATTERNS, route_model_with_patterns
from meridian.lib.catalog.models_toml import catalog_path, load_models_file_payload
from meridian.lib.core.types import HarnessId, ModelId

if TYPE_CHECKING:
    from meridian.lib.catalog.models import DiscoveredModel


class _AliasSpec(NamedTuple):
    provider: str
    include: str
    exclude: tuple[str, ...]


_BUILTIN_ALIAS_SPECS: dict[str, _AliasSpec] = {
    "opus": _AliasSpec("anthropic", "opus", ()),
    "sonnet": _AliasSpec("anthropic", "sonnet", ()),
    "haiku": _AliasSpec("anthropic", "haiku", ()),
    "codex": _AliasSpec("openai", "codex", ("-mini", "-spark", "-max")),
    "gpt": _AliasSpec("openai", "gpt-", ("-codex", "-pro", "-mini", "-nano", "-chat", "-turbo")),
    "gpt52": _AliasSpec(
        "openai",
        "gpt-5.2",
        ("-codex", "-pro", "-mini", "-nano", "-chat", "-turbo"),
    ),
    "gemini": _AliasSpec("google", "pro", ("-customtools",)),
}

_FALLBACK_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
    "codex": "gpt-5.3-codex",
    "gpt": "gpt-5.4",
    "gpt52": "gpt-5.2",
    "gemini": "gemini-3.1-pro-preview",
}

_BUILTIN_DESCRIPTIONS: dict[str, str] = {
    "claude-opus-4-6": (
        "Strong long-term vision and best orchestrator. Creative but can hallucinate or over-engineer."
        " Best for orchestration, frontend implementation, architecture, and design exploration."
        " Not recommended for backend implementation or precise technical review."
    ),
    "gpt-5.3-codex": (
        "Default backend implementer. Fast, token-efficient, and faithful to instructions."
        " Best when given a clear task. Weak at frontend and UI work."
    ),
    "gpt-5.4": (
        "Strongest generalist with broad reasoning."
        " Best for review, verification, security, and architectural judgment."
    ),
    "gpt-5.2": "Extremely thorough reviewer, but slow.",
    "gemini-3.1-pro-preview": (
        "Large context window. Best for multimodal tasks."
        " Okay at frontend design mockups (but prefer opus for true implementation)."
    ),
}


class ModelEntriesResult(NamedTuple):
    aliases: dict[str, AliasEntry]
    descriptions: dict[str, str]  # model_id → description
    pinned: set[str]  # model_ids with pinned=true


class AliasEntry(BaseModel):
    """Alias entry for model lookup."""

    model_config = ConfigDict(frozen=True)

    alias: str
    model_id: ModelId
    resolved_harness: HarnessId | None = Field(default=None, exclude=True)

    @property
    def harness(self) -> HarnessId:
        if self.resolved_harness is not None:
            return self.resolved_harness
        return route_model_with_patterns(
            str(self.model_id),
            patterns_by_harness=DEFAULT_HARNESS_PATTERNS,
        ).harness_id

    def format_text(self, ctx: object | None = None) -> str:
        _ = ctx
        from meridian.cli.format_helpers import kv_block

        pairs: list[tuple[str, str | None]] = [
            ("Model", str(self.model_id)),
            ("Harness", str(self.harness)),
            ("Alias", self.alias or None),
        ]
        return kv_block(pairs)


def entry(*, alias: str, model_id: str) -> AliasEntry:
    return AliasEntry(
        alias=alias,
        model_id=ModelId(model_id),
    )


def _resolve_alias_from_models(
    spec: _AliasSpec,
    models: Sequence[DiscoveredModel],
) -> str | None:
    candidates: list[DiscoveredModel] = []
    for m in models:
        if m.provider != spec.provider:
            continue
        mid = m.id.lower()
        if spec.include not in mid:
            continue
        if mid.endswith("-latest"):
            continue
        if any(excl in mid for excl in spec.exclude):
            continue
        candidates.append(m)

    if not candidates:
        return None

    # Latest date first; for same date, prefer shorter (cleaner) ID
    candidates.sort(key=lambda m: (m.release_date or "", -len(m.id)), reverse=True)
    return candidates[0].id


def load_builtin_aliases(
    discovered_models: Sequence[DiscoveredModel] | None = None,
) -> list[AliasEntry]:
    resolved: dict[str, str] = {}
    if discovered_models:
        for alias, spec in _BUILTIN_ALIAS_SPECS.items():
            model_id = _resolve_alias_from_models(spec, discovered_models)
            if model_id is not None:
                resolved[alias] = model_id

    # Fill gaps from fallbacks
    for alias, model_id in _FALLBACK_ALIASES.items():
        if alias not in resolved:
            resolved[alias] = model_id

    return [
        entry(alias=a, model_id=mid)
        for a, mid in sorted(resolved.items())
    ]


def load_user_aliases(
    repo_root: Path,
    discovered_models: Sequence[DiscoveredModel] | None = None,
) -> list[AliasEntry]:
    path = catalog_path(repo_root)
    if not path.is_file():
        return []

    payload = load_models_file_payload(path)
    result = _load_aliases_from_payload(payload)
    pinned = result.aliases

    if discovered_models:
        specs = _coerce_user_alias_specs(payload.get("models"))
        for alias, spec in specs.items():
            if alias not in pinned:
                model_id = _resolve_alias_from_models(spec, discovered_models)
                if model_id is not None:
                    pinned[alias] = entry(
                        alias=alias, model_id=model_id
                    )

    return [pinned[key] for key in sorted(pinned)]


def merge_alias_entries(
    builtin_aliases: list[AliasEntry],
    user_aliases: list[AliasEntry],
) -> list[AliasEntry]:
    merged: dict[str, AliasEntry] = {item.alias: item for item in builtin_aliases}
    for item in user_aliases:
        merged[item.alias] = item
    return [merged[key] for key in sorted(merged)]


def load_alias_by_name(name: str, aliases: list[AliasEntry]) -> AliasEntry | None:
    normalized = name.strip()
    if not normalized:
        return None
    for entry in aliases:
        if entry.alias == normalized:
            return entry
    return None


def _load_aliases_from_payload(payload: dict[str, object]) -> ModelEntriesResult:
    return _coerce_model_entries(payload.get("models"))


def _coerce_model_entries(
    raw_models: object,
) -> ModelEntriesResult:
    if not isinstance(raw_models, dict):
        return ModelEntriesResult(aliases={}, descriptions={}, pinned=set())

    aliases: dict[str, AliasEntry] = {}
    descriptions: dict[str, str] = {}
    pinned: set[str] = set()

    for raw_key, raw_value in cast("dict[object, object]", raw_models).items():
        key = _coerce_string(raw_key)
        if key is None:
            continue

        # Case 1: String shorthand — pinned alias
        if isinstance(raw_value, str):
            model_id = _coerce_string(raw_value)
            if model_id is None:
                continue
            aliases[key] = entry(alias=key, model_id=model_id)
            continue

        if isinstance(raw_value, dict):
            table = cast("dict[object, object]", raw_value)

            # Case 2: Auto-resolve spec (provider + include)
            if _coerce_string(table.get("provider")) and _coerce_string(table.get("include")):
                desc = _coerce_string(table.get("description"))
                if desc:
                    # Can't resolve model_id yet for description — store by alias key
                    # Will be resolved later when auto-resolve runs
                    pass
                if isinstance(table.get("pinned"), bool) and table["pinned"]:
                    pass  # pinned for auto-resolve handled after resolution
                continue

            # Case 3: Dict with model_id — alias with metadata
            model_id = _coerce_string(table.get("model_id") or table.get("id"))
            if model_id is not None:
                aliases[key] = entry(alias=key, model_id=model_id)
                desc = _coerce_string(table.get("description"))
                if desc:
                    descriptions[model_id] = desc
                if isinstance(table.get("pinned"), bool) and table["pinned"]:
                    pinned.add(model_id)
                continue

            # Case 4: No model_id — key IS the model_id, metadata only
            desc = _coerce_string(table.get("description"))
            if desc:
                descriptions[key] = desc
            if isinstance(table.get("pinned"), bool) and table["pinned"]:
                pinned.add(key)

    return ModelEntriesResult(aliases=aliases, descriptions=descriptions, pinned=pinned)


def _coerce_user_alias_specs(raw_models: object) -> dict[str, _AliasSpec]:
    if not isinstance(raw_models, dict):
        return {}

    specs: dict[str, _AliasSpec] = {}
    for raw_alias, raw_value in cast("dict[object, object]", raw_models).items():
        alias = _coerce_string(raw_alias)
        if alias is None or not isinstance(raw_value, dict):
            continue
        table = cast("dict[object, object]", raw_value)
        provider = _coerce_string(table.get("provider"))
        include = _coerce_string(table.get("include"))
        if provider is None or include is None:
            continue
        raw_exclude = table.get("exclude")
        exclude: tuple[str, ...] = ()
        if isinstance(raw_exclude, list):
            exclude = tuple(
                s
                for item in cast("list[object]", raw_exclude)
                if isinstance(item, str)
                for s in [item.strip()]
                if s
            )
        specs[alias] = _AliasSpec(provider=provider, include=include, exclude=exclude)
    return specs


def load_builtin_descriptions() -> dict[str, str]:
    """Return builtin descriptions keyed by model_id."""
    return dict(_BUILTIN_DESCRIPTIONS)


def load_user_model_metadata(
    repo_root: Path,
    aliases: list[AliasEntry],
) -> tuple[dict[str, str], set[str]]:
    """Load descriptions and pinned flags from [models.*], keyed by model_id."""
    path = catalog_path(repo_root)
    if not path.is_file():
        return {}, set()

    payload = load_models_file_payload(path)
    result = _coerce_model_entries(payload.get("models"))

    # Also resolve descriptions for auto-resolve specs by checking resolved aliases
    raw_models = payload.get("models")
    if isinstance(raw_models, dict):
        for raw_key, raw_value in cast("dict[object, object]", raw_models).items():
            key = _coerce_string(raw_key)
            if key is None or not isinstance(raw_value, dict):
                continue
            table = cast("dict[object, object]", raw_value)
            if not (_coerce_string(table.get("provider")) and _coerce_string(table.get("include"))):
                continue
            # This is an auto-resolve spec — find its resolved alias
            for alias_entry in aliases:
                if alias_entry.alias == key:
                    desc = _coerce_string(table.get("description"))
                    if desc:
                        result.descriptions[str(alias_entry.model_id)] = desc
                    if isinstance(table.get("pinned"), bool) and table["pinned"]:
                        result.pinned.add(str(alias_entry.model_id))
                    break

    return result.descriptions, result.pinned


def _coerce_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
