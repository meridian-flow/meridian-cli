"""CLI command handler for standalone doctor operation."""

from collections.abc import Callable
from functools import partial
from typing import Any

from cyclopts import App

from meridian.cli.registration import register_manifest_cli_group
from meridian.lib.ops.diag import DoctorInput, doctor_sync

Emitter = Callable[[Any], None]


def _doctor(emit: Emitter) -> None:
    emit(doctor_sync(DoctorInput()))


def register_doctor_command(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    handlers: dict[str, Callable[[], Callable[..., None]]] = {
        "doctor": lambda: partial(_doctor, emit),
    }
    return register_manifest_cli_group(app, group="doctor", handlers=handlers)
