"""Model routing, discovery, alias resolution, and catalog."""


import importlib.resources
import json
import logging
import os
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Literal, cast
from urllib import request
from urllib.error import HTTPError, URLError

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from meridian.lib.config.settings import resolve_repo_root
from meridian.lib.core.util import FormatContext
from meridian.lib.state.paths import resolve_cache_dir, resolve_state_paths
from meridian.lib.core.types import HarnessId, ModelId

logger = logging.getLogger(__name__)


# ─── Routing ───────────────────────────────────────────────────────────

SpawnMode = Literal["harness", "direct"]


class RoutingDecision(BaseModel):
    """Routing result for a model selection request."""

    model_config = ConfigDict(frozen=True)

    harness_id: HarnessId
    warning: str | None = None


def route_model(model: str, mode: SpawnMode = "harness") -> RoutingDecision:
    """Route a model ID to the corresponding harness family.

    Unknown model families are rejected to avoid silently choosing the wrong harness.
    """

    normalized = model.strip()
    if mode == "direct":
        return RoutingDecision(harness_id=HarnessId("direct"))

    if normalized.startswith(("claude-", "opus", "sonnet", "haiku")):
        return RoutingDecision(harness_id=HarnessId("claude"))
    if normalized.startswith(("gpt-", "o1", "o3", "o4", "codex")):
        return RoutingDecision(harness_id=HarnessId("codex"))
    if normalized.startswith(("opencode-", "gemini-", "gemini")) or "/" in normalized:
        return RoutingDecision(harness_id=HarnessId("opencode"))

    raise ValueError(
        f"Unknown model family '{model}'. Configure an explicit harness in models.toml."
    )


# ─── Discovery ─────────────────────────────────────────────────────────

_MODELS_DEV_URL = "https://models.dev/api.json"
_REQUEST_TIMEOUT_SECONDS = 10
_CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_FILE_NAME = "models.json"
_PROVIDER_TO_HARNESS: dict[str, HarnessId] = {
    "anthropic": HarnessId("claude"),
    "openai": HarnessId("codex"),
    "google": HarnessId("opencode"),
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

    return DiscoveredModel(
        id=row.id,
        name=row.name,
        family=row.family,
        provider=row.provider,
        harness=HarnessId(row.harness),
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
    """Force fetch from models.dev and update local cache.

    If remote fetch fails and no cache exists, returns an empty list.
    """

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

# ─── Aliases ───────────────────────────────────────────────────────────

_DEFAULT_ALIASES_RESOURCE = "default-aliases.toml"


class AliasEntry(BaseModel):
    """Alias entry for model lookup + operator-facing guidance."""

    model_config = ConfigDict(frozen=True)

    alias: str
    model_id: ModelId
    role: str | None = None
    strengths: str | None = None

    @property
    def harness(self) -> HarnessId:
        """Harness inferred from the model identifier via prefix routing."""

        return route_model(str(self.model_id)).harness_id

    def format_text(self, ctx: FormatContext | None = None) -> str:
        """Key-value detail view for a single alias entry."""
        from meridian.cli.format_helpers import kv_block

        pairs: list[tuple[str, str | None]] = [
            ("Model", str(self.model_id)),
            ("Harness", str(self.harness)),
            ("Alias", self.alias or None),
            ("Role", self.role or None),
            ("Strengths", self.strengths or None),
        ]
        return kv_block(pairs)


# ─── Catalog ───────────────────────────────────────────────────────────


def _catalog_path(repo_root: Path) -> Path:
    return resolve_state_paths(repo_root).models_path


def _coerce_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_metadata_map(raw_metadata: object) -> dict[str, dict[str, str]]:
    if not isinstance(raw_metadata, dict):
        return {}

    metadata: dict[str, dict[str, str]] = {}
    for raw_alias, raw_row in cast("dict[object, object]", raw_metadata).items():
        alias = _coerce_string(raw_alias)
        if alias is None or not isinstance(raw_row, dict):
            continue
        row = cast("dict[object, object]", raw_row)
        metadata[alias] = {
            "role": _coerce_string(row.get("role")) or "",
            "strengths": _coerce_string(row.get("strengths")) or "",
        }
    return metadata


def _entry(*, alias: str, model_id: str, role: str | None, strengths: str | None) -> AliasEntry:
    return AliasEntry(
        alias=alias,
        model_id=ModelId(model_id),
        role=role,
        strengths=strengths,
    )


def _coerce_alias_entries(
    raw_aliases: object,
    *,
    metadata: dict[str, dict[str, str]],
) -> dict[str, AliasEntry]:
    if not isinstance(raw_aliases, dict):
        return {}

    aliases: dict[str, AliasEntry] = {}
    for raw_alias, raw_value in cast("dict[object, object]", raw_aliases).items():
        alias = _coerce_string(raw_alias)
        if alias is None:
            continue

        meta_row = metadata.get(alias, {})

        if isinstance(raw_value, str):
            model_id = _coerce_string(raw_value)
            if model_id is None:
                continue
            aliases[alias] = _entry(
                alias=alias,
                model_id=model_id,
                role=meta_row.get("role") or None,
                strengths=meta_row.get("strengths") or None,
            )
            continue

        if isinstance(raw_value, dict):
            table = cast("dict[object, object]", raw_value)
            model_id = _coerce_string(table.get("model_id") or table.get("id"))
            if model_id is None:
                logger.warning("Ignoring alias '%s' without model_id.", alias)
                continue
            aliases[alias] = _entry(
                alias=alias,
                model_id=model_id,
                role=_coerce_string(table.get("role")) or None,
                strengths=_coerce_string(table.get("strengths")) or None,
            )
            continue

        logger.warning("Ignoring invalid alias entry '%s'.", alias)

    return aliases


def _load_alias_file(path: Path) -> dict[str, AliasEntry]:
    payload_obj = tomllib.loads(path.read_text(encoding="utf-8"))
    payload = cast("dict[str, object]", payload_obj)

    metadata = _coerce_metadata_map(payload.get("metadata"))
    return _coerce_alias_entries(payload.get("aliases"), metadata=metadata)


def load_builtin_aliases() -> list[AliasEntry]:
    """Load built-in aliases bundled with meridian."""

    resource_path = Path(
        str(importlib.resources.files("meridian.resources") / _DEFAULT_ALIASES_RESOURCE)
    )
    entries = _load_alias_file(resource_path)
    return [entries[key] for key in sorted(entries)]


def load_user_aliases(repo_root: Path | None = None) -> list[AliasEntry]:
    """Load user-defined aliases from `.meridian/models.toml [aliases]`."""

    root = resolve_repo_root(repo_root)
    path = _catalog_path(root)
    if not path.is_file():
        return []

    entries = _load_alias_file(path)
    return [entries[key] for key in sorted(entries)]


def load_merged_aliases(repo_root: Path | None = None) -> list[AliasEntry]:
    """Load built-in aliases merged with user aliases (user wins by alias key)."""

    merged: dict[str, AliasEntry] = {entry.alias: entry for entry in load_builtin_aliases()}
    for entry in load_user_aliases(repo_root=repo_root):
        merged[entry.alias] = entry
    return [merged[key] for key in sorted(merged)]


def resolve_alias(name: str, repo_root: Path | None = None) -> ModelId | None:
    """Resolve one alias to a model identifier."""

    normalized = name.strip()
    if not normalized:
        return None

    for entry in load_merged_aliases(repo_root=repo_root):
        if entry.alias == normalized:
            return entry.model_id
    return None

def resolve_model(name_or_alias: str, repo_root: Path | None = None) -> AliasEntry:
    """Resolve alias to model id, or pass through a direct model identifier."""

    normalized = name_or_alias.strip()
    if not normalized:
        raise ValueError("Model identifier must not be empty.")

    aliases = load_merged_aliases(repo_root=repo_root)
    by_alias = {entry.alias: entry for entry in aliases}
    resolved = by_alias.get(normalized)
    if resolved is not None:
        # Validate alias targets through routing to preserve prior behavior.
        _ = route_model(str(resolved.model_id))
        return resolved

    _ = route_model(normalized)
    return AliasEntry(alias="", model_id=ModelId(normalized), role=None, strengths=None)
