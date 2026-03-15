"""CLI command handlers for config.* operations."""

from collections.abc import Callable
from functools import partial
from typing import Any

from cyclopts import App

from meridian.cli.registration import register_manifest_cli_group
from meridian.lib.ops.config import (
    ConfigGetInput,
    ConfigInitInput,
    ConfigResetInput,
    ConfigSetInput,
    ConfigShowInput,
    config_get_sync,
    config_init_sync,
    config_reset_sync,
    config_set_sync,
    config_show_sync,
)

Emitter = Callable[[Any], None]


def _config_init(emit: Emitter) -> None:
    emit(config_init_sync(ConfigInitInput()))


def _config_show(emit: Emitter) -> None:
    emit(config_show_sync(ConfigShowInput()))


def _config_set(emit: Emitter, key: str, value: str) -> None:
    emit(config_set_sync(ConfigSetInput(key=key, value=value)))


def _config_get(emit: Emitter, key: str) -> None:
    emit(config_get_sync(ConfigGetInput(key=key)))


def _config_reset(emit: Emitter, key: str) -> None:
    emit(config_reset_sync(ConfigResetInput(key=key)))


def register_config_commands(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "config.init": lambda: partial(_config_init, emit),
        "config.show": lambda: partial(_config_show, emit),
        "config.set": lambda: partial(_config_set, emit),
        "config.get": lambda: partial(_config_get, emit),
        "config.reset": lambda: partial(_config_reset, emit),
    }
    return register_manifest_cli_group(app, group="config", handlers=handlers)
