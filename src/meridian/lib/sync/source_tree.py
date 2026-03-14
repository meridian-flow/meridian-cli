"""Filesystem discovery for installable source trees."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

from meridian.lib.sync.install_types import ItemKind, ItemRef, normalize_required_string


class ExportedSourceItem(BaseModel):
    """One installable item discovered from a source tree."""

    model_config = ConfigDict(frozen=True)

    kind: ItemKind
    name: str
    path: str

    @model_validator(mode="after")
    def _validate_fields(self) -> "ExportedSourceItem":
        normalize_required_string(self.name, source="name")
        relative = Path(normalize_required_string(self.path, source="path"))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Discovered source item paths must be repo-relative.")
        return self

    @property
    def item_ref(self) -> ItemRef:
        return ItemRef(kind=self.kind, name=self.name)

    @property
    def item_id(self) -> str:
        return self.item_ref.item_id


def discover_source_items(tree_path: Path) -> tuple[ExportedSourceItem, ...]:
    """Discover installable items from conventional source layout."""

    discovered: list[ExportedSourceItem] = []
    seen: set[str] = set()

    agents_dir = tree_path / "agents"
    if agents_dir.is_dir():
        for path in sorted(agents_dir.glob("*.md")):
            item = ExportedSourceItem(
                kind="agent",
                name=path.stem,
                path=path.relative_to(tree_path).as_posix(),
            )
            if item.item_id in seen:
                raise ValueError(f"Duplicate discovered item id: '{item.item_id}'.")
            seen.add(item.item_id)
            discovered.append(item)

    skills_dir = tree_path / "skills"
    if skills_dir.is_dir():
        for path in sorted(skills_dir.glob("*/SKILL.md")):
            item = ExportedSourceItem(
                kind="skill",
                name=path.parent.name,
                path=path.relative_to(tree_path).as_posix(),
            )
            if item.item_id in seen:
                raise ValueError(f"Duplicate discovered item id: '{item.item_id}'.")
            seen.add(item.item_id)
            discovered.append(item)

    return tuple(discovered)
