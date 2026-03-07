"""Live model discovery backed by the public models.dev API."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast
from urllib import request
from urllib.error import HTTPError, URLError

from meridian.lib.types import HarnessId

type JSONScalar = str | int | float | bool | None
type JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
type JSONObject = dict[str, JSONValue]

_MODELS_DEV_URL = "https://models.dev/api.json"
_REQUEST_TIMEOUT_SECONDS = 10
_CACHE_TTL_SECONDS = 24 * 60 * 60
_CACHE_FILE_NAME = "models.json"
_PROVIDER_TO_HARNESS: dict[str, HarnessId] = {
    "anthropic": HarnessId("claude"),
    "openai": HarnessId("codex"),
    "google": HarnessId("opencode"),
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DiscoveredModel:
    """Normalized discovered model entry from models.dev."""

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

    @property
    def harness_id(self) -> HarnessId:
        """Backward-compatible alias for callers still using `harness_id`."""
        return self.harness

    @property
    def supports_tool_call(self) -> bool:
        """Backward-compatible alias for callers still using `supports_tool_call`."""
        return "tool_call" in self.capabilities


def _default_cache_dir() -> Path:
    return Path.home() / ".meridian" / "cache"


def _resolve_cache_dir(cache_dir: Path | str | bool | None) -> tuple[Path, bool]:
    if isinstance(cache_dir, bool):
        return _default_cache_dir(), cache_dir
    if cache_dir is None:
        return _default_cache_dir(), False
    return Path(cache_dir), False


def _cache_file(cache_dir: Path) -> Path:
    return cache_dir / _CACHE_FILE_NAME


def _coerce_object(value: JSONValue | object) -> JSONObject | None:
    if isinstance(value, dict):
        return cast("JSONObject", value)
    return None


def _coerce_list(value: JSONValue | object) -> list[object] | None:
    if isinstance(value, list):
        return cast("list[object]", value)
    return None


def _coerce_string(value: JSONValue | object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip()
        return normalized or None
    return None


def _coerce_float(value: JSONValue | object) -> float | None:
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


def _coerce_int(value: JSONValue | object) -> int | None:
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


def _coerce_string_set(value: JSONValue | object) -> set[str]:
    if isinstance(value, str):
        normalized = value.strip().lower()
        return {normalized} if normalized else set()

    as_list = _coerce_list(value)
    if as_list is None:
        return set()

    values: set[str] = set()
    for item in as_list:
        if not isinstance(item, str):
            continue
        normalized = item.strip().lower()
        if normalized:
            values.add(normalized)
    return values


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


def _capabilities(row: JSONObject) -> tuple[str, ...]:
    capabilities = _coerce_string_set(row.get("capabilities"))
    if row.get("tool_call") is True:
        capabilities.add("tool_call")

    normalized = sorted(capabilities)
    return tuple(normalized)


def _parse_model_row(row: JSONObject) -> DiscoveredModel | None:
    provider = (_coerce_string(row.get("provider")) or "").lower()
    harness = _PROVIDER_TO_HARNESS.get(provider)
    if harness is None:
        return None

    capabilities = _capabilities(row)
    if "tool_call" not in capabilities:
        return None

    model_id = _coerce_string(row.get("id")) or _coerce_string(row.get("provider_model_id"))
    if model_id is None:
        return None

    name = _coerce_string(row.get("name")) or model_id
    cost = _coerce_object(row.get("cost")) or {}
    limit = _coerce_object(row.get("limit")) or {}

    return DiscoveredModel(
        id=model_id,
        name=name,
        family=_infer_family(model_id),
        provider=provider,
        harness=harness,
        cost_input=_coerce_float(cost.get("input")),
        cost_output=_coerce_float(cost.get("output")),
        context_limit=_coerce_int(limit.get("context")),
        output_limit=_coerce_int(limit.get("output")),
        capabilities=capabilities,
    )


def _parse_models_payload(payload_obj: object) -> list[DiscoveredModel]:
    payload = _coerce_object(payload_obj)
    if payload is None:
        logger.warning("Unexpected models.dev payload shape; expected provider-keyed object")
        return []

    models: list[DiscoveredModel] = []
    for provider in _PROVIDER_TO_HARNESS:
        provider_payload = _coerce_object(payload.get(provider))
        if provider_payload is None:
            continue

        provider_models = _coerce_object(provider_payload.get("models"))
        if provider_models is None:
            continue

        for raw_row in provider_models.values():
            row = _coerce_object(raw_row)
            if row is None:
                continue
            row["provider"] = provider
            parsed = _parse_model_row(row)
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


def _deserialize_cached_model(row: JSONObject) -> DiscoveredModel | None:
    model_id = _coerce_string(row.get("id"))
    name = _coerce_string(row.get("name"))
    family = _coerce_string(row.get("family"))
    provider = _coerce_string(row.get("provider"))
    harness_value = _coerce_string(row.get("harness")) or _coerce_string(row.get("harness_id"))

    capabilities_raw = row.get("capabilities")
    capabilities = _coerce_string_set(capabilities_raw)
    if not capabilities and row.get("supports_tool_call") is True:
        capabilities.add("tool_call")

    if (
        model_id is None
        or name is None
        or family is None
        or provider is None
        or harness_value is None
    ):
        return None

    return DiscoveredModel(
        id=model_id,
        name=name,
        family=family,
        provider=provider,
        harness=HarnessId(harness_value),
        cost_input=_coerce_float(row.get("cost_input")),
        cost_output=_coerce_float(row.get("cost_output")),
        context_limit=_coerce_int(row.get("context_limit")),
        output_limit=_coerce_int(row.get("output_limit")),
        capabilities=tuple(sorted(capabilities)),
    )


def _read_cache(cache_file: Path) -> tuple[float, list[DiscoveredModel]] | None:
    if not cache_file.is_file():
        return None

    try:
        payload_obj = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read models.dev cache at %s", cache_file, exc_info=True)
        return None

    payload = _coerce_object(payload_obj)
    if payload is None:
        logger.warning("Ignoring invalid models.dev cache payload at %s", cache_file)
        return None

    fetched_at = _coerce_float(payload.get("fetched_at"))
    rows = payload.get("models")
    if fetched_at is None or not isinstance(rows, list):
        logger.warning("Ignoring incomplete models.dev cache payload at %s", cache_file)
        return None

    models: list[DiscoveredModel] = []
    for raw_row in rows:
        row = _coerce_object(raw_row)
        if row is None:
            continue
        parsed = _deserialize_cached_model(row)
        if parsed is not None:
            models.append(parsed)

    return fetched_at, models


def _write_cache(cache_file: Path, models: list[DiscoveredModel]) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, object] = {
        "fetched_at": int(time.time()),
        "models": [
            {
                **asdict(model),
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

    resolved_dir, _ = _resolve_cache_dir(cache_dir)
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
                exc_info=True,
            )
            return cached[1]

        logger.warning(
            "Failed to refresh models.dev cache at %s; returning empty model list",
            cache_file,
            exc_info=True,
        )
        return []


def load_discovered_models(
    cache_dir: Path | str | bool | None = None,
    *,
    force_refresh: bool = False,
) -> list[DiscoveredModel]:
    """Load discovered models from cache with 24-hour TTL."""

    resolved_dir, legacy_force_refresh = _resolve_cache_dir(cache_dir)
    use_force_refresh = force_refresh or legacy_force_refresh

    if use_force_refresh:
        return refresh_models_cache(resolved_dir)

    cache_file = _cache_file(resolved_dir)
    cached = _read_cache(cache_file)
    if cached is not None:
        fetched_at, models = cached
        if time.time() - fetched_at < _CACHE_TTL_SECONDS:
            return models

    return refresh_models_cache(resolved_dir)


# Compatibility wrappers for existing call sites.
def fetch_from_models_dev() -> list[DiscoveredModel]:
    return fetch_models_dev()


def refresh_cache() -> list[DiscoveredModel]:
    return refresh_models_cache(None)
