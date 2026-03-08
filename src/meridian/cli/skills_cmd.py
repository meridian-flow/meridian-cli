"""CLI command handlers for skills.* operations."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

from meridian.lib.ops.manifest import get_operations_for_surface
from meridian.lib.ops.catalog import (
    SkillsListInput,
    SkillsLoadInput,
    SkillsSearchInput,
    skills_list_sync,
    skills_load_sync,
    skills_search_sync,
)

Emitter = Callable[[Any], None]


def _skills_list(emit: Emitter) -> None:
    emit(skills_list_sync(SkillsListInput()))


def _skills_search(emit: Emitter, query: str = "") -> None:
    emit(skills_search_sync(SkillsSearchInput(query=query)))


def _skills_show(emit: Emitter, name: str) -> None:
    emit(skills_load_sync(SkillsLoadInput(name=name)))


def register_skills_commands(app: Any, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "skills.list": lambda: partial(_skills_list, emit),
        "skills.search": lambda: partial(_skills_search, emit),
        "skills.show": lambda: partial(_skills_show, emit),
    }

    registered: set[str] = set()
    descriptions: dict[str, str] = {}

    for op in get_operations_for_surface("cli"):
        if op.cli_group != "skills":
            continue
        handler_factory = handlers.get(op.name)
        if handler_factory is None:
            raise ValueError(f"No CLI handler registered for operation '{op.name}'")
        handler = handler_factory()
        handler.__name__ = f"cmd_{op.cli_group}_{op.cli_name}"
        app.command(handler, name=op.cli_name, help=op.description)
        registered.add(f"{op.cli_group}.{op.cli_name}")
        descriptions[op.name] = op.description

    return registered, descriptions
