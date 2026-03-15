"""Intra-source skill dependency resolution for managed installs."""

from __future__ import annotations

import logging
from pathlib import Path

from meridian.lib.install.discovery import DiscoveredItem

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


def resolve_skill_deps(
    tree_path: Path,
    agent_names: set[str],
    discovered_items: tuple[DiscoveredItem, ...],
) -> set[str]:
    """Resolve skill dependencies for the given agents within one source tree.

    Reads each agent's markdown frontmatter to extract ``skills: [...]`` and
    returns skill names that exist in the same source.  Warns (but does not
    fail) when a dependency is not found in the source.
    """

    available_skills = {item.name for item in discovered_items if item.kind == "skill"}
    resolved: set[str] = set()

    for agent_name in sorted(agent_names):
        agent_item = next(
            (item for item in discovered_items if item.kind == "agent" and item.name == agent_name),
            None,
        )
        if agent_item is None:
            continue

        agent_path = tree_path / agent_item.path
        skill_refs = _extract_skill_refs(agent_path)
        for skill_name in skill_refs:
            if skill_name in available_skills:
                resolved.add(skill_name)
            else:
                logger.warning(
                    "Agent '%s' declares skill dependency '%s' which is not available "
                    "in the same source tree.",
                    agent_name,
                    skill_name,
                )

    return resolved


def _extract_skill_refs(agent_path: Path) -> list[str]:
    """Extract skill names from an agent profile's YAML frontmatter."""

    try:
        content = agent_path.read_text(encoding="utf-8")
    except OSError:
        return []

    from meridian.lib.catalog.skill import split_markdown_frontmatter

    frontmatter, _ = split_markdown_frontmatter(content)
    skills_value = frontmatter.get("skills")
    if skills_value is None:
        return []
    if isinstance(skills_value, list):
        from typing import cast

        return [
            str(item).strip() for item in cast("list[object]", skills_value) if str(item).strip()
        ]
    if isinstance(skills_value, str):
        stripped = skills_value.strip()
        return [stripped] if stripped else []
    return []
