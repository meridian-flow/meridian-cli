"""Config file management operations."""

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from meridian.lib.config.project_config_state import (
    ProjectConfigState,
    resolve_project_config_state,
)
from meridian.lib.config.settings import (
    MeridianConfig,
    PrimaryConfig,
    resolve_project_root,
)
from meridian.lib.config.workspace import WorkspaceFinding
from meridian.lib.core.util import FormatContext, to_jsonable
from meridian.lib.ops.config_surface import (
    ConfigSurface,
    ConfigSurfaceWorkspace,
    build_config_surface,
)
from meridian.lib.ops.runtime import async_from_sync
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.paths import (
    StateRootPaths,
    ensure_gitignore,
    resolve_repo_state_paths,
    resolve_runtime_state_root,
)

_SECTION_ORDER: tuple[str, ...] = ("defaults", "timeouts", "harness", "primary", "output")
_OUTPUT_VERBOSITY_PRESETS = frozenset({"quiet", "normal", "verbose", "debug"})
_MISSING_PROJECT_CONFIG_MESSAGE = "no project config; run `meridian config init`"


class _ConfigKeySpec(BaseModel):
    model_config = ConfigDict(frozen=True)

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
        canonical_key="defaults.model",
        section="defaults",
        file_key="model",
        field_path=("default_model",),
        value_kind="str",
        env_var="MERIDIAN_DEFAULT_MODEL",
        aliases=("defaults.default_model", "default_model"),
    ),
    _ConfigKeySpec(
        canonical_key="defaults.harness",
        section="defaults",
        file_key="harness",
        field_path=("default_harness",),
        value_kind="str",
        env_var="MERIDIAN_DEFAULT_HARNESS",
        aliases=("defaults.default_harness", "default_harness"),
    ),
    _ConfigKeySpec(
        canonical_key="timeouts.kill_grace_minutes",
        section="timeouts",
        file_key="kill_grace_minutes",
        field_path=("kill_grace_minutes",),
        value_kind="float",
        env_var="MERIDIAN_KILL_GRACE_MINUTES",
        aliases=("kill_grace_minutes",),
    ),
    _ConfigKeySpec(
        canonical_key="timeouts.guardrail_minutes",
        section="timeouts",
        file_key="guardrail_minutes",
        field_path=("guardrail_timeout_minutes",),
        value_kind="float",
        env_var="MERIDIAN_GUARDRAIL_TIMEOUT_MINUTES",
        aliases=("timeouts.guardrail_timeout_minutes", "guardrail_timeout_minutes"),
    ),
    _ConfigKeySpec(
        canonical_key="timeouts.wait_minutes",
        section="timeouts",
        file_key="wait_minutes",
        field_path=("wait_timeout_minutes",),
        value_kind="float",
        env_var="MERIDIAN_WAIT_TIMEOUT_MINUTES",
        aliases=("timeouts.wait_timeout_minutes", "wait_timeout_minutes"),
    ),
    _ConfigKeySpec(
        canonical_key="harness.claude",
        section="harness",
        file_key="claude",
        field_path=("harness", "claude"),
        value_kind="str",
        env_var="MERIDIAN_HARNESS_MODEL_CLAUDE",
    ),
    _ConfigKeySpec(
        canonical_key="harness.codex",
        section="harness",
        file_key="codex",
        field_path=("harness", "codex"),
        value_kind="str",
        env_var="MERIDIAN_HARNESS_MODEL_CODEX",
    ),
    _ConfigKeySpec(
        canonical_key="harness.opencode",
        section="harness",
        file_key="opencode",
        field_path=("harness", "opencode"),
        value_kind="str",
        env_var="MERIDIAN_HARNESS_MODEL_OPENCODE",
    ),
    _ConfigKeySpec(
        canonical_key="primary.autocompact_pct",
        section="primary",
        file_key="autocompact_pct",
        field_path=("primary", "autocompact_pct"),
        value_kind="int",
        aliases=("autocompact_pct",),
    ),
    _ConfigKeySpec(
        canonical_key="primary.model",
        section="primary",
        file_key="model",
        field_path=("primary", "model"),
        value_kind="str",
        env_var="MERIDIAN_MODEL",
        aliases=(),
    ),
    _ConfigKeySpec(
        canonical_key="primary.harness",
        section="primary",
        file_key="harness",
        field_path=("primary", "harness"),
        value_kind="str",
        env_var="MERIDIAN_HARNESS",
        aliases=(),
    ),
    _ConfigKeySpec(
        canonical_key="primary.agent",
        section="primary",
        file_key="agent",
        field_path=("primary", "agent"),
        value_kind="str",
        env_var="MERIDIAN_AGENT",
        aliases=(),
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


class ConfigInitInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class ConfigInitOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    created: bool

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        status = "created" if self.created else "exists"
        return f"{status}: {self.path}"


class ConfigShowInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    repo_root: str | None = None


class ConfigResolvedValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    value: object
    source: Literal["builtin", "file", "user-config", "env var"]
    env_var: str | None = None


class ConfigShowOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    workspace: ConfigSurfaceWorkspace
    values: tuple[ConfigResolvedValue, ...]
    workspace_findings: tuple[WorkspaceFinding, ...] = Field(default=(), exclude=True)
    warning: str | None = None

    @field_serializer("workspace")
    def _serialize_workspace(self, value: ConfigSurfaceWorkspace) -> dict[str, object]:
        return value.model_dump(exclude_none=True)

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        lines = [f"path: {self.path}"]
        lines.append(f"workspace.status = {self.workspace.status}")
        if self.workspace.path is not None:
            lines.append(f"workspace.path = {self.workspace.path}")
        lines.append(f"workspace.roots.count = {self.workspace.roots.count}")
        lines.append(f"workspace.roots.enabled = {self.workspace.roots.enabled}")
        lines.append(f"workspace.roots.missing = {self.workspace.roots.missing}")
        for harness in ("claude", "codex", "opencode"):
            applicability = self.workspace.applicability.get(harness)
            if applicability is None:
                continue
            lines.append(f"workspace.applicability.{harness} = {applicability}")
        if self.warning is not None:
            lines.append(f"warning: {self.warning}")
        for finding in self.workspace_findings:
            lines.append(f"warning: {finding.code}: {finding.message}")
        for item in self.values:
            source_note = item.source
            if item.env_var is not None:
                source_note = f"{source_note} ({item.env_var})"
            lines.append(
                f"{item.key}: {_format_value_for_text(item.value)} [source: {source_note}]"
            )
        return "\n".join(lines)


class ConfigSetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    value: str
    repo_root: str | None = None


class ConfigSetOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    key: str
    value: object

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        return f"set {self.key} = {_format_value_for_text(self.value)} in {self.path}"


class ConfigGetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    repo_root: str | None = None


class ConfigGetOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    value: object
    source: Literal["builtin", "file", "user-config", "env var"]
    env_var: str | None = None

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        source_note = self.source if self.env_var is None else f"{self.source} ({self.env_var})"
        return f"{self.key}: {_format_value_for_text(self.value)} [source: {source_note}]"


class ConfigResetInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str
    repo_root: str | None = None


class ConfigResetOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    path: str
    key: str
    removed: bool

    def format_text(self, ctx: FormatContext | None = None) -> str:
        _ = ctx
        status = "removed" if self.removed else "already-default"
        return f"reset {self.key} ({status}) in {self.path}"


@dataclass(frozen=True)
class _ConfigInspectionState:
    surface: ConfigSurface
    project_overrides: dict[str, object]
    user_overrides: dict[str, object]
    resolved_values: dict[str, object]


def _resolve_project_config_state(repo_root: Path) -> ProjectConfigState:
    return resolve_project_config_state(repo_root)


def _require_project_config_path(state: ProjectConfigState) -> Path:
    if state.path is None:
        raise ValueError(_MISSING_PROJECT_CONFIG_MESSAGE)
    return state.path


def _resolve_project_root(repo_root: str | None) -> Path:
    explicit = Path(repo_root).expanduser().resolve() if repo_root else None
    return resolve_project_root(explicit)


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
                raise ValueError(f"Invalid value for '{spec.canonical_key}': expected array[str].")
            items = [str(item).strip() for item in cast("list[object]", parsed_obj)]
        else:
            items = [part.strip() for part in normalized.split(",")]

        filtered = [item for item in items if item]
        if not filtered:
            raise ValueError(f"Invalid value for '{spec.canonical_key}': expected non-empty items.")
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


def _source_for_key(
    spec: _ConfigKeySpec,
    *,
    project_overrides: dict[str, object],
    user_overrides: dict[str, object],
) -> tuple[Literal["builtin", "file", "user-config", "env var"], str | None]:
    env_var = spec.env_var
    if env_var is not None and os.getenv(env_var) is not None:
        return "env var", env_var
    if spec.canonical_key in project_overrides:
        return "file", None
    if spec.canonical_key in user_overrides:
        return "user-config", None
    return "builtin", None


def _build_config_inspection_state(repo_root: Path) -> _ConfigInspectionState:
    surface = build_config_surface(repo_root)
    project_overrides = _extract_file_overrides(
        _read_file_payload(surface.project_config.write_path)
    )
    user_overrides = (
        _extract_file_overrides(_read_file_payload(surface.user_config_path))
        if surface.user_config_path is not None
        else {}
    )
    resolved_values = _resolved_values(surface.resolved_config)
    return _ConfigInspectionState(
        surface=surface,
        project_overrides=project_overrides,
        user_overrides=user_overrides,
        resolved_values=resolved_values,
    )


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

    lines = [
        "# Meridian configuration.",
        "# All values shown are built-in defaults. Uncomment to override.",
        "# Environment variables (MERIDIAN_*) take precedence over file values.",
        "",
        "# -- Execution defaults -----------------------------------------------------",
        "[defaults]",
        "# Maximum agent nesting depth (int).",
        f"# max_depth = {defaults['defaults.max_depth']}",
        "# Retry attempts per failed spawn (int).",
        f"# max_retries = {defaults['defaults.max_retries']}",
        "# Delay multiplier between retries in seconds (float).",
        f"# retry_backoff_seconds = {defaults['defaults.retry_backoff_seconds']}",
        "# Default model for spawns when --model and profile model are both unset",
        "# (str model id).",
        f"# model = {_toml_literal(cast('str', defaults['defaults.model']))}",
        "# Default harness for spawns when higher-precedence values and profile harness are unset.",
        f"# harness = {_toml_literal(cast('str', defaults['defaults.harness']))}",
        "",
        "# -- Timeout behavior -------------------------------------------------------",
        "[timeouts]",
        "# Grace period before force-killing processes (float minutes).",
        f"# kill_grace_minutes = {defaults['timeouts.kill_grace_minutes']}",
        "# Max minutes to wait for guardrail checks (float minutes).",
        f"# guardrail_minutes = {defaults['timeouts.guardrail_minutes']}",
        "# Max minutes to wait on run completion operations (float minutes).",
        f"# wait_minutes = {defaults['timeouts.wait_minutes']}",
        "",
        "# -- Harness default models ------------------------------------------------",
        "[harness]",
        "# Default model for Claude harness (str model id).",
        (
            "# claude = "
            f"{_toml_literal(cast('str', defaults['harness.claude']))}  "
            "# empty = harness picks its own default model"
        ),
        "# Default model for Codex harness (str model id).",
        (
            "# codex = "
            f"{_toml_literal(cast('str', defaults['harness.codex']))}  "
            "# empty = harness picks its own default model"
        ),
        "# Default model for OpenCode harness (str model id).",
        (
            "# opencode = "
            f"{_toml_literal(cast('str', defaults['harness.opencode']))}  "
            "# empty = harness picks its own default model"
        ),
        "",
        "# -- Primary agent defaults -------------------------------------------------",
        "[primary]",
        "# Context compaction threshold for the primary agent (int 1-100).",
        f"# autocompact_pct = {primary_defaults.autocompact_pct or 65}",
        "# Model override for the primary agent (str model id; unset = use defaults.model).",
        '# model = ""',
        "# Harness override for the primary agent (str; unset = use defaults.harness).",
        '# harness = ""',
        "# Agent profile name for the primary session (str; unset = no profile).",
        '# agent = ""',
        "",
        "# -- Output streaming -------------------------------------------------------",
        "[output]",
        "# Event categories shown while streaming output (array[str]).",
        f"# show = {_toml_literal(cast('tuple[str, ...]', output_show))}",
        "# Output verbosity preset (str; valid: quiet, normal, verbose, debug).",
        (
            f"# verbosity = {_toml_literal(output_verbosity)}"
            if isinstance(output_verbosity, str)
            else '# verbosity = "normal"  # example override; default is unset'
        ),
        "",
    ]
    return "\n".join(lines)


def ensure_runtime_state_bootstrap_sync(repo_root: Path) -> None:
    """Ensure first-run runtime state exists without creating project-root files."""

    repo_state = resolve_repo_state_paths(repo_root)
    repo_dirs = (
        repo_state.root_dir,
        repo_state.fs_dir,
        repo_state.work_dir,
        repo_state.work_archive_dir,
    )
    for dir_path in repo_dirs:
        dir_path.mkdir(parents=True, exist_ok=True)

    runtime_root = resolve_runtime_state_root(repo_root)
    runtime_state = StateRootPaths.from_root_dir(runtime_root)
    runtime_dirs = (
        runtime_state.root_dir,
        runtime_state.spawns_dir,
    )
    for dir_path in runtime_dirs:
        dir_path.mkdir(parents=True, exist_ok=True)
    ensure_gitignore(repo_root)


def ensure_state_bootstrap_sync(repo_root: Path) -> ConfigInitOutput:
    """Ensure runtime state exists and scaffold project config when missing."""

    ensure_runtime_state_bootstrap_sync(repo_root)
    state = _resolve_project_config_state(repo_root)
    if state.path is not None:
        return ConfigInitOutput(path=state.path.as_posix(), created=False)

    atomic_write_text(state.write_path, _scaffold_template())
    return ConfigInitOutput(path=state.write_path.as_posix(), created=True)


def config_init_sync(payload: ConfigInitInput) -> ConfigInitOutput:
    # init targets explicit path, then MERIDIAN_REPO_ROOT, then CWD.
    if payload.repo_root:
        repo_root = Path(payload.repo_root).expanduser().resolve()
    else:
        env_root = os.getenv("MERIDIAN_REPO_ROOT", "").strip()
        repo_root = Path(env_root).expanduser().resolve() if env_root else Path.cwd().resolve()
    return ensure_state_bootstrap_sync(repo_root)


def config_show_sync(payload: ConfigShowInput) -> ConfigShowOutput:
    repo_root = _resolve_project_root(payload.repo_root)
    inspection = _build_config_inspection_state(repo_root)

    values: list[ConfigResolvedValue] = []
    for spec in _CONFIG_KEY_SPECS:
        source, env_var = _source_for_key(
            spec,
            project_overrides=inspection.project_overrides,
            user_overrides=inspection.user_overrides,
        )
        values.append(
            ConfigResolvedValue(
                key=spec.canonical_key,
                value=inspection.resolved_values[spec.canonical_key],
                source=source,
                env_var=env_var,
            )
        )

    return ConfigShowOutput(
        path=inspection.surface.project_config.write_path.as_posix(),
        workspace=inspection.surface.workspace,
        values=tuple(values),
        workspace_findings=inspection.surface.workspace_findings,
        warning=inspection.surface.warning,
    )


def config_set_sync(payload: ConfigSetInput) -> ConfigSetOutput:
    repo_root = _resolve_project_root(payload.repo_root)
    path = _require_project_config_path(_resolve_project_config_state(repo_root))

    spec = _resolve_key_spec(payload.key)
    value = _parse_cli_value(spec, payload.value)

    file_overrides = _extract_file_overrides(_read_file_payload(path))
    file_overrides[spec.canonical_key] = value

    atomic_write_text(path, _render_config_toml(file_overrides))

    return ConfigSetOutput(
        path=path.as_posix(),
        key=spec.canonical_key,
        value=_normalize_runtime_value(value),
    )


def config_get_sync(payload: ConfigGetInput) -> ConfigGetOutput:
    repo_root = _resolve_project_root(payload.repo_root)
    spec = _resolve_key_spec(payload.key)
    inspection = _build_config_inspection_state(repo_root)
    source, env_var = _source_for_key(
        spec,
        project_overrides=inspection.project_overrides,
        user_overrides=inspection.user_overrides,
    )

    return ConfigGetOutput(
        key=spec.canonical_key,
        value=inspection.resolved_values[spec.canonical_key],
        source=source,
        env_var=env_var,
    )


def config_reset_sync(payload: ConfigResetInput) -> ConfigResetOutput:
    repo_root = _resolve_project_root(payload.repo_root)
    path = _require_project_config_path(_resolve_project_config_state(repo_root))
    spec = _resolve_key_spec(payload.key)

    file_overrides = _extract_file_overrides(_read_file_payload(path))
    removed = spec.canonical_key in file_overrides
    file_overrides.pop(spec.canonical_key, None)

    atomic_write_text(path, _render_config_toml(file_overrides))

    return ConfigResetOutput(path=path.as_posix(), key=spec.canonical_key, removed=removed)


config_init = async_from_sync(config_init_sync)
config_show = async_from_sync(config_show_sync)
config_set = async_from_sync(config_set_sync)
config_get = async_from_sync(config_get_sync)
config_reset = async_from_sync(config_reset_sync)
