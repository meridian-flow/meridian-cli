"""CLI command handlers for models.* operations."""

from collections.abc import Callable
from functools import partial
from typing import Any

from meridian.cli.registration import register_manifest_cli_group
from meridian.lib.ops.catalog import (
    ModelsListInput,
    models_list_sync,
)

Emitter = Callable[[Any], None]


def _models_list(emit: Emitter, all: bool = False, show_superseded: bool = False) -> None:
    emit(models_list_sync(ModelsListInput(all=all, show_superseded=show_superseded)))


def register_models_commands(app: Any, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "models.list": lambda: partial(_models_list, emit),
        # models.refresh is auto-generated (no required CLI args).
    }
    return register_manifest_cli_group(
        app,
        group="models",
        handlers=handlers,
        emit=emit,
        default_handler=partial(_models_list, emit),
    )
