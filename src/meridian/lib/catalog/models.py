"""Model discovery plus compatibility exports for catalog helpers."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import cast
from urllib import request
from urllib.error import HTTPError, URLError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from meridian.lib.catalog.model_aliases import (
    AliasEntry,
    load_alias_by_name,
    load_builtin_aliases,
    load_builtin_descriptions,
    load_user_model_metadata,
    merge_alias_entries,
)
from meridian.lib.catalog.model_aliases import (
    load_user_aliases as _load_user_aliases,
)
from meridian.lib.catalog.model_policy import (
    DEFAULT_HARNESS_PATTERNS,
    DEFAULT_MODEL_VISIBILITY,
    ModelVisibilityConfig,
    RoutingDecision,
    SpawnMode,
    coerce_harness_patterns,
    coerce_model_visibility,
    compute_superseded_ids,
    is_default_visible_model,
    merge_harness_patterns,
    merge_model_visibility,
    route_model_with_patterns,
)
from meridian.lib.catalog.models_toml import (
    catalog_path as _catalog_path,
)
from meridian.lib.catalog.models_toml import (
    ensure_models_config,
    load_models_file_payload,
    render_models_toml,
    scaffold_models_toml,
)
from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.core.types import HarnessId, ModelId
from meridian.lib.state.paths import resolve_cache_dir

logger = logging.getLogger(__name__)


def load_harness_patterns(repo_root: Path | None = None) -> dict[HarnessId, tuple[str, ...]]:
    if repo_root is None:
        return merge_harness_patterns()

    path = _catalog_path(resolve_repo_root(repo_root))
    if not path.is_file():
        return merge_harness_patterns()

    payload = load_models_file_payload(path)
    return merge_harness_patterns(coerce_harness_patterns(payload.get("harness_patterns")))


def route_model(
    model: str,
    mode: SpawnMode = "harness",
    *,
    repo_root: Path | None = None,
) -> RoutingDecision:
    """Route a model ID to the corresponding harness family."""

    return route_model_with_patterns(
        model,
        patterns_by_harness=load_harness_patterns(repo_root=repo_root),
        mode=mode,
    )


def load_model_visibility(repo_root: Path | None = None) -> ModelVisibilityConfig:
    if repo_root is None:
        return DEFAULT_MODEL_VISIBILITY

    path = _catalog_path(resolve_repo_root(repo_root))
    if not path.is_file():
        return DEFAULT_MODEL_VISIBILITY

    payload = load_models_file_payload(path)
    return merge_model_visibility(coerce_model_visibility(payload.get("model_visibility")))


def load_user_aliases(
    repo_root: Path | None = None,
    discovered_models: list[DiscoveredModel] | None = None,
) -> list[AliasEntry]:
    root = resolve_repo_root(repo_root)
    return _load_user_aliases(root, discovered_models=discovered_models)


def _resolve_alias_harness(entry: AliasEntry, repo_root: Path | None) -> AliasEntry:
    resolved_harness = route_model(str(entry.model_id), repo_root=repo_root).harness_id
    return entry.model_copy(update={"resolved_harness": resolved_harness})


def load_merged_aliases(repo_root: Path | None = None) -> list[AliasEntry]:
    """Load built-in aliases merged with user aliases (user wins by alias key)."""

    discovered = load_discovered_models()

    merged = merge_alias_entries(
        load_builtin_aliases(discovered_models=discovered),
        load_user_aliases(repo_root=repo_root, discovered_models=discovered),
    )
    resolved_root = resolve_repo_root(repo_root) if repo_root is not None else None
    return [_resolve_alias_harness(entry, resolved_root) for entry in merged]


def resolve_alias(name: str, repo_root: Path | None = None) -> ModelId | None:
    """Resolve one alias to a model identifier."""

    resolved = load_alias_by_name(name, load_merged_aliases(repo_root=repo_root))
    if resolved is None:
        return None
    return resolved.model_id


def resolve_model(name_or_alias: str, repo_root: Path | None = None) -> AliasEntry:
    """Resolve alias to model id, or pass through a direct model identifier."""

    normalized = name_or_alias.strip()
    if not normalized:
        raise ValueError("Model identifier must not be empty.")

    resolved = load_alias_by_name(normalized, load_merged_aliases(repo_root=repo_root))
    if resolved is not None:
        _ = route_model(str(resolved.model_id), repo_root=repo_root)
        return resolved

    resolved_harness = route_model(normalized, repo_root=repo_root).harness_id
    return AliasEntry(
        alias="",
        model_id=ModelId(normalized),
        resolved_harness=resolved_harness,
    )


_MODELS_DEV_URL = "https://models.dev/api.json"
_REQUEST_TIMEOUT_SECONDS = 10
_CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_FILE_NAME = "models.json"
_PROVIDER_TO_HARNESS: dict[str, HarnessId] = {
    "anthropic": HarnessId.CLAUDE,
    "openai": HarnessId.CODEX,
    "google": HarnessId.OPENCODE,
}


class DiscoveredModel(BaseModel):
    """Normalized discovered model entry from models.dev."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    family: str
    provider: str
    harness: HarnessId
    cost_input: float | None
    cost_output: float | None
    context_limit: int | None
    output_limit: int | None
    capabilities: tuple[str, ...]
    release_date: str | None


def _parse_string(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _parse_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def _parse_capabilities(value: object) -> tuple[str, ...]:
    raw_values: list[object]
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, list):
        raw_values = cast("list[object]", value)
    elif isinstance(value, tuple):
        raw_values = list(cast("tuple[object, ...]", value))
    elif isinstance(value, set):
        raw_values = list(cast("set[object]", value))
    else:
        return ()

    capabilities: set[str] = set()
    for raw in raw_values:
        if not isinstance(raw, str):
            continue
        normalized = raw.strip().lower()
        if normalized:
            capabilities.add(normalized)
    return tuple(sorted(capabilities))


class _ModelsDevCost(BaseModel):
    model_config = ConfigDict(extra="ignore")

    input: float | None = None
    output: float | None = None

    @field_validator("input", "output", mode="before")
    @classmethod
    def _parse_cost_value(cls, value: object) -> float | None:
        return _parse_float(value)


class _ModelsDevLimit(BaseModel):
    model_config = ConfigDict(extra="ignore")

    context: int | None = None
    output: int | None = None

    @field_validator("context", "output", mode="before")
    @classmethod
    def _parse_limit_value(cls, value: object) -> int | None:
        return _parse_int(value)


class _ModelsDevModelRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    provider_model_id: str | None = None
    name: str | None = None
    tool_call: bool = False
    capabilities: tuple[str, ...] = ()
    cost: _ModelsDevCost = Field(default_factory=_ModelsDevCost)
    limit: _ModelsDevLimit = Field(default_factory=_ModelsDevLimit)
    release_date: str | None = None

    @field_validator("id", "provider_model_id", "name", "release_date", mode="before")
    @classmethod
    def _parse_optional_string(cls, value: object) -> str | None:
        return _parse_string(value)

    @field_validator("capabilities", mode="before")
    @classmethod
    def _parse_capability_values(cls, value: object) -> tuple[str, ...]:
        return _parse_capabilities(value)


class _ModelsDevProviderPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    models: dict[str, object] = Field(default_factory=dict)


class _ModelsDevPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    anthropic: _ModelsDevProviderPayload | None = None
    openai: _ModelsDevProviderPayload | None = None
    google: _ModelsDevProviderPayload | None = None


class _CachedModelRow(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str | None = None
    family: str | None = None
    provider: str | None = None
    harness: str | None = None
    cost_input: float | None = None
    cost_output: float | None = None
    context_limit: int | None = None
    output_limit: int | None = None
    capabilities: tuple[str, ...] = ()
    release_date: str | None = None

    @field_validator(
        "id",
        "name",
        "family",
        "provider",
        "harness",
        "release_date",
        mode="before",
    )
    @classmethod
    def _parse_optional_string(cls, value: object) -> str | None:
        return _parse_string(value)

    @field_validator("cost_input", "cost_output", mode="before")
    @classmethod
    def _parse_cost_value(cls, value: object) -> float | None:
        return _parse_float(value)

    @field_validator("context_limit", "output_limit", mode="before")
    @classmethod
    def _parse_limit_value(cls, value: object) -> int | None:
        return _parse_int(value)

    @field_validator("capabilities", mode="before")
    @classmethod
    def _parse_capability_values(cls, value: object) -> tuple[str, ...]:
        return _parse_capabilities(value)


class _CachedModelsPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fetched_at: float | None = None
    models: tuple[object, ...] = ()

    @field_validator("fetched_at", mode="before")
    @classmethod
    def _parse_fetched_at(cls, value: object) -> float | None:
        return _parse_float(value)


def _default_cache_dir() -> Path:
    return resolve_cache_dir(resolve_repo_root())


def _resolve_cache_dir(cache_dir: Path | str | None) -> Path:
    if cache_dir is None:
        return _default_cache_dir()
    return Path(cache_dir)


def _cache_file(cache_dir: Path) -> Path:
    return cache_dir / _CACHE_FILE_NAME


def _infer_family(model_id: str) -> str:
    normalized = model_id.strip()
    if not normalized:
        return ""

    tail = normalized.rsplit("/", maxsplit=1)[-1]
    for separator in ("-", "."):
        if separator in tail:
            prefix = tail.split(separator, maxsplit=1)[0].strip()
            if prefix:
                return prefix
    return tail


def _capabilities(row: _ModelsDevModelRow) -> tuple[str, ...]:
    capabilities = set(row.capabilities)
    if row.tool_call:
        capabilities.add("tool_call")
    return tuple(sorted(capabilities))


def _parse_model_row(row: _ModelsDevModelRow, provider: str) -> DiscoveredModel | None:
    harness = _PROVIDER_TO_HARNESS.get(provider)
    if harness is None:
        return None

    capabilities = _capabilities(row)
    if "tool_call" not in capabilities:
        return None

    model_id = row.id or row.provider_model_id
    if model_id is None:
        return None

    name = row.name or model_id
    return DiscoveredModel(
        id=model_id,
        name=name,
        family=_infer_family(model_id),
        provider=provider,
        harness=harness,
        cost_input=row.cost.input,
        cost_output=row.cost.output,
        context_limit=row.limit.context,
        output_limit=row.limit.output,
        capabilities=capabilities,
        release_date=row.release_date,
    )


def _parse_models_payload(payload_obj: object) -> list[DiscoveredModel]:
    try:
        payload = _ModelsDevPayload.model_validate(payload_obj)
    except ValidationError:
        logger.warning("Unexpected models.dev payload shape; expected provider-keyed object")
        return []

    models: list[DiscoveredModel] = []
    for provider in _PROVIDER_TO_HARNESS:
        provider_payload = getattr(payload, provider)
        if provider_payload is None:
            continue

        for raw_row in provider_payload.models.values():
            try:
                row = _ModelsDevModelRow.model_validate(raw_row)
            except ValidationError:
                continue
            parsed = _parse_model_row(row, provider)
            if parsed is not None:
                models.append(parsed)

    return models


def fetch_models_dev() -> list[DiscoveredModel]:
    """Fetch and normalize coding-capable models from models.dev."""

    req = request.Request(
        _MODELS_DEV_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "meridian-channel/0.0.1",
        },
    )
    with request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
        payload_obj = json.loads(response.read().decode("utf-8"))

    return _parse_models_payload(payload_obj)


def _deserialize_cached_model(row: _CachedModelRow) -> DiscoveredModel | None:
    if (
        row.id is None
        or row.name is None
        or row.family is None
        or row.provider is None
        or row.harness is None
    ):
        return None

    try:
        harness = HarnessId(row.harness)
    except ValueError:
        return None

    return DiscoveredModel(
        id=row.id,
        name=row.name,
        family=row.family,
        provider=row.provider,
        harness=harness,
        cost_input=row.cost_input,
        cost_output=row.cost_output,
        context_limit=row.context_limit,
        output_limit=row.output_limit,
        capabilities=tuple(sorted(row.capabilities)),
        release_date=row.release_date,
    )


def _read_cache(cache_file: Path) -> tuple[float, list[DiscoveredModel]] | None:
    if not cache_file.is_file():
        return None

    try:
        payload_obj = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read models.dev cache at %s", cache_file, exc_info=False)
        logger.debug("Failed to read models.dev cache at %s", cache_file, exc_info=True)
        return None

    try:
        payload = _CachedModelsPayload.model_validate(payload_obj)
    except ValidationError:
        logger.warning("Ignoring invalid models.dev cache payload at %s", cache_file)
        return None

    if payload.fetched_at is None:
        logger.warning("Ignoring incomplete models.dev cache payload at %s", cache_file)
        return None

    models: list[DiscoveredModel] = []
    for raw_row in payload.models:
        try:
            row = _CachedModelRow.model_validate(raw_row)
        except ValidationError:
            continue
        parsed = _deserialize_cached_model(row)
        if parsed is not None:
            models.append(parsed)

    return payload.fetched_at, models


def _write_cache(cache_file: Path, models: list[DiscoveredModel]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, object] = {
        "fetched_at": int(time.time()),
        "models": [
            {
                **model.model_dump(),
                "harness": str(model.harness),
                "capabilities": list(model.capabilities),
            }
            for model in models
        ],
    }

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{cache_file.name}.",
        suffix=".tmp",
        dir=cache_file.parent,
    )
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2, sort_keys=True))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, cache_file)
    finally:
        tmp_path.unlink(missing_ok=True)


def refresh_models_cache(cache_dir: Path | str | None = None) -> list[DiscoveredModel]:
    """Force fetch from models.dev and update local cache."""

    resolved_dir = _resolve_cache_dir(cache_dir)
    cache_file = _cache_file(resolved_dir)
    cached = _read_cache(cache_file)

    try:
        models = fetch_models_dev()
        _write_cache(cache_file, models)
        return models
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        if cached is not None:
            logger.warning(
                "Failed to refresh models.dev cache at %s; using cached models",
                cache_file,
                exc_info=False,
            )
            logger.debug(
                "Failed to refresh models.dev cache at %s; using cached models",
                cache_file,
                exc_info=True,
            )
            return cached[1]

        logger.warning(
            "Failed to refresh models.dev catalog; no cached data available",
            exc_info=False,
        )
        logger.debug(
            "Failed to refresh models.dev cache at %s; no cached data available",
            cache_file,
            exc_info=True,
        )
        return []


def load_discovered_models(
    cache_dir: Path | str | None = None,
    *,
    force_refresh: bool = False,
) -> list[DiscoveredModel]:
    """Load discovered models from cache with 24-hour TTL."""

    resolved_dir = _resolve_cache_dir(cache_dir)
    if force_refresh:
        return refresh_models_cache(resolved_dir)

    cache_file = _cache_file(resolved_dir)
    cached = _read_cache(cache_file)
    if cached is not None:
        fetched_at, models = cached
        if time.time() - fetched_at < _CACHE_TTL_SECONDS:
            return models

    return refresh_models_cache(resolved_dir)


__all__ = [
    "DEFAULT_HARNESS_PATTERNS",
    "DEFAULT_MODEL_VISIBILITY",
    "AliasEntry",
    "DiscoveredModel",
    "ModelVisibilityConfig",
    "RoutingDecision",
    "SpawnMode",
    "coerce_harness_patterns",
    "coerce_model_visibility",
    "compute_superseded_ids",
    "ensure_models_config",
    "fetch_models_dev",
    "is_default_visible_model",
    "load_builtin_aliases",
    "load_builtin_descriptions",
    "load_discovered_models",
    "load_harness_patterns",
    "load_merged_aliases",
    "load_model_visibility",
    "load_user_aliases",
    "load_user_model_metadata",
    "merge_harness_patterns",
    "merge_model_visibility",
    "refresh_models_cache",
    "render_models_toml",
    "resolve_alias",
    "resolve_model",
    "route_model",
    "route_model_with_patterns",
    "scaffold_models_toml",
]
