"""Managed install source manifest models and TOML I/O."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from meridian.lib.install.types import (
    ItemRef,
    SourceKind,
    normalize_required_string,
    parse_item_id,
    validate_source_name,
)
from meridian.lib.state.atomic import atomic_write_text


class SourceConfig(BaseModel):
    """One declared managed source."""

    model_config = ConfigDict(frozen=True)

    name: str
    kind: SourceKind
    url: str | None = None
    path: str | None = None
    ref: str | None = None
    items: tuple[ItemRef, ...] | None = None
    agents: tuple[str, ...] | None = None
    skills: tuple[str, ...] | None = None
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

    @field_validator("agents", "skills", mode="before")
    @classmethod
    def _validate_string_lists(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> tuple[str, ...] | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            result: list[str] = []
            for item in cast("list[object] | tuple[object, ...]", value):
                if not isinstance(item, str):
                    raise ValueError(
                        f"Invalid value for '{info.field_name}': expected array of strings."
                    )
                normalized = item.strip()
                if not normalized:
                    raise ValueError(
                        f"Invalid value for '{info.field_name}': empty string in list."
                    )
                result.append(normalized)
            return tuple(result)
        raise ValueError(f"Invalid value for '{info.field_name}': expected array of strings.")

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
                raise ValueError("Invalid value for 'rename': expected string-to-string mappings.")
            key = normalize_required_string(raw_key, source="rename")
            parse_item_id(key)
            normalized[key] = normalize_required_string(raw_value, source="rename")
        return normalized

    @model_validator(mode="after")
    def _validate_kind_fields(self) -> SourceConfig:
        if self.kind == "git":
            if self.url is None or self.path is not None:
                raise ValueError("Git sources require 'url' and must not set 'path'.")
            return self

        if self.path is None or self.url is not None:
            raise ValueError("Path sources require 'path' and must not set 'url'.")
        if self.ref is not None:
            raise ValueError("Path sources must not set 'ref'.")
        return self

    @model_validator(mode="after")
    def _migrate_items_to_agents_skills(self) -> SourceConfig:
        has_new = self.agents is not None or self.skills is not None
        has_old = self.items is not None

        if has_old and has_new:
            raise ValueError(
                "Cannot specify both 'items' and 'agents'/'skills'. "
                "Use 'agents' and 'skills' instead of 'items'."
            )

        if has_old and not has_new:
            agent_names: list[str] = []
            skill_names: list[str] = []
            for item_ref in self.items or ():
                if item_ref.kind == "agent":
                    agent_names.append(item_ref.name)
                else:
                    skill_names.append(item_ref.name)
            updates: dict[str, object] = {"items": None}
            if agent_names:
                updates["agents"] = tuple(agent_names)
            if skill_names:
                updates["skills"] = tuple(skill_names)
            return self.model_copy(update=updates)

        return self

    @property
    def effective_items(self) -> tuple[ItemRef, ...] | None:
        """Return combined ItemRef tuples from agents/skills fields, or None if unfiltered."""

        if self.agents is None and self.skills is None:
            return None
        refs: list[ItemRef] = []
        for name in self.agents or ():
            refs.append(ItemRef(kind="agent", name=name))
        for name in self.skills or ():
            refs.append(ItemRef(kind="skill", name=name))
        return tuple(refs)


class SourcesConfig(BaseModel):
    """Top-level `.meridian/agents.toml` content."""

    model_config = ConfigDict(frozen=True)

    sources: tuple[SourceConfig, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_names(self) -> SourcesConfig:
        seen: set[str] = set()
        for source in self.sources:
            if source.name in seen:
                raise ValueError(f"Duplicate managed source name: '{source.name}'.")
            seen.add(source.name)
        return self


def load_sources_config(config_path: Path) -> SourcesConfig:
    """Load `.meridian/agents.toml`."""

    if not config_path.is_file():
        return SourcesConfig()

    raw_text = config_path.read_text(encoding="utf-8")
    if not raw_text.strip():
        return SourcesConfig()

    payload_obj = tomllib.loads(raw_text)
    payload = cast("dict[str, object]", payload_obj)
    raw_sources = payload.get("sources")
    if raw_sources is None:
        return SourcesConfig()
    if not isinstance(raw_sources, list):
        raise ValueError("Invalid value for 'sources': expected array of tables.")

    sources = tuple(
        SourceConfig.model_validate(cast("dict[str, object]", raw_source))
        for raw_source in cast("list[object]", raw_sources)
    )
    return SourcesConfig(sources=sources)


def write_sources_config(config_path: Path, config: SourcesConfig) -> None:
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


def _render_source_block(source: SourceConfig) -> list[str]:
    lines = ["[[sources]]"]
    lines.append(f"name = {_toml_string(source.name)}")
    lines.append(f"kind = {_toml_string(source.kind)}")
    if source.url is not None:
        lines.append(f"url = {_toml_string(source.url)}")
    if source.path is not None:
        lines.append(f"path = {_toml_string(source.path)}")
    if source.ref is not None:
        lines.append(f"ref = {_toml_string(source.ref)}")
    if source.agents is not None:
        lines.append(f"agents = {_render_string_list(source.agents)}")
    if source.skills is not None:
        lines.append(f"skills = {_render_string_list(source.skills)}")
    if source.exclude_items:
        lines.append(f"exclude_items = {_render_item_ref_list(source.exclude_items)}")
    if source.rename:
        mappings = ", ".join(
            f"{_toml_string(key)} = {_toml_string(value)}"
            for key, value in sorted(source.rename.items())
        )
        lines.append(f"rename = {{ {mappings} }}")
    return lines


def _render_string_list(names: tuple[str, ...]) -> str:
    rendered = ", ".join(_toml_string(name) for name in names)
    return f"[{rendered}]"


def _render_item_ref_list(items: tuple[ItemRef, ...]) -> str:
    rendered = ", ".join(
        f"{{ kind = {_toml_string(item.kind)}, name = {_toml_string(item.name)} }}"
        for item in items
    )
    return f"[{rendered}]"


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


# ---------------------------------------------------------------------------
# Two-file manifest (agents.toml + agents.local.toml)
# ---------------------------------------------------------------------------

ManifestFile = Literal["shared", "local"]


class SourceManifest(BaseModel):
    """Combined view of agents.toml (shared) and agents.local.toml (local).

    Local entries **override** shared entries with the same name.  This lets
    a developer customise a team-wide source (different ref, extra agents,
    local path swap) without editing the committed manifest.
    """

    model_config = ConfigDict(frozen=True)

    shared: SourcesConfig = SourcesConfig()
    local: SourcesConfig = SourcesConfig()

    @property
    def all_sources(self) -> tuple[SourceConfig, ...]:
        """Merged sources — local overrides shared on name collision."""
        local_names = {s.name for s in self.local.sources}
        merged: list[SourceConfig] = []
        for s in self.shared.sources:
            if s.name not in local_names:
                merged.append(s)
        merged.extend(self.local.sources)
        return tuple(merged)

    def find_source(self, source_name: str) -> SourceConfig | None:
        """Find a source by name.  Local takes priority over shared."""
        for s in self.local.sources:
            if s.name == source_name:
                return s
        for s in self.shared.sources:
            if s.name == source_name:
                return s
        return None

    def file_for_source(self, source_name: str) -> ManifestFile | None:
        """Return which file a source lives in, or None if not found.

        When a source appears in both files (local override), returns
        ``"local"`` because that is the effective entry.
        """
        if any(s.name == source_name for s in self.local.sources):
            return "local"
        if any(s.name == source_name for s in self.shared.sources):
            return "shared"
        return None

    def is_overridden(self, source_name: str) -> bool:
        """Return whether a shared source is overridden by a local entry."""
        has_shared = any(s.name == source_name for s in self.shared.sources)
        has_local = any(s.name == source_name for s in self.local.sources)
        return has_shared and has_local

    def with_source(
        self,
        source: SourceConfig,
        *,
        target: ManifestFile,
    ) -> SourceManifest:
        """Return a new manifest with the source added or replaced in the target file.

        When writing to local, the shared entry (if any) is left intact — the
        local entry simply overrides it at merge time.
        """
        if target == "local":
            existing = [s for s in self.local.sources if s.name != source.name]
            existing.append(source)
            return self.model_copy(update={"local": SourcesConfig(sources=tuple(existing))})
        existing = [s for s in self.shared.sources if s.name != source.name]
        existing.append(source)
        return self.model_copy(update={"shared": SourcesConfig(sources=tuple(existing))})

    def without_source(self, source_name: str) -> SourceManifest:
        """Return a new manifest with the named source removed.

        Removes from whichever file(s) contain it.  If only the local
        override is removed, the shared base becomes visible again.
        """
        return SourceManifest(
            shared=SourcesConfig(
                sources=tuple(s for s in self.shared.sources if s.name != source_name)
            ),
            local=SourcesConfig(
                sources=tuple(s for s in self.local.sources if s.name != source_name)
            ),
        )


def load_source_manifest(shared_path: Path, local_path: Path) -> SourceManifest:
    """Load both agents.toml and agents.local.toml."""
    shared = load_sources_config(shared_path)
    local = load_sources_config(local_path)
    return SourceManifest(shared=shared, local=local)


def write_source_manifest(
    shared_path: Path,
    local_path: Path,
    manifest: SourceManifest,
) -> None:
    """Write both manifest files atomically."""
    write_sources_config(shared_path, manifest.shared)
    if manifest.local.sources:
        write_sources_config(local_path, manifest.local)
    elif local_path.is_file():
        local_path.unlink()


def route_source_to_file(
    source: SourceConfig,
    *,
    force_local: bool = False,
) -> ManifestFile:
    """Determine which manifest file a new source should be written to."""
    if force_local:
        return "local"
    return "shared"
