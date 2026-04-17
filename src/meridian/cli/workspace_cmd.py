"""CLI command handlers for workspace operations."""

from collections.abc import Callable
from typing import Any

from cyclopts import App

from meridian.cli.registration import register_manifest_cli_group

Emitter = Callable[[Any], None]


def register_workspace_commands(app: App, emit: Emitter) -> tuple[set[str], dict[str, str]]:
    # workspace.init has no required CLI args — handler is auto-generated.
    return register_manifest_cli_group(
        app,
        group="workspace",
        command_help_epilogues={
            "workspace.init": (
                "Create the local workspace topology file (workspace.local.toml).\n\n"
                "The file is local-only and scaffolded with commented examples.\n"
                "The command is idempotent and also ensures local gitignore coverage.\n\n"
                "Examples:\n\n"
                "  meridian workspace init\n"
            )
        },
        emit=emit,
    )
