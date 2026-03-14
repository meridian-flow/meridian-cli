"""Interactive conflict resolution for managed install destination collisions."""

from __future__ import annotations

import sys
from pathlib import Path

from meridian.lib.install.engine import PlannedSourceItem


class ConflictResolution:
    """Result of resolving a destination collision."""

    __slots__ = ("skip", "rename_to")

    def __init__(self, *, skip: bool = False, rename_to: str | None = None) -> None:
        self.skip = skip
        self.rename_to = rename_to


def resolve_destination_conflicts(
    planned_items: list[PlannedSourceItem],
    other_destinations: dict[str, str],
    source_name: str,
    *,
    rename_overrides: dict[str, str] | None = None,
) -> tuple[list[PlannedSourceItem], dict[str, str]]:
    """Check for destination collisions and resolve interactively or via overrides.

    Returns (filtered_planned_items, new_rename_entries) where:
    - filtered_planned_items has colliding items either renamed or removed
    - new_rename_entries maps item_id → new_name for items that were renamed
    """

    rename_map = rename_overrides or {}
    resolved_items: list[PlannedSourceItem] = []
    new_renames: dict[str, str] = {}

    for planned in planned_items:
        dest_key = planned.destination_path.as_posix()
        existing = other_destinations.get(dest_key)

        if existing is None:
            other_destinations[dest_key] = planned.item_key
            resolved_items.append(planned)
            continue

        # Check if --rename was provided for this item
        override_name = rename_map.get(planned.item.name) or rename_map.get(planned.item_key)
        if override_name is not None:
            # Apply the rename
            new_renames[planned.item_key] = override_name
            repo_root = planned.destination_path.parents[2]  # .agents/agents/name.md → repo_root
            new_dest = _destination_path(repo_root, planned.item_kind, override_name)
            resolved_items.append(PlannedSourceItem(
                source_name=planned.source_name,
                item=planned.item,
                destination_name=override_name,
                destination_path=new_dest,
            ))
            other_destinations[new_dest.as_posix()] = planned.item_key
            continue

        # Interactive resolution
        if sys.stdin.isatty():
            resolution = _prompt_conflict_resolution(
                planned=planned,
                existing_item=existing,
            )
            if resolution.skip:
                continue
            if resolution.rename_to is not None:
                new_renames[planned.item_key] = resolution.rename_to
                repo_root = planned.destination_path.parents[2]
                new_dest = _destination_path(repo_root, planned.item_kind, resolution.rename_to)
                resolved_items.append(PlannedSourceItem(
                    source_name=planned.source_name,
                    item=planned.item,
                    destination_name=resolution.rename_to,
                    destination_path=new_dest,
                ))
                other_destinations[new_dest.as_posix()] = planned.item_key
                continue

        # Non-interactive or unresolved → error
        raise ValueError(
            f"Source '{source_name}' collides at {dest_key} with existing item "
            f"'{existing}'. Use --rename {planned.item.name}=NEW_NAME to resolve."
        )

    return resolved_items, new_renames


def _prompt_conflict_resolution(
    *,
    planned: PlannedSourceItem,
    existing_item: str,
) -> ConflictResolution:
    """Prompt user to resolve a destination collision."""

    print(
        f"\nConflict: {planned.item_kind} '{planned.item.name}' already exists "
        f"from '{existing_item}'."
    )
    print("  Enter a new name to rename, or press Enter to skip:")
    try:
        response = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        return ConflictResolution(skip=True)

    if not response:
        return ConflictResolution(skip=True)

    return ConflictResolution(rename_to=response)


def _destination_path(repo_root: Path, item_kind: str, destination_name: str) -> Path:
    if item_kind == "agent":
        return repo_root / ".agents" / "agents" / f"{destination_name}.md"
    return repo_root / ".agents" / "skills" / destination_name
