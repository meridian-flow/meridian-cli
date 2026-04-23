"""CLI command handler for standalone doctor operation."""

from collections.abc import Callable
from typing import Any

from cyclopts import App

from meridian.cli.ext_registration import register_extension_cli_group
from meridian.lib.extensions.registry import get_first_party_registry

Emitter = Callable[[Any], None]


def register_doctor_command(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    # doctor has no required CLI args — handler is auto-generated.
    return register_extension_cli_group(
        app,
        registry=get_first_party_registry(),
        group="doctor",
        command_help_epilogues={
            "meridian.doctor.doctor": (
                "Health check and auto-repair for meridian state.\n\n"
                "Reconciles orphaned spawns (dead PIDs, missing spawn directories),\n"
                "cleans stale session locks, and warns about\n"
                "missing or malformed configuration.\n\n"
                "Doctor is idempotent - re-running converges on the same result.\n"
                "It is safe (and intended) to run after a crash, after a force-kill,\n"
                "or any time `meridian spawn show` reports a status that doesn't match\n"
                "reality.\n\n"
                "Examples:\n\n"
                "  meridian doctor                  # check and repair, JSON output\n\n"
                "  meridian doctor --format text    # human-readable summary\n"
            )
        },
        emit=emit,
    )
