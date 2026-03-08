"""Repository-level operational config loader."""

from __future__ import annotations

import logging
import os
import tomllib
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

from meridian.lib.state.paths import resolve_state_paths

logger = logging.getLogger(__name__)

_OUTPUT_VERBOSITY_PRESETS = frozenset({"quiet", "normal", "verbose", "debug"})
_PERMISSION_TIERS = ("read-only", "workspace-write", "full-access")
_PRIMARY_AUTOCOMPACT_PCT_MIN = 1
_PRIMARY_AUTOCOMPACT_PCT_MAX = 100
USER_CONFIG_ENV_VAR = "MERIDIAN_CONFIG"
_DEFAULT_USER_CONFIG = Path("~/.config/meridian/config.toml").expanduser()


@dataclass(frozen=True, slots=True)
class _SettingsLoadContext:
    repo_root: Path
    user_config: Path | None


_SETTINGS_CONTEXT: ContextVar[_SettingsLoadContext | None] = ContextVar(
    "_SETTINGS_CONTEXT",
    default=None,
)


def _current_repo_root() -> Path | None:
    context = _SETTINGS_CONTEXT.get()
    if context is None:
        return None
    return context.repo_root


def _validate_permission_tier(raw: str) -> str:
    normalized = raw.strip().lower()
    if normalized in _PERMISSION_TIERS:
        return normalized
    allowed = ", ".join(_PERMISSION_TIERS)
    raise ValueError(f"Unsupported permission tier '{raw}'. Expected: {allowed}.")


def _normalize_required_string(raw: str, *, source: str) -> str:
    normalized = raw.strip()
    if not normalized:
        raise ValueError(f"Invalid value for '{source}': expected non-empty string.")
    return normalized


def _normalize_optional_string(raw: str | None, *, source: str) -> str | None:
    if raw is None:
        return None
    normalized = raw.strip()
    if not normalized:
        raise ValueError(f"Invalid value for '{source}': expected non-empty string.")
    return normalized


def _normalize_model_identifier(model: str, *, repo_root: Path | None) -> str:
    normalized = model.strip()
    if not normalized:
        return normalized
    if repo_root is None:
        return normalized
    try:
        from meridian.lib.config.aliases import resolve_model

        return str(resolve_model(normalized, repo_root=repo_root).model_id)
    except ValueError:
        # Unknown model IDs are allowed here and validated during launch.
        return normalized


def _normalize_string_tuple(
    values: tuple[str, ...],
    *,
    source: str,
) -> tuple[str, ...]:
    normalized: list[str] = []
    for item in values:
        compact = item.strip()
        if not compact:
            raise ValueError(f"Invalid value for '{source}': expected non-empty entries.")
        normalized.append(compact)
    return tuple(normalized)


def _parse_env_int(raw_value: str, *, env_name: str) -> int:
    try:
        return int(raw_value.strip())
    except ValueError as error:
        raise ValueError(
            f"Invalid environment override '{env_name}': expected int, got {raw_value!r}."
        ) from error


def _parse_env_float(raw_value: str, *, env_name: str) -> float:
    try:
        return float(raw_value.strip())
    except ValueError as error:
        raise ValueError(
            f"Invalid environment override '{env_name}': expected float, got {raw_value!r}."
        ) from error


def _parse_env_string(raw_value: str, *, env_name: str) -> str:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(
            f"Invalid environment override '{env_name}': expected non-empty string."
        )
    return normalized


def _parse_env_path_list(raw_value: str, *, env_name: str) -> tuple[str, ...]:
    parsed = [entry.strip() for entry in raw_value.split(":")]
    normalized = [entry for entry in parsed if entry]
    if not normalized:
        raise ValueError(
            f"Invalid environment override '{env_name}': expected colon-separated paths."
        )
    return tuple(normalized)


def _parse_file_scalar(*, field_name: str, raw_value: object, source: str) -> object:
    int_fields = {"max_depth", "max_retries"}
    float_fields = {
        "retry_backoff_seconds",
        "kill_grace_minutes",
        "guardrail_timeout_minutes",
        "wait_timeout_minutes",
    }

    if field_name in int_fields:
        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            raise ValueError(
                f"Invalid value for '{source}': expected int, got "
                f"{type(raw_value).__name__} ({raw_value!r})."
            )
        return raw_value

    if field_name in float_fields:
        if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
            raise ValueError(
                f"Invalid value for '{source}': expected float, got "
                f"{type(raw_value).__name__} ({raw_value!r})."
            )
        return float(raw_value)

    if not isinstance(raw_value, str):
        raise ValueError(
            f"Invalid value for '{source}': expected str, got "
            f"{type(raw_value).__name__} ({raw_value!r})."
        )
    return _normalize_required_string(raw_value, source=source)


def _parse_toml_list(*, raw_value: object, source: str) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        raise ValueError(
            f"Invalid value for '{source}': expected array[str], "
            f"got {type(raw_value).__name__} ({raw_value!r})."
        )

    parsed: list[str] = []
    for item in cast("list[object]", raw_value):
        if not isinstance(item, str):
            raise ValueError(
                f"Invalid value for '{source}': expected array[str], "
                f"got {type(item).__name__} ({item!r})."
            )
        normalized = item.strip()
        if not normalized:
            raise ValueError(
                f"Invalid value for '{source}': expected non-empty path entries."
            )
        parsed.append(normalized)
    return tuple(parsed)


def _merge_nested_dicts(base: dict[str, object], overrides: dict[str, object]) -> dict[str, object]:
    merged = dict(base)
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_nested_dicts(
                cast("dict[str, object]", current),
                cast("dict[str, object]", value),
            )
            continue
        merged[key] = value
    return merged


def _assign_nested_value(target: dict[str, object], path: tuple[str, ...], value: object) -> None:
    current = target
    for part in path[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            replacement: dict[str, object] = {}
            current[part] = replacement
            current = replacement
            continue
        current = cast("dict[str, object]", nested)
    current[path[-1]] = value


def _read_toml(path: Path) -> dict[str, object]:
    payload_obj = tomllib.loads(path.read_text(encoding="utf-8"))
    return cast("dict[str, object]", payload_obj)


def _resolve_project_toml(repo_root: Path) -> Path | None:
    current = repo_root
    for candidate_root in (current, *current.parents):
        candidate = candidate_root / "meridian.toml"
        if candidate.is_file():
            return candidate

    legacy = resolve_state_paths(repo_root).config_path
    if legacy.is_file():
        return legacy
    return None


def _resolve_user_config_path(user_config: Path | None) -> Path | None:
    resolved = user_config.expanduser() if user_config is not None else None
    if resolved is None:
        raw_env = os.getenv(USER_CONFIG_ENV_VAR, "").strip()
        if raw_env:
            resolved = Path(raw_env).expanduser()

    if resolved is None:
        if _DEFAULT_USER_CONFIG.is_file():
            return _DEFAULT_USER_CONFIG
        return None

    if not resolved.is_file():
        raise FileNotFoundError(
            f"User Meridian config file not found: '{resolved.as_posix()}'."
        )
    return resolved


def _normalize_output_table(raw_value: object, *, source: str) -> dict[str, object]:
    if not isinstance(raw_value, dict):
        raise ValueError(f"Invalid value for '{source}': expected table.")

    values: dict[str, object] = {}
    for key, value in cast("dict[str, object]", raw_value).items():
        if key == "show":
            values[key] = _parse_toml_list(raw_value=value, source=f"{source}.show")
            continue
        if key == "verbosity":
            if not isinstance(value, str):
                raise ValueError(
                    f"Invalid value for '{source}.verbosity': expected str, got "
                    f"{type(value).__name__} ({value!r})."
                )
            normalized = value.strip().lower()
            if not normalized:
                raise ValueError(
                    f"Invalid value for '{source}.verbosity': expected non-empty string."
                )
            if normalized not in _OUTPUT_VERBOSITY_PRESETS:
                raise ValueError(
                    f"Invalid value for '{source}.verbosity': expected one of "
                    f"{sorted(_OUTPUT_VERBOSITY_PRESETS)}, got {value!r}."
                )
            values[key] = normalized
            continue
        if key == "format":
            if not isinstance(value, str):
                raise ValueError(
                    f"Invalid value for '{source}.format': expected str, got "
                    f"{type(value).__name__} ({value!r})."
                )
            values[key] = _normalize_required_string(value, source=f"{source}.format")
            continue

        logger.warning("Ignoring unknown Meridian config key '%s.%s'.", source, key)

    return values


def _normalize_search_paths_table(raw_value: object, *, source: str) -> dict[str, object]:
    if not isinstance(raw_value, dict):
        raise ValueError(f"Invalid value for '{source}': expected table.")

    allowed = frozenset({"agents", "skills", "global_agents", "global_skills"})
    values: dict[str, object] = {}
    for key, value in cast("dict[str, object]", raw_value).items():
        if key not in allowed:
            logger.warning("Ignoring unknown Meridian config key '%s.%s'.", source, key)
            continue
        values[key] = _parse_toml_list(raw_value=value, source=f"{source}.{key}")
    return values


def _normalize_primary_table(raw_value: object, *, source: str) -> dict[str, object]:
    if not isinstance(raw_value, dict):
        raise ValueError(f"Invalid value for '{source}': expected table.")

    values: dict[str, object] = {}
    for key, value in cast("dict[str, object]", raw_value).items():
        if key == "autocompact_pct":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"Invalid value for '{source}.autocompact_pct': expected int, got "
                    f"{type(value).__name__} ({value!r})."
                )
            if not (_PRIMARY_AUTOCOMPACT_PCT_MIN <= value <= _PRIMARY_AUTOCOMPACT_PCT_MAX):
                raise ValueError(
                    f"Invalid value for '{source}.autocompact_pct': expected int between "
                    f"{_PRIMARY_AUTOCOMPACT_PCT_MIN} and "
                    f"{_PRIMARY_AUTOCOMPACT_PCT_MAX}, got {value!r}."
                )
            values[key] = value
            continue

        if key == "permission_tier":
            if not isinstance(value, str):
                raise ValueError(
                    f"Invalid value for '{source}.permission_tier': expected str, got "
                    f"{type(value).__name__} ({value!r})."
                )
            values[key] = _validate_permission_tier(value)
            continue

        if key in {"model", "harness", "agent"}:
            if not isinstance(value, str):
                raise ValueError(
                    f"Invalid value for '{source}.{key}': expected str, got "
                    f"{type(value).__name__} ({value!r})."
                )
            values[key] = _normalize_required_string(value, source=f"{source}.{key}")
            continue

        if key in {"max_turns", "max_input_tokens", "max_output_tokens"}:
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"Invalid value for '{source}.{key}': expected int, got "
                    f"{type(value).__name__} ({value!r})."
                )
            values[key] = value
            continue

        if key == "budget":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ValueError(
                    f"Invalid value for '{source}.budget': expected float, got "
                    f"{type(value).__name__} ({value!r})."
                )
            values[key] = float(value)
            continue

        logger.warning("Ignoring unknown Meridian config key '%s.%s'.", source, key)

    return values


def _normalize_harness_table(
    raw_value: object,
    *,
    source: str,
    repo_root: Path,
) -> dict[str, object]:
    if not isinstance(raw_value, dict):
        raise ValueError(f"Invalid value for '{source}': expected table.")

    allowed = frozenset({"claude", "codex", "opencode"})
    values: dict[str, object] = {}
    for key, value in cast("dict[str, object]", raw_value).items():
        if key not in allowed:
            logger.warning("Ignoring unknown Meridian config key '%s.%s'.", source, key)
            continue
        if not isinstance(value, str):
            raise ValueError(
                f"Invalid value for '{source}.{key}': expected str, got "
                f"{type(value).__name__} ({value!r})."
            )
        normalized = _normalize_required_string(value, source=f"{source}.{key}")
        values[key] = _normalize_model_identifier(normalized, repo_root=repo_root)

    return values


def _normalize_toml_payload(
    *,
    payload: dict[str, object],
    path: Path,
    repo_root: Path,
) -> dict[str, object]:
    section_aliases: dict[str, dict[str, str]] = {
        "defaults": {
            "max_depth": "max_depth",
            "max_retries": "max_retries",
            "retry_backoff_seconds": "retry_backoff_seconds",
            "default_primary_agent": "default_primary_agent",
            "primary_agent": "default_primary_agent",
            "agent": "default_agent",
            "default_agent": "default_agent",
            "model": "default_model",
            "default_model": "default_model",
        },
        "timeouts": {
            "kill_grace_minutes": "kill_grace_minutes",
            "guardrail_minutes": "guardrail_timeout_minutes",
            "guardrail_timeout_minutes": "guardrail_timeout_minutes",
            "wait_minutes": "wait_timeout_minutes",
            "wait_timeout_minutes": "wait_timeout_minutes",
        },
        "permissions": {
            "default_tier": "default_permission_tier",
            "default_permission_tier": "default_permission_tier",
        },
    }
    top_level_aliases: dict[str, str] = {
        "max_depth": "max_depth",
        "max_retries": "max_retries",
        "retry_backoff_seconds": "retry_backoff_seconds",
        "kill_grace_minutes": "kill_grace_minutes",
        "guardrail_timeout_minutes": "guardrail_timeout_minutes",
        "wait_timeout_minutes": "wait_timeout_minutes",
        "default_permission_tier": "default_permission_tier",
        "default_primary_agent": "default_primary_agent",
        "primary_agent": "default_primary_agent",
        "default_agent": "default_agent",
        "default_model": "default_model",
    }

    normalized: dict[str, object] = {}
    for key, raw_value in payload.items():
        if key == "output":
            normalized["output"] = _merge_nested_dicts(
                cast("dict[str, object]", normalized.get("output", {})),
                _normalize_output_table(raw_value, source="output"),
            )
            continue
        if key == "search_paths":
            normalized["search_paths"] = _merge_nested_dicts(
                cast("dict[str, object]", normalized.get("search_paths", {})),
                _normalize_search_paths_table(raw_value, source="search_paths"),
            )
            continue
        if key == "primary":
            normalized["primary"] = _merge_nested_dicts(
                cast("dict[str, object]", normalized.get("primary", {})),
                _normalize_primary_table(raw_value, source="primary"),
            )
            continue
        if key == "harness":
            normalized["harness"] = _merge_nested_dicts(
                cast("dict[str, object]", normalized.get("harness", {})),
                _normalize_harness_table(raw_value, source="harness", repo_root=repo_root),
            )
            continue

        section_map = section_aliases.get(key)
        if section_map is not None:
            if not isinstance(raw_value, dict):
                raise ValueError(f"Invalid value for '{key}' in '{path}': expected table.")
            for section_key, section_value in cast("dict[str, object]", raw_value).items():
                field_name = section_map.get(section_key)
                if field_name is None:
                    logger.warning(
                        "Ignoring unknown Meridian config key '%s.%s'.",
                        key,
                        section_key,
                    )
                    continue
                coerced = _parse_file_scalar(
                    field_name=field_name,
                    raw_value=section_value,
                    source=f"{key}.{section_key}",
                )
                if field_name == "default_model":
                    coerced = _normalize_model_identifier(
                        cast("str", coerced),
                        repo_root=repo_root,
                    )
                normalized[field_name] = coerced
            continue

        field_name = top_level_aliases.get(key)
        if field_name is None:
            logger.warning("Ignoring unknown Meridian config key '%s'.", key)
            continue

        coerced = _parse_file_scalar(
            field_name=field_name,
            raw_value=raw_value,
            source=key,
        )
        if field_name == "default_model":
            coerced = _normalize_model_identifier(cast("str", coerced), repo_root=repo_root)
        normalized[field_name] = coerced

    return normalized


def _env_alias_overrides(repo_root: Path) -> dict[str, object]:
    values: dict[str, object] = {}
    env_specs: tuple[tuple[str, tuple[str, ...], Literal["int", "float", "str", "paths"]], ...] = (
        ("MERIDIAN_MAX_DEPTH", ("max_depth",), "int"),
        ("MERIDIAN_MAX_RETRIES", ("max_retries",), "int"),
        ("MERIDIAN_RETRY_BACKOFF_SECONDS", ("retry_backoff_seconds",), "float"),
        ("MERIDIAN_KILL_GRACE_MINUTES", ("kill_grace_minutes",), "float"),
        (
            "MERIDIAN_GUARDRAIL_TIMEOUT_MINUTES",
            ("guardrail_timeout_minutes",),
            "float",
        ),
        ("MERIDIAN_WAIT_TIMEOUT_MINUTES", ("wait_timeout_minutes",), "float"),
        (
            "MERIDIAN_DEFAULT_PERMISSION_TIER",
            ("default_permission_tier",),
            "str",
        ),
        ("MERIDIAN_PRIMARY_AGENT", ("default_primary_agent",), "str"),
        ("MERIDIAN_DEFAULT_PRIMARY_AGENT", ("default_primary_agent",), "str"),
        ("MERIDIAN_DEFAULT_AGENT", ("default_agent",), "str"),
        ("MERIDIAN_DEFAULT_MODEL", ("default_model",), "str"),
        ("MERIDIAN_HARNESS_MODEL_CLAUDE", ("harness", "claude"), "str"),
        ("MERIDIAN_HARNESS_MODEL_CODEX", ("harness", "codex"), "str"),
        ("MERIDIAN_HARNESS_MODEL_OPENCODE", ("harness", "opencode"), "str"),
        ("MERIDIAN_MODEL", ("primary", "model"), "str"),
        ("MERIDIAN_HARNESS", ("primary", "harness"), "str"),
        ("MERIDIAN_MAX_TURNS", ("primary", "max_turns"), "int"),
        (
            "MERIDIAN_MAX_INPUT_TOKENS",
            ("primary", "max_input_tokens"),
            "int",
        ),
        (
            "MERIDIAN_MAX_OUTPUT_TOKENS",
            ("primary", "max_output_tokens"),
            "int",
        ),
        ("MERIDIAN_BUDGET", ("primary", "budget"), "float"),
        ("MERIDIAN_AGENT", ("primary", "agent"), "str"),
        ("MERIDIAN_FORMAT", ("output", "format"), "str"),
        ("MERIDIAN_AGENT_SEARCH_PATHS", ("search_paths", "agents"), "paths"),
        ("MERIDIAN_SKILL_SEARCH_PATHS", ("search_paths", "skills"), "paths"),
    )

    for env_name, field_path, value_kind in env_specs:
        raw_value = os.getenv(env_name)
        if raw_value is None:
            continue

        parsed: object
        if value_kind == "int":
            parsed = _parse_env_int(raw_value, env_name=env_name)
        elif value_kind == "float":
            parsed = _parse_env_float(raw_value, env_name=env_name)
        elif value_kind == "paths":
            parsed = _parse_env_path_list(raw_value, env_name=env_name)
        else:
            parsed = _parse_env_string(raw_value, env_name=env_name)

        if field_path in {
            ("default_model",),
            ("harness", "claude"),
            ("harness", "codex"),
            ("harness", "opencode"),
            ("primary", "model"),
        }:
            parsed = _normalize_model_identifier(cast("str", parsed), repo_root=repo_root)

        _assign_nested_value(values, field_path, parsed)

    return values


class OutputConfig(BaseModel):
    """Terminal output filtering configuration for run streaming."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    show: tuple[str, ...] = ("lifecycle", "sub-run", "error", "system")
    verbosity: str | None = None
    format: str = "text"

    @field_validator("show")
    @classmethod
    def _validate_show(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_string_tuple(value, source="output.show")

    @field_validator("verbosity")
    @classmethod
    def _validate_verbosity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _normalize_required_string(value, source="output.verbosity").lower()
        if normalized not in _OUTPUT_VERBOSITY_PRESETS:
            raise ValueError(
                "Invalid value for 'output.verbosity': expected one of "
                f"{sorted(_OUTPUT_VERBOSITY_PRESETS)}, got {value!r}."
            )
        return normalized

    @field_validator("format")
    @classmethod
    def _validate_format(cls, value: str) -> str:
        return _normalize_required_string(value, source="output.format")


class SearchPathConfig(BaseModel):
    """Configurable discovery paths for agent profiles and skills."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    agents: tuple[str, ...] = (
        ".agents/agents",
        ".claude/agents",
        ".codex/agents",
        ".opencode/agents",
        ".cursor/agents",
    )
    skills: tuple[str, ...] = (
        ".agents/skills",
        ".claude/skills",
        ".codex/skills",
        ".opencode/skills",
        ".cursor/skills",
    )
    global_agents: tuple[str, ...] = (
        "~/.claude/agents",
        "~/.codex/agents",
        "~/.opencode/agents",
    )
    global_skills: tuple[str, ...] = (
        "~/.claude/skills",
        "~/.codex/skills",
        "~/.opencode/skills",
    )

    @field_validator("agents", "skills", "global_agents", "global_skills")
    @classmethod
    def _validate_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _normalize_string_tuple(value, source="search_paths")


class PrimaryConfig(BaseModel):
    """Primary-specific harness settings."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    autocompact_pct: int = 65
    permission_tier: str = "full-access"
    model: str | None = None
    harness: str | None = None
    max_turns: int | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    budget: float | None = None
    agent: str | None = None

    @field_validator("autocompact_pct")
    @classmethod
    def _validate_autocompact_pct(cls, value: int) -> int:
        if not (_PRIMARY_AUTOCOMPACT_PCT_MIN <= value <= _PRIMARY_AUTOCOMPACT_PCT_MAX):
            raise ValueError(
                "Invalid value for 'primary.autocompact_pct': expected int between "
                f"{_PRIMARY_AUTOCOMPACT_PCT_MIN} and "
                f"{_PRIMARY_AUTOCOMPACT_PCT_MAX}, got {value!r}."
            )
        return value

    @field_validator("permission_tier")
    @classmethod
    def _validate_permission(cls, value: str) -> str:
        return _validate_permission_tier(value)

    @field_validator("model")
    @classmethod
    def _validate_model(cls, value: str | None) -> str | None:
        normalized = _normalize_optional_string(value, source="primary.model")
        if normalized is None:
            return None
        return _normalize_model_identifier(normalized, repo_root=_current_repo_root())

    @field_validator("harness", "agent")
    @classmethod
    def _validate_optional_string_fields(cls, value: str | None) -> str | None:
        return _normalize_optional_string(value, source="primary")


class HarnessConfig(BaseModel):
    """Default model configuration for each harness adapter."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    claude: str = "claude-opus-4-6"
    codex: str = "gpt-5.3-codex"
    opencode: str = "gemini-3.1-pro"

    @field_validator("claude", "codex", "opencode")
    @classmethod
    def _normalize_models(cls, value: str) -> str:
        normalized = _normalize_required_string(value, source="harness")
        return _normalize_model_identifier(normalized, repo_root=_current_repo_root())


class MeridianConfig(BaseSettings):
    """Resolved operational configuration for meridian."""

    model_config = SettingsConfigDict(
        frozen=True,
        extra="ignore",
        env_prefix="MERIDIAN_",
        env_nested_delimiter="__",
    )

    max_depth: int = 3
    max_retries: int = 3
    retry_backoff_seconds: float = 0.25
    kill_grace_minutes: float = 2.0 / 60.0
    guardrail_timeout_minutes: float = 0.5
    wait_timeout_minutes: float = 30.0
    default_permission_tier: str = "read-only"
    default_primary_agent: str = "primary"
    default_agent: str = "agent"
    default_model: str = "gpt-5.3-codex"

    harness: HarnessConfig = Field(default_factory=HarnessConfig)
    primary: PrimaryConfig = Field(default_factory=PrimaryConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    search_paths: SearchPathConfig = Field(default_factory=SearchPathConfig)

    @field_validator("default_permission_tier")
    @classmethod
    def _validate_default_permission_tier(cls, value: str) -> str:
        return _validate_permission_tier(value)

    @field_validator("default_primary_agent", "default_agent")
    @classmethod
    def _validate_default_agents(cls, value: str) -> str:
        return _normalize_required_string(value, source="defaults")

    @field_validator("default_model")
    @classmethod
    def _validate_default_model(cls, value: str) -> str:
        normalized = _normalize_required_string(value, source="default_model")
        return _normalize_model_identifier(normalized, repo_root=_current_repo_root())

    @property
    def primary_agent(self) -> str:
        """Backward-compatible alias for legacy config field name."""
        return self.default_primary_agent

    def default_model_for_harness(self, harness_id: str) -> str | None:
        """Return configured default model for one harness ID."""

        normalized = harness_id.strip().lower()
        if normalized == "claude":
            return self.harness.claude
        if normalized == "codex":
            return self.harness.codex
        if normalized == "opencode":
            return self.harness.opencode
        return None

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        _ = settings_cls
        _ = dotenv_settings
        _ = file_secret_settings

        def project_toml_source() -> dict[str, object]:
            context = _SETTINGS_CONTEXT.get()
            if context is None:
                return {}
            project_config = _resolve_project_toml(context.repo_root)
            if project_config is None:
                return {}
            payload = _read_toml(project_config)
            return _normalize_toml_payload(
                payload=payload,
                path=project_config,
                repo_root=context.repo_root,
            )

        def user_toml_source() -> dict[str, object]:
            context = _SETTINGS_CONTEXT.get()
            if context is None or context.user_config is None:
                return {}
            payload = _read_toml(context.user_config)
            return _normalize_toml_payload(
                payload=payload,
                path=context.user_config,
                repo_root=context.repo_root,
            )

        def layered_env_source() -> dict[str, object]:
            context = _SETTINGS_CONTEXT.get()
            if context is None:
                return {}
            _ = env_settings
            return _env_alias_overrides(context.repo_root)

        return (
            init_settings,
            cast("PydanticBaseSettingsSource", layered_env_source),
            cast("PydanticBaseSettingsSource", user_toml_source),
            cast("PydanticBaseSettingsSource", project_toml_source),
        )


def load_config(repo_root: Path, *, user_config: Path | None = None) -> MeridianConfig:
    """Load config with precedence: defaults < project < user < environment."""

    resolved_repo_root = repo_root.expanduser().resolve()
    resolved_user_config = _resolve_user_config_path(user_config)

    token = _SETTINGS_CONTEXT.set(
        _SettingsLoadContext(
            repo_root=resolved_repo_root,
            user_config=resolved_user_config,
        )
    )
    try:
        return MeridianConfig()
    finally:
        _SETTINGS_CONTEXT.reset(token)
