"""Managed install source manifest models and TOML I/O."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.sync.install_types import ItemRef, SourceKind, normalize_required_string, parse_item_id
from meridian.lib.sync.install_types import validate_source_name


class ManagedSourceConfig(BaseModel):
    """One declared managed source."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: SourceKind
    url: str | None = None
    path: str | None = None
    ref: str | None = None
    items: tuple[ItemRef, ...] | None = None
    exclude_items: tuple[ItemRef, ...] = ()
    rename: dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        return validate_source_name(value)

    @field_validator("url", "path", "ref")
    @classmethod
    def _validate_optional_strings(
        cls,
        value: str | None,
        info: ValidationInfo,
    ) -> str | None:
        if value is None:
            return None
        field_name = info.field_name
        if field_name is None:
            raise ValueError("Managed source validator missing field name.")
        return normalize_required_string(value, source=field_name)

    @field_validator("items", "exclude_items", mode="before")
    @classmethod
    def _validate_item_refs(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> tuple[ItemRef, ...] | None:
        if value is None:
            return None if info.field_name == "items" else ()
        if not isinstance(value, list | tuple):
            raise ValueError("Invalid item selector list: expected array of tables.")

        refs: list[ItemRef] = []
        for raw_item in cast("list[object] | tuple[object, ...]", value):
            if isinstance(raw_item, ItemRef):
                refs.append(raw_item)
                continue
            if not isinstance(raw_item, dict):
                raise ValueError("Invalid item selector list: expected array of tables.")
            refs.append(ItemRef.model_validate(cast("dict[str, object]", raw_item)))
        return tuple(refs)

    @field_validator("rename", mode="before")
    @classmethod
    def _validate_rename(cls, value: object) -> dict[str, str]:
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
            key = normalize_required_string(raw_key, source="rename")
            parse_item_id(key)
            normalized[key] = normalize_required_string(raw_value, source="rename")
        return normalized

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> "ManagedSourceConfig":
        if self.kind == "git":
            if self.url is None or self.path is not None:
                raise ValueError("Git sources require 'url' and must not set 'path'.")
            return self

        if self.path is None or self.url is not None:
            raise ValueError("Path sources require 'path' and must not set 'url'.")
        if self.ref is not None:
            raise ValueError("Path sources must not set 'ref'.")
        return self


class ManagedSourcesConfig(BaseModel):
    """Top-level `.meridian/agents.toml` content."""

    model_config = ConfigDict(frozen=True)

    sources: tuple[ManagedSourceConfig, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_names(self) -> "ManagedSourcesConfig":
        seen: set[str] = set()
        for source in self.sources:
            if source.name in seen:
                raise ValueError(f"Duplicate managed source name: '{source.name}'.")
            seen.add(source.name)
        return self


def load_install_config(config_path: Path) -> ManagedSourcesConfig:
    """Load `.meridian/agents.toml`."""

    if not config_path.is_file():
        return ManagedSourcesConfig()

    raw_text = config_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return ManagedSourcesConfig()

    payload_obj = tomllib.loads(raw_text)
    payload = cast("dict[str, object]", payload_obj)
    raw_sources = payload.get("sources")
    if raw_sources is None:
        return ManagedSourcesConfig()
    if not isinstance(raw_sources, list):
        raise ValueError("Invalid value for 'sources': expected array of tables.")

    sources = tuple(
        ManagedSourceConfig.model_validate(cast("dict[str, object]", raw_source))
        for raw_source in cast("list[object]", raw_sources)
    )
    return ManagedSourcesConfig(sources=sources)


def write_install_config(config_path: Path, config: ManagedSourcesConfig) -> None:
    """Write `.meridian/agents.toml` atomically."""

    lines: list[str] = []
    for source in config.sources:
        if lines:
            lines.append("")
        lines.extend(_render_source_block(source))

    payload = "\n".join(lines)
    if payload:
        payload += "\n"
    atomic_write_text(config_path, payload)


def _render_source_block(source: ManagedSourceConfig) -> list[str]:
    lines = ["[[sources]]"]
    lines.append(f'name = {_toml_string(source.name)}')
    lines.append(f'kind = {_toml_string(source.kind)}')
    if source.url is not None:
        lines.append(f'url = {_toml_string(source.url)}')
    if source.path is not None:
        lines.append(f'path = {_toml_string(source.path)}')
    if source.ref is not None:
        lines.append(f'ref = {_toml_string(source.ref)}')
    if source.items is not None:
        lines.append(f"items = {_render_item_ref_list(source.items)}")
    if source.exclude_items:
        lines.append(f"exclude_items = {_render_item_ref_list(source.exclude_items)}")
    if source.rename:
        mappings = ", ".join(
            f"{_toml_string(key)} = {_toml_string(value)}"
            for key, value in sorted(source.rename.items())
        )
        lines.append(f"rename = {{ {mappings} }}")
    return lines


def _render_item_ref_list(items: tuple[ItemRef, ...]) -> str:
    rendered = ", ".join(
        f"{{ kind = {_toml_string(item.kind)}, name = {_toml_string(item.name)} }}"
        for item in items
    )
    return f"[{rendered}]"


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
