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
_CACHE_TTL_SECONDS = 86400
_PROVIDER_TO_HARNESS: dict[str, HarnessId] = {
    "anthropic": HarnessId("claude"),
    "openai": HarnessId("codex"),
    "google": HarnessId("opencode"),
}
_EXCLUDED_TYPE_TOKENS = ("embedding", "tts", "speech", "audio", "transcription")

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DiscoveredModel:
    """Model entry normalized from the models.dev API."""

    id: str
    name: str
    family: str
    provider: str
    harness_id: HarnessId
    cost_input: float | None
    cost_output: float | None
    context_limit: int | None
    output_limit: int | None
    supports_tool_call: bool


def _cache_path() -> Path:
    return Path.home() / ".meridian" / "cache" / "models-dev.json"


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
    list_value = _coerce_list(value)
    if list_value is not None:
        values: set[str] = set()
        for item in list_value:
            if isinstance(item, str):
                normalized = item.strip().lower()
                if normalized:
                    values.add(normalized)
        return values
    return set()


def _infer_family(model_id: str) -> str:
    normalized = model_id.strip()
    if not normalized:
        return ""
    trimmed = normalized.rsplit("/", maxsplit=1)[-1]
    for separator in ("-", "."):
        if separator in trimmed:
            prefix = trimmed.split(separator, maxsplit=1)[0].strip()
            if prefix:
                return prefix
    return trimmed


def _supports_tool_call(row: JSONObject) -> bool:
    tool_call = row.get("tool_call")
    return tool_call is True


def _input_modalities(row: JSONObject) -> set[str]:
    modalities = _coerce_object(row.get("modalities"))
    if modalities is None:
        return set()
    return _coerce_string_set(modalities.get("input"))


def _output_modalities(row: JSONObject) -> set[str]:
    modalities = _coerce_object(row.get("modalities"))
    if modalities is None:
        return set()
    return _coerce_string_set(modalities.get("output"))


def _is_supported_coding_model(row: JSONObject) -> bool:
    if not _supports_tool_call(row):
        return False

    model_type = (_coerce_string(row.get("type")) or "").lower()
    if any(token in model_type for token in _EXCLUDED_TYPE_TOKENS):
        return False

    input_modalities = _input_modalities(row)
    output_modalities = _output_modalities(row)

    if input_modalities and "text" not in input_modalities:
        return False
    if output_modalities and "text" not in output_modalities:
        return False
    return True


def _parse_model_row(row: JSONObject) -> DiscoveredModel | None:
    provider = (_coerce_string(row.get("provider")) or "").lower()
    harness_id = _PROVIDER_TO_HARNESS.get(provider)
    if harness_id is None or not _is_supported_coding_model(row):
        return None

    model_id = _coerce_string(row.get("id")) or _coerce_string(row.get("provider_model_id"))
    if model_id is None:
        return None

    name = _coerce_string(row.get("name")) or model_id
    costs = _coerce_object(row.get("cost")) or {}
    limits = _coerce_object(row.get("limit")) or {}

    return DiscoveredModel(
        id=model_id,
        name=name,
        family=_infer_family(model_id),
        provider=provider,
        harness_id=harness_id,
        cost_input=_coerce_float(costs.get("input")),
        cost_output=_coerce_float(costs.get("output")),
        context_limit=_coerce_int(limits.get("context")),
        output_limit=_coerce_int(limits.get("output")),
        supports_tool_call=True,
    )


def _parse_models_payload_by_provider(payload_obj: object) -> list[DiscoveredModel]:
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
        for row in provider_models.values():
            parsed_row = _coerce_object(row)
            if parsed_row is None:
                continue
            parsed_row["provider"] = provider
            parsed_model = _parse_model_row(parsed_row)
            if parsed_model is not None:
                models.append(parsed_model)
    return models


def fetch_from_models_dev() -> list[DiscoveredModel]:
    """Fetch and normalize models from the public models.dev API."""

    req = request.Request(
        _MODELS_DEV_URL,
        headers={
            "Accept": "application/json",
            "User-Agent": "meridian-channel/0.0.1",
        },
    )
    with request.urlopen(req, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
        payload_obj = json.loads(response.read().decode("utf-8"))
    return _parse_models_payload_by_provider(payload_obj)


def _deserialize_cached_model(row: JSONObject) -> DiscoveredModel | None:
    model_id = _coerce_string(row.get("id"))
    name = _coerce_string(row.get("name"))
    family = _coerce_string(row.get("family"))
    provider = _coerce_string(row.get("provider"))
    harness_text = _coerce_string(row.get("harness_id"))
    supports_tool_call = row.get("supports_tool_call")

    if not isinstance(supports_tool_call, bool):
        return None
    if (
        model_id is None
        or name is None
        or family is None
        or provider is None
        or harness_text is None
    ):
        return None

    return DiscoveredModel(
        id=model_id,
        name=name,
        family=family,
        provider=provider,
        harness_id=HarnessId(harness_text),
        cost_input=_coerce_float(row.get("cost_input")),
        cost_output=_coerce_float(row.get("cost_output")),
        context_limit=_coerce_int(row.get("context_limit")),
        output_limit=_coerce_int(row.get("output_limit")),
        supports_tool_call=supports_tool_call,
    )


def _read_cache(path: Path | None = None) -> tuple[float, list[DiscoveredModel]] | None:
    target = path or _cache_path()
    if not target.is_file():
        return None

    try:
        payload_obj = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning(
            "Failed to read models.dev cache at %s",
            target,
            exc_info=True,
        )
        return None

    payload = _coerce_object(payload_obj)
    if payload is None:
        logger.warning("Ignoring invalid models.dev cache payload at %s", target)
        return None

    fetched_at = _coerce_float(payload.get("fetched_at"))
    rows = payload.get("models")
    if fetched_at is None or not isinstance(rows, list):
        logger.warning("Ignoring incomplete models.dev cache payload at %s", target)
        return None

    models: list[DiscoveredModel] = []
    for row in rows:
        parsed_row = _coerce_object(row)
        if parsed_row is None:
            continue
        cached_model = _deserialize_cached_model(parsed_row)
        if cached_model is not None:
            models.append(cached_model)

    return fetched_at, models


def _write_cache(models: list[DiscoveredModel], path: Path | None = None) -> None:
    target = path or _cache_path()
    payload = {
        "fetched_at": int(time.time()),
        "models": [asdict(model) for model in models],
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)


def _refresh_from_remote() -> list[DiscoveredModel]:
    models = fetch_from_models_dev()
    _write_cache(models)
    return models


def refresh_cache() -> list[DiscoveredModel]:
    """Force-refresh the user-level models.dev cache."""

    cached = _read_cache()
    try:
        return _refresh_from_remote()
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        if cached is not None:
            logger.warning(
                "Failed to refresh models.dev cache at %s; using cached models",
                _cache_path(),
                exc_info=True,
            )
            return cached[1]
        logger.warning(
            "Failed to refresh models.dev cache at %s; returning empty model list",
            _cache_path(),
            exc_info=True,
        )
        return []


def load_discovered_models(force_refresh: bool = False) -> list[DiscoveredModel]:
    """Load discovered models from the user cache, refreshing when stale."""

    if force_refresh:
        return refresh_cache()

    cached = _read_cache()
    if cached is not None:
        fetched_at, models = cached
        if time.time() - fetched_at < _CACHE_TTL_SECONDS:
            return models

    return refresh_cache()
