"""Tests for startup-cheap Cyclopts app construction."""

from __future__ import annotations

import importlib
import sys

from cyclopts import App


def test_importing_lazy_app_builder_does_not_import_command_modules() -> None:
    sys.modules.pop("meridian.cli.startup.cyclopts_app", None)
    sys.modules.pop("meridian.cli.spawn", None)
    sys.modules.pop("meridian.cli.chat_cmd", None)

    importlib.import_module("meridian.cli.startup.cyclopts_app")

    assert "meridian.cli.spawn" not in sys.modules
    assert "meridian.cli.chat_cmd" not in sys.modules


def test_lazy_app_tree_can_be_built_from_catalog_metadata() -> None:
    from meridian.cli.startup.cyclopts_app import build_lazy_app

    app = build_lazy_app()

    assert isinstance(app, App)
    assert "spawn" in app._commands
    assert "config" in app._commands
    assert "serve" in app._commands

    spawn_app = app._commands["spawn"]
    assert isinstance(spawn_app, App)
    assert "list" in spawn_app._commands
    assert "report" in spawn_app._commands

    report_app = spawn_app._commands["report"]
    assert isinstance(report_app, App)
    assert "show" in report_app._commands
