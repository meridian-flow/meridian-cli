"""CLI command handlers for models.* operations."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

from meridian.lib.ops.catalog import (
    ModelsListInput,
    ModelsRefreshInput,
    ModelsShowInput,
    models_list_sync,
    models_refresh_sync,
    models_show_sync,
)
from meridian.lib.ops.manifest import get_operations_for_surface

Emitter = Callable[[Any], None]


def _models_list(emit: Emitter, all: bool = False) -> None:
    emit(models_list_sync(ModelsListInput(all=all)))


def _models_show(emit: Emitter, name: str) -> None:
    emit(models_show_sync(ModelsShowInput(model=name)))


def _models_refresh(emit: Emitter) -> None:
    emit(models_refresh_sync(ModelsRefreshInput()))


def register_models_commands(app: Any, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "models.list": lambda: partial(_models_list, emit),
        "models.refresh": lambda: partial(_models_refresh, emit),
        "models.show": lambda: partial(_models_show, emit),
    }

    registered: set[str] = set()
    descriptions: dict[str, str] = {}

    for op in get_operations_for_surface("cli"):
        if op.cli_group != "models":
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
