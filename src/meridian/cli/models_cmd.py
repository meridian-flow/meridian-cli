"""CLI command handlers for models.* operations."""

from collections.abc import Callable
from functools import partial
from typing import Any

from meridian.cli.registration import register_manifest_cli_group
from meridian.lib.ops.catalog import (
    ModelsListInput,
    ModelsRefreshInput,
    models_list_sync,
    models_refresh_sync,
)

Emitter = Callable[[Any], None]


def _models_list(emit: Emitter, all: bool = False) -> None:
    emit(models_list_sync(ModelsListInput(all=all)))


def _models_refresh(emit: Emitter) -> None:
    emit(models_refresh_sync(ModelsRefreshInput()))


def register_models_commands(app: Any, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "models.list": lambda: partial(_models_list, emit),
        "models.refresh": lambda: partial(_models_refresh, emit),
    }
    return register_manifest_cli_group(
        app,
        group="models",
        handlers=handlers,
        default_handler=partial(_models_list, emit),
    )
