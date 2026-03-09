"""Sync source configuration models and TOML I/O."""


import re
import tomllib
from pathlib import Path
from typing import cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)
from meridian.lib.state.atomic import atomic_write_text

_SOURCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_SYNC_SOURCE_HEADER_PATTERN = re.compile(r"(?m)^\s*\[\[sync\.sources\]\]\s*$")
_TOP_LEVEL_HEADER_PATTERN = re.compile(r"(?m)^\s*\[")


class SyncSourceConfig(BaseModel):
    """One configured sync source."""

    model_config = ConfigDict(frozen=True)

    name: str
    repo: str | None = None
    path: str | None = None
    ref: str | None = None
    skills: tuple[str, ...] | None = None
    agents: tuple[str, ...] | None = None
    exclude_skills: tuple[str, ...] = ()
    exclude_agents: tuple[str, ...] = ()
    rename: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Invalid value for 'name': expected non-empty string.")
        if _SOURCE_NAME_PATTERN.fullmatch(normalized) is None:
            raise ValueError(
                "Invalid value for 'name': expected alphanumeric characters, hyphens, "
                "or underscores."
            )
        return normalized

    @field_validator("repo")
    @classmethod
    def _validate_repo(cls, value: str | None) -> str | None:
        normalized = _normalize_optional_string(value, source="repo")
        if normalized is None:
            return None

        owner, separator, repo_name = normalized.partition("/")
        if separator != "/" or "/" in repo_name or not owner or not repo_name:
            raise ValueError(
                "Invalid value for 'repo': expected GitHub shorthand in 'owner/repo' format."
            )
        return normalized

    @field_validator("path", "ref")
    @classmethod
    def _validate_optional_strings(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        field_name = info.field_name
        if field_name is None:
            raise ValueError("Sync config validator missing field name.")
        return _normalize_optional_string(value, source=field_name)

    @field_validator("skills", "agents", "exclude_skills", "exclude_agents", mode="before")
    @classmethod
    def _validate_filters(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> tuple[str, ...] | None:
        field_name = info.field_name
        if field_name is None:
            raise ValueError("Sync config validator missing field name.")
        if value is None:
            if field_name in {"skills", "agents"}:
                return None
            return ()
        return _normalize_string_tuple(value, source=field_name)

    @field_validator("rename", mode="before")
    @classmethod
    def _validate_rename_map(cls, value: object) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("Invalid value for 'rename': expected table.")

        normalized: dict[str, str] = {}
        for raw_key, raw_value in cast("dict[object, object]", value).items():
            if not isinstance(raw_key, str) or not isinstance(raw_value, str):
                raise ValueError(
                    "Invalid value for 'rename': expected string-to-string mappings."
                )

            key = raw_key.strip()
            renamed = raw_value.strip()
            if not key or not renamed:
                raise ValueError(
                    "Invalid value for 'rename': expected non-empty keys and values."
                )
            normalized[key] = renamed
        return normalized

    @model_validator(mode="after")
    def _validate_source_selector(self) -> "SyncSourceConfig":
        has_repo = self.repo is not None
        has_path = self.path is not None
        if has_repo == has_path:
            raise ValueError("Exactly one of 'repo' or 'path' must be set.")
        if self.ref is not None and self.repo is None:
            raise ValueError("Invalid value for 'ref': 'ref' is only valid with 'repo'.")
        return self


class SyncConfig(BaseModel):
    """Top-level sync configuration."""

    model_config = ConfigDict(frozen=True)

    sources: tuple[SyncSourceConfig, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_names(self) -> "SyncConfig":
        seen: set[str] = set()
        for source in self.sources:
            if source.name in seen:
                raise ValueError(f"Duplicate sync source name: '{source.name}'.")
            seen.add(source.name)
        return self


class _SourceBlock(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: int
    end: int
    name: str


def load_sync_config(config_path: Path) -> SyncConfig:
    """Load sync configuration from a project config TOML file."""

    if not config_path.is_file():
        return SyncConfig()

    raw_text = config_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return SyncConfig()

    payload_obj = tomllib.loads(raw_text)
    payload = cast("dict[str, object]", payload_obj)

    raw_sync = payload.get("sync")
    if raw_sync is None:
        return SyncConfig()
    if not isinstance(raw_sync, dict):
        raise ValueError("Invalid value for 'sync': expected table.")

    raw_sources = cast("dict[str, object]", raw_sync).get("sources")
    if raw_sources is None:
        return SyncConfig()
    if not isinstance(raw_sources, list):
        raise ValueError("Invalid value for 'sync.sources': expected array of tables.")

    normalized_sources = cast("list[dict[str, object]]", raw_sources)
    parsed_sources = tuple(SyncSourceConfig.model_validate(item) for item in normalized_sources)
    return SyncConfig(sources=parsed_sources)


def add_sync_source(config_path: Path, source: SyncSourceConfig) -> None:
    """Append a sync source entry to a project config TOML file."""

    existing_config = load_sync_config(config_path)
    if any(existing.name == source.name for existing in existing_config.sources):
        raise ValueError(f"Sync source '{source.name}' already exists.")

    current_text = ""
    if config_path.is_file():
        current_text = config_path.read_text(encoding="utf-8")

    block = _render_source_block(source)
    if current_text.strip():
        updated_text = current_text.rstrip("\n") + "\n\n" + block
    else:
        updated_text = block

    _atomic_write_text(config_path, updated_text)


def remove_sync_source(config_path: Path, name: str) -> None:
    """Remove one sync source entry from a project config TOML file."""

    existing_config = load_sync_config(config_path)
    if not any(source.name == name for source in existing_config.sources):
        raise ValueError(f"Sync source '{name}' not found.")

    current_text = config_path.read_text(encoding="utf-8")
    blocks = _parse_sync_source_blocks(current_text)
    target_block = next((block for block in blocks if block.name == name), None)
    if target_block is None:
        raise ValueError(f"Sync source '{name}' could not be removed from TOML.")

    updated_text = current_text[: target_block.start] + current_text[target_block.end :]
    _atomic_write_text(config_path, updated_text)


def _normalize_optional_string(raw: str | None, *, source: str) -> str | None:
    if raw is None:
        return None
    normalized = raw.strip()
    if not normalized:
        raise ValueError(f"Invalid value for '{source}': expected non-empty string.")
    return normalized


def _normalize_string_tuple(value: object, *, source: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        raise ValueError(f"Invalid value for '{source}': expected array[str].")

    normalized: list[str] = []
    for item in cast("list[object] | tuple[object, ...]", value):
        if not isinstance(item, str):
            raise ValueError(f"Invalid value for '{source}': expected array[str].")
        compact = item.strip()
        if not compact:
            raise ValueError(
                f"Invalid value for '{source}': expected non-empty entries."
            )
        normalized.append(compact)
    return tuple(normalized)


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
    raise ValueError(f"Unsupported sync config value type: {type(value).__name__}.")


def _toml_inline_table(value: dict[str, str]) -> str:
    items = [
        f"{_toml_string(key)} = {_toml_string(mapped)}"
        for key, mapped in sorted(value.items())
    ]
    return "{ " + ", ".join(items) + " }"


def _render_source_block(source: SyncSourceConfig) -> str:
    lines = ["[[sync.sources]]", f"name = {_toml_literal(source.name)}"]
    if source.repo is not None:
        lines.append(f"repo = {_toml_literal(source.repo)}")
    if source.path is not None:
        lines.append(f"path = {_toml_literal(source.path)}")
    if source.ref is not None:
        lines.append(f"ref = {_toml_literal(source.ref)}")
    if source.skills is not None:
        lines.append(f"skills = {_toml_literal(source.skills)}")
    if source.agents is not None:
        lines.append(f"agents = {_toml_literal(source.agents)}")
    if source.exclude_skills:
        lines.append(f"exclude_skills = {_toml_literal(source.exclude_skills)}")
    if source.exclude_agents:
        lines.append(f"exclude_agents = {_toml_literal(source.exclude_agents)}")
    if source.rename:
        lines.append(f"rename = {_toml_inline_table(source.rename)}")
    return "\n".join(lines) + "\n"


def _parse_sync_source_blocks(text: str) -> tuple[_SourceBlock, ...]:
    matches = list(_SYNC_SOURCE_HEADER_PATTERN.finditer(text))
    if not matches:
        return ()

    blocks: list[_SourceBlock] = []
    for index, match in enumerate(matches):
        start = match.start()
        search_start = match.end()
        next_header = None

        next_source_start = matches[index + 1].start() if index + 1 < len(matches) else None
        next_table_match = _TOP_LEVEL_HEADER_PATTERN.search(text, search_start)
        if next_table_match is not None:
            next_header = next_table_match.start()
        if next_source_start is not None and (
            next_header is None or next_source_start < next_header
        ):
            next_header = next_source_start

        end = len(text) if next_header is None else next_header
        block_text = text[start:end]
        block_name = _extract_source_name_from_block(block_text)
        blocks.append(_SourceBlock(start=start, end=end, name=block_name))

    return tuple(blocks)


def _extract_source_name_from_block(block_text: str) -> str:
    payload_obj = tomllib.loads(block_text)
    payload = cast("dict[str, object]", payload_obj)
    sync_payload = cast("dict[str, object]", payload["sync"])
    sources = cast("list[object]", sync_payload["sources"])
    source = cast("dict[str, object]", sources[0])
    raw_name = source.get("name")
    if not isinstance(raw_name, str):
        raise ValueError("Invalid sync source block: missing string 'name'.")
    return raw_name.strip()


def _atomic_write_text(path: Path, content: str) -> None:
    atomic_write_text(path, content)
