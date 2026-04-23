"""CLI command handlers for models.* operations."""

from collections.abc import Callable
from functools import partial
from typing import Any

from meridian.cli.ext_registration import register_extension_cli_group
from meridian.lib.extensions.registry import get_first_party_registry
from meridian.lib.ops.catalog import (
    ModelsListInput,
    models_list_sync,
)

Emitter = Callable[[Any], None]


def _models_list(emit: Emitter, all: bool = False, show_superseded: bool = False) -> None:
    emit(models_list_sync(ModelsListInput(all=all, show_superseded=show_superseded)))


def register_models_commands(app: Any, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "meridian.models.list": lambda: partial(_models_list, emit),
        # models.refresh is auto-generated (no required CLI args).
    }
    return register_extension_cli_group(
        app,
        registry=get_first_party_registry(),
        group="models",
        handlers=handlers,
        emit=emit,
        default_handler=partial(_models_list, emit),
    )
