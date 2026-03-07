"""Repository-level operational config loader."""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path
from typing import cast

from meridian.lib.state.paths import resolve_state_paths

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class OutputConfig:
    """Terminal output filtering configuration for run streaming."""

    show: tuple[str, ...] = ("lifecycle", "sub-run", "error", "system")
    verbosity: str | None = None


@dataclass(frozen=True, slots=True)
class SearchPathConfig:
    """Configurable discovery paths for agent profiles and skills."""

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
    global_agents: tuple[str, ...] = ("~/.claude/agents", "~/.opencode/agents")
    global_skills: tuple[str, ...] = ("~/.claude/skills", "~/.opencode/skills")


@dataclass(frozen=True, slots=True)
class PrimaryConfig:
    """Primary-specific harness settings."""

    autocompact_pct: int = 65
    permission_tier: str = "full-access"


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """Default model configuration for each harness adapter."""

    claude: str = "claude-opus-4-6"
    codex: str = "gpt-5.3-codex"
    opencode: str = "gemini-3.1-pro"


@dataclass(frozen=True, slots=True)
class MeridianConfig:
    """Resolved operational configuration for meridian."""

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
    harness: HarnessConfig = HarnessConfig()
    primary: PrimaryConfig = PrimaryConfig()
    output: OutputConfig = OutputConfig()
    search_paths: SearchPathConfig = SearchPathConfig()

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


_SECTION_KEY_MAP: dict[str, dict[str, str]] = {
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

_TOP_LEVEL_KEY_MAP: dict[str, str] = {
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

_ENV_OVERRIDE_MAP: dict[str, str] = {
    "MERIDIAN_MAX_DEPTH": "max_depth",
    "MERIDIAN_MAX_RETRIES": "max_retries",
    "MERIDIAN_RETRY_BACKOFF_SECONDS": "retry_backoff_seconds",
    "MERIDIAN_KILL_GRACE_MINUTES": "kill_grace_minutes",
    "MERIDIAN_GUARDRAIL_TIMEOUT_MINUTES": "guardrail_timeout_minutes",
    "MERIDIAN_WAIT_TIMEOUT_MINUTES": "wait_timeout_minutes",
    "MERIDIAN_DEFAULT_PERMISSION_TIER": "default_permission_tier",
    "MERIDIAN_PRIMARY_AGENT": "default_primary_agent",
    "MERIDIAN_DEFAULT_PRIMARY_AGENT": "default_primary_agent",
    "MERIDIAN_DEFAULT_AGENT": "default_agent",
    "MERIDIAN_DEFAULT_MODEL": "default_model",
    "MERIDIAN_HARNESS_MODEL_CLAUDE": "harness.claude",
    "MERIDIAN_HARNESS_MODEL_CODEX": "harness.codex",
    "MERIDIAN_HARNESS_MODEL_OPENCODE": "harness.opencode",
}

_OUTPUT_VERBOSITY_PRESETS = frozenset({"quiet", "normal", "verbose", "debug"})
_SEARCH_PATH_KEYS = frozenset({"agents", "skills", "global_agents", "global_skills"})
_PRIMARY_KEYS = frozenset({"autocompact_pct", "permission_tier"})
_HARNESS_KEYS = frozenset({"claude", "codex", "opencode"})
_PERMISSION_TIERS = ("read-only", "workspace-write", "full-access")
_PRIMARY_AUTOCOMPACT_PCT_MIN = 1
_PRIMARY_AUTOCOMPACT_PCT_MAX = 100
_USER_CONFIG_ENV_VAR = "MERIDIAN_CONFIG"


def _validate_permission_tier(raw: str) -> None:
    normalized = raw.strip().lower()
    if normalized in _PERMISSION_TIERS:
        return
    allowed = ", ".join(_PERMISSION_TIERS)
    raise ValueError(f"Unsupported permission tier '{raw}'. Expected: {allowed}.")


def _expected_type_name(field_name: str) -> str:
    if field_name in {"max_depth", "max_retries"}:
        return "int"
    if field_name in {
        "retry_backoff_seconds",
        "kill_grace_minutes",
        "guardrail_timeout_minutes",
        "wait_timeout_minutes",
    }:
        return "float"
    return "str"


def _coerce_file_value(*, field_name: str, raw_value: object, source: str) -> object:
    expected = _expected_type_name(field_name)
    if expected == "int":
        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            raise ValueError(
                f"Invalid value for '{source}': expected int, got "
                f"{type(raw_value).__name__} ({raw_value!r})."
            )
        return raw_value

    if expected == "float":
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
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"Invalid value for '{source}': expected non-empty string.")
    return normalized


def _coerce_output_config(
    *,
    raw_value: object,
    source: str,
    base: OutputConfig | None = None,
) -> OutputConfig:
    if not isinstance(raw_value, dict):
        raise ValueError(f"Invalid value for '{source}': expected table.")

    defaults = base if base is not None else OutputConfig()
    show = defaults.show
    verbosity = defaults.verbosity
    for key, value in cast("dict[str, object]", raw_value).items():
        if key == "show":
            if not isinstance(value, list):
                raise ValueError(
                    f"Invalid value for '{source}.show': expected array[str], "
                    f"got {type(value).__name__} ({value!r})."
                )
            parsed: list[str] = []
            for item in cast("list[object]", value):
                if not isinstance(item, str):
                    raise ValueError(
                        f"Invalid value for '{source}.show': expected array[str], got "
                        f"{type(item).__name__} ({item!r})."
                    )
                normalized = item.strip()
                if not normalized:
                    raise ValueError(
                        f"Invalid value for '{source}.show': expected non-empty category."
                    )
                parsed.append(normalized)
            show = tuple(parsed)
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
            verbosity = normalized
            continue

        logger.warning("Ignoring unknown Meridian config key '%s.%s'.", source, key)

    return OutputConfig(show=show, verbosity=verbosity)


def _coerce_search_path_list(*, raw_value: object, source: str) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        raise ValueError(
            f"Invalid value for '{source}': expected array[str], got "
            f"{type(raw_value).__name__} ({raw_value!r})."
        )

    parsed: list[str] = []
    for item in cast("list[object]", raw_value):
        if not isinstance(item, str):
            raise ValueError(
                f"Invalid value for '{source}': expected array[str], got "
                f"{type(item).__name__} ({item!r})."
            )
        normalized = item.strip()
        if not normalized:
            raise ValueError(
                f"Invalid value for '{source}': expected non-empty path entries."
            )
        parsed.append(normalized)
    return tuple(parsed)


def _coerce_search_path_config(
    *,
    raw_value: object,
    source: str,
    base: SearchPathConfig | None = None,
) -> SearchPathConfig:
    if not isinstance(raw_value, dict):
        raise ValueError(f"Invalid value for '{source}': expected table.")

    defaults = base if base is not None else SearchPathConfig()
    values: dict[str, tuple[str, ...]] = {
        "agents": defaults.agents,
        "skills": defaults.skills,
        "global_agents": defaults.global_agents,
        "global_skills": defaults.global_skills,
    }

    for key, value in cast("dict[str, object]", raw_value).items():
        if key not in _SEARCH_PATH_KEYS:
            logger.warning("Ignoring unknown Meridian config key '%s.%s'.", source, key)
            continue
        values[key] = _coerce_search_path_list(raw_value=value, source=f"{source}.{key}")

    return SearchPathConfig(
        agents=values["agents"],
        skills=values["skills"],
        global_agents=values["global_agents"],
        global_skills=values["global_skills"],
    )


def _coerce_primary_config(
    *,
    raw_value: object,
    source: str,
    base: PrimaryConfig | None = None,
) -> PrimaryConfig:
    if not isinstance(raw_value, dict):
        raise ValueError(f"Invalid value for '{source}': expected table.")

    defaults = base if base is not None else PrimaryConfig()
    autocompact_pct = defaults.autocompact_pct
    permission_tier = defaults.permission_tier
    for key, value in cast("dict[str, object]", raw_value).items():
        if key not in _PRIMARY_KEYS:
            logger.warning("Ignoring unknown Meridian config key '%s.%s'.", source, key)
            continue

        if key == "autocompact_pct":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(
                    f"Invalid value for '{source}.autocompact_pct': expected int, got "
                    f"{type(value).__name__} ({value!r})."
                )
            if not (
                _PRIMARY_AUTOCOMPACT_PCT_MIN
                <= value
                <= _PRIMARY_AUTOCOMPACT_PCT_MAX
            ):
                raise ValueError(
                    f"Invalid value for '{source}.autocompact_pct': expected int between "
                    f"{_PRIMARY_AUTOCOMPACT_PCT_MIN} and "
                    f"{_PRIMARY_AUTOCOMPACT_PCT_MAX}, got {value!r}."
                )
            autocompact_pct = value
            continue

        if not isinstance(value, str):
            raise ValueError(
                f"Invalid value for '{source}.permission_tier': expected str, got "
                f"{type(value).__name__} ({value!r})."
            )
        normalized = value.strip()
        if not normalized:
            raise ValueError(
                f"Invalid value for '{source}.permission_tier': expected non-empty string."
            )
        _validate_permission_tier(normalized)
        permission_tier = normalized

    return PrimaryConfig(
        autocompact_pct=autocompact_pct,
        permission_tier=permission_tier,
    )


def _normalize_model_identifier(model: str, *, repo_root: Path) -> str:
    normalized = model.strip()
    if not normalized:
        return normalized
    try:
        from meridian.lib.config.aliases import resolve_model

        return str(resolve_model(normalized, repo_root=repo_root).model_id)
    except ValueError:
        # Unknown model IDs are allowed here and validated during launch.
        return normalized


def _coerce_harness_config(
    *,
    raw_value: object,
    source: str,
    repo_root: Path,
    base: HarnessConfig | None = None,
) -> HarnessConfig:
    if not isinstance(raw_value, dict):
        raise ValueError(f"Invalid value for '{source}': expected table.")

    defaults = base if base is not None else HarnessConfig()
    values = {
        "claude": defaults.claude,
        "codex": defaults.codex,
        "opencode": defaults.opencode,
    }
    for key, value in cast("dict[str, object]", raw_value).items():
        if key not in _HARNESS_KEYS:
            logger.warning("Ignoring unknown Meridian config key '%s.%s'.", source, key)
            continue
        if not isinstance(value, str):
            raise ValueError(
                f"Invalid value for '{source}.{key}': expected str, got "
                f"{type(value).__name__} ({value!r})."
            )
        normalized = value.strip()
        if not normalized:
            raise ValueError(
                f"Invalid value for '{source}.{key}': expected non-empty string."
            )
        normalized = _normalize_model_identifier(normalized, repo_root=repo_root)
        values[key] = normalized

    return HarnessConfig(
        claude=values["claude"],
        codex=values["codex"],
        opencode=values["opencode"],
    )


def _coerce_env_value(*, field_name: str, raw_value: str, env_name: str) -> object:
    expected = _expected_type_name(field_name)
    if expected == "int":
        try:
            return int(raw_value.strip())
        except ValueError as error:
            raise ValueError(
                f"Invalid environment override '{env_name}': expected int, got {raw_value!r}."
            ) from error

    if expected == "float":
        try:
            return float(raw_value.strip())
        except ValueError as error:
            raise ValueError(
                f"Invalid environment override '{env_name}': expected float, got {raw_value!r}."
            ) from error

    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(
            f"Invalid environment override '{env_name}': expected non-empty string."
        )
    return normalized


def _default_values() -> dict[str, object]:
    defaults = MeridianConfig()
    return {field.name: getattr(defaults, field.name) for field in fields(MeridianConfig)}


def _apply_toml_payload(
    *,
    values: dict[str, object],
    payload: dict[str, object],
    path: Path,
    repo_root: Path,
) -> None:
    for key, raw_value in payload.items():
        if key == "output":
            values["output"] = _coerce_output_config(
                raw_value=raw_value,
                source="output",
                base=cast("OutputConfig", values["output"]),
            )
            continue
        if key == "search_paths":
            values["search_paths"] = _coerce_search_path_config(
                raw_value=raw_value,
                source="search_paths",
                base=cast("SearchPathConfig", values["search_paths"]),
            )
            continue
        if key == "primary":
            values["primary"] = _coerce_primary_config(
                raw_value=raw_value,
                source="primary",
                base=cast("PrimaryConfig", values["primary"]),
            )
            continue
        if key == "harness":
            values["harness"] = _coerce_harness_config(
                raw_value=raw_value,
                source="harness",
                repo_root=repo_root,
                base=cast("HarnessConfig", values["harness"]),
            )
            continue

        section_map = _SECTION_KEY_MAP.get(key)
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
                values[field_name] = _coerce_file_value(
                    field_name=field_name,
                    raw_value=section_value,
                    source=f"{key}.{section_key}",
                )
                if field_name == "default_model":
                    values[field_name] = _normalize_model_identifier(
                        cast("str", values[field_name]),
                        repo_root=repo_root,
                    )
            continue

        field_name = _TOP_LEVEL_KEY_MAP.get(key)
        if field_name is None:
            logger.warning("Ignoring unknown Meridian config key '%s'.", key)
            continue
        values[field_name] = _coerce_file_value(
            field_name=field_name,
            raw_value=raw_value,
            source=key,
        )
        if field_name == "default_model":
            values[field_name] = _normalize_model_identifier(
                cast("str", values[field_name]),
                repo_root=repo_root,
            )


def _apply_env_overrides(values: dict[str, object], *, repo_root: Path) -> None:
    for env_name, field_name in _ENV_OVERRIDE_MAP.items():
        raw_value = os.getenv(env_name)
        if raw_value is None:
            continue
        if field_name.startswith("harness."):
            harness_key = field_name.split(".", 1)[1]
            current_harness = cast("HarnessConfig", values["harness"])
            raw_harness = {
                "claude": current_harness.claude,
                "codex": current_harness.codex,
                "opencode": current_harness.opencode,
                harness_key: raw_value,
            }
            values["harness"] = _coerce_harness_config(
                raw_value=raw_harness,
                source="harness",
                repo_root=repo_root,
                base=current_harness,
            )
            continue
        values[field_name] = _coerce_env_value(
            field_name=field_name,
            raw_value=raw_value,
            env_name=env_name,
        )
        if field_name == "default_model":
            values[field_name] = _normalize_model_identifier(
                cast("str", values[field_name]),
                repo_root=repo_root,
            )


def _build_config(values: dict[str, object]) -> MeridianConfig:
    config = MeridianConfig(
        max_depth=cast("int", values["max_depth"]),
        max_retries=cast("int", values["max_retries"]),
        retry_backoff_seconds=cast("float", values["retry_backoff_seconds"]),
        kill_grace_minutes=cast("float", values["kill_grace_minutes"]),
        guardrail_timeout_minutes=cast("float", values["guardrail_timeout_minutes"]),
        wait_timeout_minutes=cast("float", values["wait_timeout_minutes"]),
        default_permission_tier=cast("str", values["default_permission_tier"]),
        default_primary_agent=cast("str", values["default_primary_agent"]),
        default_agent=cast("str", values["default_agent"]),
        default_model=cast("str", values["default_model"]),
        harness=cast("HarnessConfig", values["harness"]),
        primary=cast("PrimaryConfig", values["primary"]),
        output=cast("OutputConfig", values["output"]),
        search_paths=cast("SearchPathConfig", values["search_paths"]),
    )
    _validate_permission_tier(config.default_permission_tier)
    _validate_permission_tier(config.primary.permission_tier)
    return config


def _resolve_user_config_path(user_config: Path | None) -> Path | None:
    resolved = user_config.expanduser() if user_config is not None else None
    if resolved is None:
        raw_env = os.getenv(_USER_CONFIG_ENV_VAR, "").strip()
        if raw_env:
            resolved = Path(raw_env).expanduser()

    if resolved is None:
        return None
    if not resolved.is_file():
        raise FileNotFoundError(
            f"User Meridian config file not found: '{resolved.as_posix()}'."
        )
    return resolved


def load_config(repo_root: Path, *, user_config: Path | None = None) -> MeridianConfig:
    """Load config with precedence: defaults < project < user < environment."""

    values = _default_values()
    project_path = resolve_state_paths(repo_root).config_path
    if project_path.is_file():
        payload_obj = tomllib.loads(project_path.read_text(encoding="utf-8"))
        payload = cast("dict[str, object]", payload_obj)
        _apply_toml_payload(
            values=values,
            payload=payload,
            path=project_path,
            repo_root=repo_root,
        )

    resolved_user_config = _resolve_user_config_path(user_config)
    if resolved_user_config is not None:
        payload_obj = tomllib.loads(resolved_user_config.read_text(encoding="utf-8"))
        payload = cast("dict[str, object]", payload_obj)
        _apply_toml_payload(
            values=values,
            payload=payload,
            path=resolved_user_config,
            repo_root=repo_root,
        )

    _apply_env_overrides(values, repo_root=repo_root)
    return _build_config(values)
