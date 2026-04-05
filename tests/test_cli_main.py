import importlib

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
