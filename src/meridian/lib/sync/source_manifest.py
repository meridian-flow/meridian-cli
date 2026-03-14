"""Exported-source manifest parsing for installable agent trees."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator, model_validator

from meridian.lib.sync.install_types import ItemKind, ItemRef, normalize_required_string


class ExportedSourceItem(BaseModel):
    """One exported item from `meridian-source.toml`."""

    model_config = ConfigDict(frozen=True)

    kind: ItemKind
    name: str
    path: str
    managed: bool = False
    system: bool = False
    depends_on: tuple[ItemRef, ...] = ()
    bundle_requires: tuple[ItemRef, ...] = ()

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        normalized = normalize_required_string(value, source="kind")
        if normalized not in {"agent", "skill"}:
            raise ValueError("Invalid value for 'kind': expected 'agent' or 'skill'.")
        return normalized

    @field_validator("name", "path")
    @classmethod
    def _validate_required_strings(
        cls,
        value: str,
        info: ValidationInfo,
    ) -> str:
        field_name = info.field_name
        if field_name is None:
            raise ValueError("Exported source validator missing field name.")
        return normalize_required_string(value, source=field_name)

    @field_validator("depends_on", "bundle_requires", mode="before")
    @classmethod
    def _validate_item_refs(cls, value: object) -> tuple[ItemRef, ...]:
        if value is None:
            return ()
        if not isinstance(value, list | tuple):
            raise ValueError("Invalid dependency list: expected array of tables.")

        refs: list[ItemRef] = []
        for raw_item in cast("list[object] | tuple[object, ...]", value):
            if not isinstance(raw_item, dict):
                raise ValueError("Invalid dependency list: expected array of tables.")
            refs.append(ItemRef.model_validate(cast("dict[str, object]", raw_item)))
        return tuple(refs)

    @model_validator(mode="after")
    def _validate_path_layout(self) -> "ExportedSourceItem":
        relative = Path(self.path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid value for 'path': expected repo-relative exported path.")

        if self.kind == "agent":
            if not self.path.startswith("agents/") or relative.suffix != ".md":
                raise ValueError(
                    "Agent item paths must live under 'agents/' and end with '.md'."
                )
        else:
            if not self.path.startswith("skills/") or relative.name != "SKILL.md":
                raise ValueError(
                    "Skill item paths must live under 'skills/' and point to 'SKILL.md'."
                )
        return self

    @property
    def item_ref(self) -> ItemRef:
        """Return this item as a canonical reference."""

        return ItemRef(kind=self.kind, name=self.name)

    @property
    def item_id(self) -> str:
        """Return this item's canonical id."""

        return self.item_ref.item_id


class ExportedSourceManifest(BaseModel):
    """Parsed `meridian-source.toml`."""

    model_config = ConfigDict(frozen=True)

    items: tuple[ExportedSourceItem, ...] = ()

    @model_validator(mode="after")
    def _validate_unique_item_ids(self) -> "ExportedSourceManifest":
        seen: set[str] = set()
        for item in self.items:
            if item.item_id in seen:
                raise ValueError(f"Duplicate exported item id: '{item.item_id}'.")
            seen.add(item.item_id)
        return self

    def items_by_id(self) -> dict[str, ExportedSourceItem]:
        """Return exported items keyed by canonical item id."""

        return {item.item_id: item for item in self.items}


def load_source_manifest(tree_path: Path) -> ExportedSourceManifest:
    """Load one exported-source manifest from a source tree."""

    manifest_path = tree_path / "meridian-source.toml"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Source manifest not found: {manifest_path}")

    payload_obj = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    payload = cast("dict[str, object]", payload_obj)
    raw_items = payload.get("items")
    if raw_items is None:
        return ExportedSourceManifest()
    if not isinstance(raw_items, list):
        raise ValueError("Invalid value for 'items': expected array of tables.")

    items = tuple(
        ExportedSourceItem.model_validate(cast("dict[str, object]", raw_item))
        for raw_item in cast("list[object]", raw_items)
    )
    manifest = ExportedSourceManifest(items=items)

    for item in manifest.items:
        target = tree_path / item.path
        if not target.is_file():
            raise FileNotFoundError(f"Exported item path not found: {target}")

    return manifest
