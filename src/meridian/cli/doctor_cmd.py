"""CLI command handler for standalone doctor operation."""

from collections.abc import Callable
from typing import Any

from cyclopts import App

from meridian.cli.registration import register_manifest_cli_group

Emitter = Callable[[Any], None]


def register_doctor_command(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    # doctor has no required CLI args — handler is auto-generated.
    return register_manifest_cli_group(app, group="doctor", emit=emit)
