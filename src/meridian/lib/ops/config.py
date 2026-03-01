"""Config file management operations."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from meridian.lib.config._paths import resolve_repo_root
from meridian.lib.config.settings import (
    MeridianConfig,
    PrimaryConfig,
    SearchPathConfig,
    _USER_CONFIG_ENV_VAR,
    load_config,
)
from meridian.lib.ops.registry import OperationSpec, operation
from meridian.lib.serialization import to_jsonable
from meridian.lib.state.paths import resolve_state_paths

if TYPE_CHECKING:
    from meridian.lib.formatting import FormatContext


_SECTION_ORDER: tuple[str, ...] = ("defaults", "timeouts", "permissions", "output")
_OUTPUT_VERBOSITY_PRESETS = frozenset({"quiet", "normal", "verbose", "debug"})


@dataclass(frozen=True, slots=True)
class _ConfigKeySpec:
    canonical_key: str
    section: str
    file_key: str
    field_path: tuple[str, ...]
    value_kind: Literal["int", "float", "str", "str_list", "verbosity"]
    env_var: str | None = None
    aliases: tuple[str, ...] = ()


_CONFIG_KEY_SPECS: tuple[_ConfigKeySpec, ...] = (
    _ConfigKeySpec(
        canonical_key="defaults.max_depth",
        section="defaults",
        file_key="max_depth",
        field_path=("max_depth",),
        value_kind="int",
        env_var="MERIDIAN_MAX_DEPTH",
        aliases=("max_depth",),
    ),
    _ConfigKeySpec(
        canonical_key="defaults.max_retries",
        section="defaults",
        file_key="max_retries",
        field_path=("max_retries",),
        value_kind="int",
        env_var="MERIDIAN_MAX_RETRIES",
        aliases=("max_retries",),
    ),
    _ConfigKeySpec(
        canonical_key="defaults.retry_backoff_seconds",
        section="defaults",
        file_key="retry_backoff_seconds",
        field_path=("retry_backoff_seconds",),
        value_kind="float",
        env_var="MERIDIAN_RETRY_BACKOFF_SECONDS",
        aliases=("retry_backoff_seconds",),
    ),
    _ConfigKeySpec(
        canonical_key="defaults.default_primary_agent",
        section="defaults",
        file_key="default_primary_agent",
        field_path=("default_primary_agent",),
        value_kind="str",
        env_var="MERIDIAN_DEFAULT_PRIMARY_AGENT",
        aliases=("defaults.primary_agent", "default_primary_agent", "primary_agent"),
    ),
    _ConfigKeySpec(
        canonical_key="defaults.agent",
        section="defaults",
        file_key="agent",
        field_path=("default_agent",),
        value_kind="str",
        env_var="MERIDIAN_DEFAULT_AGENT",
        aliases=("defaults.default_agent", "default_agent", "agent"),
    ),
    _ConfigKeySpec(
        canonical_key="timeouts.kill_grace_seconds",
        section="timeouts",
        file_key="kill_grace_seconds",
        field_path=("kill_grace_seconds",),
        value_kind="float",
        env_var="MERIDIAN_KILL_GRACE_SECONDS",
        aliases=("kill_grace_seconds",),
    ),
    _ConfigKeySpec(
        canonical_key="timeouts.guardrail_seconds",
        section="timeouts",
        file_key="guardrail_seconds",
        field_path=("guardrail_timeout_seconds",),
        value_kind="float",
        env_var="MERIDIAN_GUARDRAIL_TIMEOUT_SECONDS",
        aliases=("timeouts.guardrail_timeout_seconds", "guardrail_timeout_seconds"),
    ),
    _ConfigKeySpec(
        canonical_key="timeouts.wait_seconds",
        section="timeouts",
        file_key="wait_seconds",
        field_path=("wait_timeout_seconds",),
        value_kind="float",
        env_var="MERIDIAN_WAIT_TIMEOUT_SECONDS",
        aliases=("timeouts.wait_timeout_seconds", "wait_timeout_seconds"),
    ),
    _ConfigKeySpec(
        canonical_key="permissions.default_tier",
        section="permissions",
        file_key="default_tier",
        field_path=("default_permission_tier",),
        value_kind="str",
        env_var="MERIDIAN_DEFAULT_PERMISSION_TIER",
        aliases=(
            "permissions.default_permission_tier",
            "default_tier",
            "default_permission_tier",
        ),
    ),
    _ConfigKeySpec(
        canonical_key="output.show",
        section="output",
        file_key="show",
        field_path=("output", "show"),
        value_kind="str_list",
        aliases=(),
    ),
    _ConfigKeySpec(
        canonical_key="output.verbosity",
        section="output",
        file_key="verbosity",
        field_path=("output", "verbosity"),
        value_kind="verbosity",
        aliases=(),
    ),
)


_CONFIG_KEY_ALIAS_MAP: dict[str, _ConfigKeySpec] = {}
for spec in _CONFIG_KEY_SPECS:
    for alias in (spec.canonical_key, *spec.aliases):
        existing = _CONFIG_KEY_ALIAS_MAP.get(alias)
        if existing is not None and existing is not spec:
            raise ValueError(f"Conflicting config key alias '{alias}'.")
        _CONFIG_KEY_ALIAS_MAP[alias] = spec


@dataclass(frozen=True, slots=True)
class ConfigInitInput:
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigInitOutput:
    path: str
    created: bool

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        status = "created" if self.created else "exists"
        return f"{status}: {self.path}"


@dataclass(frozen=True, slots=True)
class ConfigShowInput:
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigResolvedValue:
    key: str
    value: object
    source: Literal["builtin", "file", "user-config", "env var"]
    env_var: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigShowOutput:
    path: str
    values: tuple[ConfigResolvedValue, ...]
    warning: str | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines = [f"path: {self.path}"]
        if self.warning is not None:
            lines.append(f"warning: {self.warning}")
        for item in self.values:
            source_note = item.source
            if item.env_var is not None:
                source_note = f"{source_note} ({item.env_var})"
            lines.append(
                f"{item.key}: {_format_value_for_text(item.value)} [source: {source_note}]"
            )
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class ConfigSetInput:
    key: str
    value: str
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigSetOutput:
    path: str
    key: str
    value: object

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return f"set {self.key} = {_format_value_for_text(self.value)} in {self.path}"


@dataclass(frozen=True, slots=True)
class ConfigGetInput:
    key: str
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigGetOutput:
    key: str
    value: object
    source: Literal["builtin", "file", "user-config", "env var"]
    env_var: str | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        source_note = self.source if self.env_var is None else f"{self.source} ({self.env_var})"
        return f"{self.key}: {_format_value_for_text(self.value)} [source: {source_note}]"


@dataclass(frozen=True, slots=True)
class ConfigResetInput:
    key: str
    repo_root: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigResetOutput:
    path: str
    key: str
    removed: bool

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        status = "removed" if self.removed else "already-default"
        return f"reset {self.key} ({status}) in {self.path}"


def _config_path(repo_root: Path) -> Path:
    return resolve_state_paths(repo_root).config_path


def _resolve_repo_root(repo_root: str | None) -> Path:
    explicit = Path(repo_root).expanduser().resolve() if repo_root else None
    return resolve_repo_root(explicit)


def _resolve_key_spec(key: str) -> _ConfigKeySpec:
    normalized = key.strip()
    if not normalized:
        raise ValueError("Config key must not be empty.")

    resolved = _CONFIG_KEY_ALIAS_MAP.get(normalized)
    if resolved is not None:
        return resolved

    valid = ", ".join(spec.canonical_key for spec in _CONFIG_KEY_SPECS)
    raise ValueError(f"Unknown config key '{key}'. Supported keys: {valid}")


def _get_field_value(config: MeridianConfig, field_path: tuple[str, ...]) -> object:
    current: object = config
    for part in field_path:
        current = getattr(current, part)
    return current


def _default_values() -> dict[str, object]:
    defaults = MeridianConfig()
    return {
        spec.canonical_key: _normalize_runtime_value(_get_field_value(defaults, spec.field_path))
        for spec in _CONFIG_KEY_SPECS
    }


def _resolved_values(config: MeridianConfig) -> dict[str, object]:
    return {
        spec.canonical_key: _normalize_runtime_value(_get_field_value(config, spec.field_path))
        for spec in _CONFIG_KEY_SPECS
    }


def _normalize_runtime_value(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(str(item) for item in cast("tuple[object, ...]", value))
    return value


def _read_file_payload(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    payload_obj = tomllib.loads(path.read_text(encoding="utf-8"))
    return cast("dict[str, object]", payload_obj)


def _parse_toml_value(spec: _ConfigKeySpec, raw_value: object, source: str) -> object:
    if spec.value_kind == "int":
        if isinstance(raw_value, bool) or not isinstance(raw_value, int):
            raise ValueError(
                f"Invalid value for '{source}': expected int, got "
                f"{type(raw_value).__name__} ({raw_value!r})."
            )
        return raw_value

    if spec.value_kind == "float":
        if isinstance(raw_value, bool) or not isinstance(raw_value, int | float):
            raise ValueError(
                f"Invalid value for '{source}': expected float, got "
                f"{type(raw_value).__name__} ({raw_value!r})."
            )
        return float(raw_value)

    if spec.value_kind == "str_list":
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
                raise ValueError(f"Invalid value for '{source}': expected non-empty items.")
            parsed.append(normalized)
        return tuple(parsed)

    if not isinstance(raw_value, str):
        raise ValueError(
            f"Invalid value for '{source}': expected str, got "
            f"{type(raw_value).__name__} ({raw_value!r})."
        )

    normalized = raw_value.strip()
    if not normalized:
        raise ValueError(f"Invalid value for '{source}': expected non-empty string.")

    if spec.value_kind == "verbosity":
        lowered = normalized.lower()
        if lowered not in _OUTPUT_VERBOSITY_PRESETS:
            raise ValueError(
                f"Invalid value for '{source}': expected one of "
                f"{sorted(_OUTPUT_VERBOSITY_PRESETS)}, got {raw_value!r}."
            )
        return lowered

    if spec.canonical_key == "permissions.default_tier" and normalized.lower() == "danger":
        raise ValueError("Invalid default_permission_tier: 'danger' is not allowed in config.")

    return normalized


def _parse_cli_value(spec: _ConfigKeySpec, raw_value: str) -> object:
    normalized = raw_value.strip()

    if spec.value_kind == "int":
        try:
            return int(normalized)
        except ValueError as error:
            raise ValueError(
                f"Invalid value for '{spec.canonical_key}': expected int, got {raw_value!r}."
            ) from error

    if spec.value_kind == "float":
        try:
            return float(normalized)
        except ValueError as error:
            raise ValueError(
                f"Invalid value for '{spec.canonical_key}': expected float, got {raw_value!r}."
            ) from error

    if spec.value_kind == "str_list":
        if not normalized:
            raise ValueError(
                f"Invalid value for '{spec.canonical_key}': expected comma-separated values."
            )

        items: list[str]
        if normalized.startswith("["):
            try:
                parsed_obj = tomllib.loads(f"value = {normalized}")["value"]
            except tomllib.TOMLDecodeError as error:
                raise ValueError(
                    f"Invalid TOML array for '{spec.canonical_key}': {raw_value!r}."
                ) from error
            if not isinstance(parsed_obj, list):
                raise ValueError(
                    f"Invalid value for '{spec.canonical_key}': expected array[str]."
                )
            items = [str(item).strip() for item in cast("list[object]", parsed_obj)]
        else:
            items = [part.strip() for part in normalized.split(",")]

        filtered = [item for item in items if item]
        if not filtered:
            raise ValueError(
                f"Invalid value for '{spec.canonical_key}': expected non-empty items."
            )
        return tuple(filtered)

    if not normalized:
        raise ValueError(f"Invalid value for '{spec.canonical_key}': expected non-empty string.")

    if spec.value_kind == "verbosity":
        lowered = normalized.lower()
        if lowered not in _OUTPUT_VERBOSITY_PRESETS:
            raise ValueError(
                f"Invalid value for '{spec.canonical_key}': expected one of "
                f"{sorted(_OUTPUT_VERBOSITY_PRESETS)}, got {raw_value!r}."
            )
        return lowered

    if spec.canonical_key == "permissions.default_tier" and normalized.lower() == "danger":
        raise ValueError("Invalid default_permission_tier: 'danger' is not allowed in config.")

    return normalized


def _extract_file_overrides(payload: dict[str, object]) -> dict[str, object]:
    overrides: dict[str, object] = {}

    for key, raw_value in payload.items():
        if isinstance(raw_value, dict):
            section_values = cast("dict[str, object]", raw_value)
            for section_key, section_value in section_values.items():
                spec = _CONFIG_KEY_ALIAS_MAP.get(f"{key}.{section_key}")
                if spec is None:
                    continue
                overrides[spec.canonical_key] = _parse_toml_value(
                    spec,
                    section_value,
                    source=f"{key}.{section_key}",
                )
            continue

        spec = _CONFIG_KEY_ALIAS_MAP.get(key)
        if spec is None:
            continue
        overrides[spec.canonical_key] = _parse_toml_value(spec, raw_value, source=key)

    return overrides


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, list | tuple):
        items = cast("list[object] | tuple[object, ...]", value)
        return "[" + ", ".join(_toml_literal(item) for item in items) + "]"
    raise ValueError(f"Unsupported config value type: {type(value).__name__}")


def _render_config_toml(overrides: dict[str, object]) -> str:
    sections: dict[str, dict[str, object]] = {name: {} for name in _SECTION_ORDER}

    for spec in _CONFIG_KEY_SPECS:
        if spec.canonical_key not in overrides:
            continue
        sections[spec.section][spec.file_key] = overrides[spec.canonical_key]

    lines: list[str] = []
    for section_name in _SECTION_ORDER:
        values = sections[section_name]
        if not values:
            continue

        if lines:
            lines.append("")
        lines.append(f"[{section_name}]")
        for key, value in values.items():
            lines.append(f"{key} = {_toml_literal(value)}")

    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def _source_for_key(
    spec: _ConfigKeySpec,
    *,
    project_overrides: dict[str, object],
    user_overrides: dict[str, object],
) -> tuple[Literal["builtin", "file", "user-config", "env var"], str | None]:
    env_var = spec.env_var
    if env_var is not None and os.getenv(env_var) is not None:
        return "env var", env_var
    if spec.canonical_key in user_overrides:
        return "user-config", None
    if spec.canonical_key in project_overrides:
        return "file", None
    return "builtin", None


def _user_config_path_from_env() -> Path | None:
    raw_value = os.getenv(_USER_CONFIG_ENV_VAR, "").strip()
    if not raw_value:
        return None
    return Path(raw_value).expanduser()


def _format_value_for_text(value: object) -> str:
    payload = to_jsonable(value)
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, sort_keys=True)


def _scaffold_template() -> str:
    defaults = _default_values()
    output_show = defaults["output.show"]
    output_verbosity = defaults["output.verbosity"]
    primary_defaults = PrimaryConfig()
    search_path_defaults = SearchPathConfig()

    lines = [
        "# Meridian configuration.",
        "# All values shown are built-in defaults. Uncomment to override.",
        "# Environment variables (MERIDIAN_*) take precedence over file values.",
        "",
        "# -- Execution defaults -----------------------------------------------------",
        "[defaults]",
        "# Maximum agent nesting depth (int).",
        f"# max_depth = {defaults['defaults.max_depth']}",
        "# Retry attempts per failed run-agent call (int).",
        f"# max_retries = {defaults['defaults.max_retries']}",
        "# Delay multiplier between retries in seconds (float).",
        f"# retry_backoff_seconds = {defaults['defaults.retry_backoff_seconds']}",
        "# Profile name for the primary agent (str).",
        (
            "# default_primary_agent = "
            f"{_toml_literal(cast('str', defaults['defaults.default_primary_agent']))}"
        ),
        "# Profile name for the default non-primary agent (str).",
        f"# agent = {_toml_literal(cast('str', defaults['defaults.agent']))}",
        "",
        "# -- Timeout behavior -------------------------------------------------------",
        "[timeouts]",
        "# Grace period before force-killing processes (float seconds).",
        f"# kill_grace_seconds = {defaults['timeouts.kill_grace_seconds']}",
        "# Max seconds to wait for guardrail checks (float seconds).",
        f"# guardrail_seconds = {defaults['timeouts.guardrail_seconds']}",
        "# Max seconds to wait on run completion operations (float seconds).",
        f"# wait_seconds = {defaults['timeouts.wait_seconds']}",
        "",
        "# -- Permission defaults ----------------------------------------------------",
        "[permissions]",
        "# Default permission tier for non-primary sessions (str; valid: read-only,",
        "# workspace-write, full-access; 'danger' is not allowed in config).",
        f"# default_tier = {_toml_literal(cast('str', defaults['permissions.default_tier']))}",
        "",
        "# -- Primary agent defaults -------------------------------------------------",
        "[primary]",
        "# Context compaction threshold for the primary agent (int 1-100).",
        f"# autocompact_pct = {primary_defaults.autocompact_pct}",
        "# Permission tier for primary sessions (str; valid: read-only,",
        "# workspace-write, full-access; 'danger' is not allowed in config).",
        f"# permission_tier = {_toml_literal(primary_defaults.permission_tier)}",
        "",
        "# -- Output streaming -------------------------------------------------------",
        "[output]",
        "# Event categories shown while streaming output (array[str]).",
        f"# show = {_toml_literal(cast('tuple[str, ...]', output_show))}",
        "# Output verbosity preset (str; valid: quiet, normal, verbose, debug).",
        (
            "# verbosity = "
            f"{_toml_literal(cast('str', output_verbosity))}"
            if isinstance(output_verbosity, str)
            else "# verbosity = \"normal\"  # example override; default is unset"
        ),
        "",
        "# -- Profile and skill discovery paths -------------------------------------",
        "[search_paths]",
        "# Agent profile search directories (array[str]; first match wins).",
        f"# agents = {_toml_literal(search_path_defaults.agents)}",
        "# Skill definition search directories (array[str]).",
        f"# skills = {_toml_literal(search_path_defaults.skills)}",
        "# Global/user-level agent profile directories (array[str]).",
        f"# global_agents = {_toml_literal(search_path_defaults.global_agents)}",
        "# Global/user-level skill directories (array[str]).",
        f"# global_skills = {_toml_literal(search_path_defaults.global_skills)}",
        "",
    ]
    return "\n".join(lines)


def config_init_sync(payload: ConfigInitInput) -> ConfigInitOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)
    if path.exists():
        return ConfigInitOutput(path=path.as_posix(), created=False)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_scaffold_template(), encoding="utf-8")
    return ConfigInitOutput(path=path.as_posix(), created=True)


def config_show_sync(payload: ConfigShowInput) -> ConfigShowOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)
    project_overrides = _extract_file_overrides(_read_file_payload(path))
    user_path = _user_config_path_from_env()
    user_overrides = (
        _extract_file_overrides(_read_file_payload(user_path))
        if user_path is not None
        else {}
    )

    resolved_config = load_config(repo_root)
    resolved_values = _resolved_values(resolved_config)

    values: list[ConfigResolvedValue] = []
    for spec in _CONFIG_KEY_SPECS:
        source, env_var = _source_for_key(
            spec,
            project_overrides=project_overrides,
            user_overrides=user_overrides,
        )
        values.append(
            ConfigResolvedValue(
                key=spec.canonical_key,
                value=resolved_values[spec.canonical_key],
                source=source,
                env_var=env_var,
            )
        )

    warning: str | None = None
    if not repo_root.exists():
        warning = f"Resolved repo root '{repo_root.as_posix()}' does not exist on disk."

    return ConfigShowOutput(path=path.as_posix(), values=tuple(values), warning=warning)


def config_set_sync(payload: ConfigSetInput) -> ConfigSetOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)

    spec = _resolve_key_spec(payload.key)
    value = _parse_cli_value(spec, payload.value)

    file_overrides = _extract_file_overrides(_read_file_payload(path))
    file_overrides[spec.canonical_key] = value

    _atomic_write_text(path, _render_config_toml(file_overrides))

    return ConfigSetOutput(
        path=path.as_posix(),
        key=spec.canonical_key,
        value=_normalize_runtime_value(value),
    )


def config_get_sync(payload: ConfigGetInput) -> ConfigGetOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)
    spec = _resolve_key_spec(payload.key)

    project_overrides = _extract_file_overrides(_read_file_payload(path))
    user_path = _user_config_path_from_env()
    user_overrides = (
        _extract_file_overrides(_read_file_payload(user_path))
        if user_path is not None
        else {}
    )
    source, env_var = _source_for_key(
        spec,
        project_overrides=project_overrides,
        user_overrides=user_overrides,
    )

    resolved_values = _resolved_values(load_config(repo_root))

    return ConfigGetOutput(
        key=spec.canonical_key,
        value=resolved_values[spec.canonical_key],
        source=source,
        env_var=env_var,
    )


def config_reset_sync(payload: ConfigResetInput) -> ConfigResetOutput:
    repo_root = _resolve_repo_root(payload.repo_root)
    path = _config_path(repo_root)
    spec = _resolve_key_spec(payload.key)

    file_overrides = _extract_file_overrides(_read_file_payload(path))
    removed = spec.canonical_key in file_overrides
    file_overrides.pop(spec.canonical_key, None)

    _atomic_write_text(path, _render_config_toml(file_overrides))

    return ConfigResetOutput(path=path.as_posix(), key=spec.canonical_key, removed=removed)


async def config_init(payload: ConfigInitInput) -> ConfigInitOutput:
    return await asyncio.to_thread(config_init_sync, payload)


async def config_show(payload: ConfigShowInput) -> ConfigShowOutput:
    return await asyncio.to_thread(config_show_sync, payload)


async def config_set(payload: ConfigSetInput) -> ConfigSetOutput:
    return await asyncio.to_thread(config_set_sync, payload)


async def config_get(payload: ConfigGetInput) -> ConfigGetOutput:
    return await asyncio.to_thread(config_get_sync, payload)


async def config_reset(payload: ConfigResetInput) -> ConfigResetOutput:
    return await asyncio.to_thread(config_reset_sync, payload)


operation(
    OperationSpec[ConfigInitInput, ConfigInitOutput](
        name="config.init",
        handler=config_init,
        sync_handler=config_init_sync,
        input_type=ConfigInitInput,
        output_type=ConfigInitOutput,
        cli_group="config",
        cli_name="init",
        mcp_name="config_init",
        description="Scaffold .meridian/config.toml with commented defaults.",
        cli_only=True,
    )
)

operation(
    OperationSpec[ConfigShowInput, ConfigShowOutput](
        name="config.show",
        handler=config_show,
        sync_handler=config_show_sync,
        input_type=ConfigShowInput,
        output_type=ConfigShowOutput,
        cli_group="config",
        cli_name="show",
        mcp_name="config_show",
        description="Show resolved config values with source annotations.",
        cli_only=True,
    )
)

operation(
    OperationSpec[ConfigSetInput, ConfigSetOutput](
        name="config.set",
        handler=config_set,
        sync_handler=config_set_sync,
        input_type=ConfigSetInput,
        output_type=ConfigSetOutput,
        cli_group="config",
        cli_name="set",
        mcp_name="config_set",
        description="Set one config key in .meridian/config.toml.",
        cli_only=True,
    )
)

operation(
    OperationSpec[ConfigGetInput, ConfigGetOutput](
        name="config.get",
        handler=config_get,
        sync_handler=config_get_sync,
        input_type=ConfigGetInput,
        output_type=ConfigGetOutput,
        cli_group="config",
        cli_name="get",
        mcp_name="config_get",
        description="Get one resolved config key with source annotation.",
        cli_only=True,
    )
)

operation(
    OperationSpec[ConfigResetInput, ConfigResetOutput](
        name="config.reset",
        handler=config_reset,
        sync_handler=config_reset_sync,
        input_type=ConfigResetInput,
        output_type=ConfigResetOutput,
        cli_group="config",
        cli_name="reset",
        mcp_name="config_reset",
        description="Remove one config key from file overrides.",
        cli_only=True,
    )
)
