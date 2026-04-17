import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

cli_main = importlib.import_module("meridian.cli.main")


def test_extract_global_options_stops_parsing_after_double_dash() -> None:
    cleaned, options = cli_main._extract_global_options(
        ["codex", "--", "--harness", "claude", "exec"]
    )

    assert options.harness == "codex"
    assert cleaned == ["--", "--harness", "claude", "exec"]


def test_validate_top_level_command_rejects_unknown_without_harness() -> None:
    with pytest.raises(SystemExit):
        cli_main._validate_top_level_command(["exec"])


def test_validate_top_level_command_allows_passthrough_with_harness() -> None:
    cleaned, options = cli_main._extract_global_options(["codex", "exec"])

    assert options.harness == "codex"
    assert cleaned == ["exec"]
    cli_main._validate_top_level_command(cleaned, global_harness=options.harness)


def test_config_help_mentions_meridian_toml() -> None:
    assert "meridian.toml" in cli_main.config_app.help
    assert ".meridian/config.toml" not in cli_main.config_app.help


def test_workspace_help_mentions_local_workspace_file() -> None:
    assert "workspace.local.toml" in cli_main.workspace_app.help
    assert "workspace.toml" not in cli_main.workspace_app.help


def test_main_uses_runtime_only_bootstrap_on_startup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    calls = {"runtime_bootstrap": 0, "config_bootstrap": 0}

    settings_mod = importlib.import_module("meridian.lib.config.settings")
    config_mod = importlib.import_module("meridian.lib.ops.config")

    def _resolve_project_root(explicit: Path | None = None) -> Path:
        _ = explicit
        return repo_root

    def _runtime_bootstrap(root: Path) -> None:
        _ = root
        calls["runtime_bootstrap"] += 1

    def _config_bootstrap(root: Path) -> None:
        _ = root
        calls["config_bootstrap"] += 1

    def _create_sink(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace()

    def _flush_sink(_sink: object) -> None:
        return None

    def _app(_argv: object) -> None:
        return None

    monkeypatch.setattr(settings_mod, "resolve_project_root", _resolve_project_root)
    monkeypatch.setattr(config_mod, "ensure_runtime_state_bootstrap_sync", _runtime_bootstrap)
    monkeypatch.setattr(config_mod, "ensure_state_bootstrap_sync", _config_bootstrap)
    monkeypatch.setattr(cli_main, "create_sink", _create_sink)
    monkeypatch.setattr(cli_main, "flush_sink", _flush_sink)
    monkeypatch.setattr(cli_main, "app", _app)

    cli_main.main([])

    assert calls["runtime_bootstrap"] == 1
    assert calls["config_bootstrap"] == 0
