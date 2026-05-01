import importlib
from pathlib import Path
from typing import Any

import pytest

from meridian.cli.app_tree import AGENT_ROOT_HELP

cli_main = importlib.import_module("meridian.cli.main")
mars_passthrough = importlib.import_module("meridian.cli.mars_passthrough")
primary_launch = importlib.import_module("meridian.cli.primary_launch")
config_ops = importlib.import_module("meridian.lib.ops.config")


def test_main_rejects_unknown_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["exec"])

    assert exc_info.value.code == 1
    assert "Unknown command: exec" in capsys.readouterr().err


def test_main_harness_shortcut_routes_into_primary_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    captured: dict[str, object] = {}

    def _fake_primary_launch(**kwargs: object) -> object:
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(primary_launch, "run_primary_launch", _fake_primary_launch)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["codex", "--dry-run"])

    assert exc_info.value.code == 0
    assert captured["harness"] == "codex"
    assert captured["dry_run"] is True


def test_config_help_mentions_meridian_toml() -> None:
    assert "meridian.toml" in cli_main.config_app.help
    assert ".meridian/config.toml" not in cli_main.config_app.help


def test_workspace_help_mentions_workspace_local_toml() -> None:
    assert "workspace.local.toml" in cli_main.workspace_app.help
    assert "workspace.toml" not in cli_main.workspace_app.help


def test_init_help_mentions_link_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["init", "--help"])

    assert exc_info.value.code == 0
    assert "--link" in capsys.readouterr().out


def test_init_alias_link_uses_mars_init_when_mars_toml_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured_project_root: dict[str, str] = {}
    captured_mars: list[tuple[tuple[str, ...], str | None]] = []

    def _fake_config_init(payload: Any) -> object:
        captured_project_root["value"] = payload.project_root
        return object()

    def _fake_run_mars_passthrough(
        args: list[str] | tuple[str, ...],
        *,
        output_format: str | None = None,
        **_kwargs: object,
    ) -> None:
        captured_mars.append((tuple(args), output_format))

    monkeypatch.setattr(config_ops, "config_init_sync", _fake_config_init)
    monkeypatch.setattr(mars_passthrough, "run_mars_passthrough", _fake_run_mars_passthrough)

    cli_main.init_alias(path=tmp_path.as_posix(), link=".claude")

    expected_root = tmp_path.resolve().as_posix()
    assert captured_project_root["value"] == expected_root
    assert captured_mars == [
        (("--root", expected_root, "init", "--link", ".claude"), "text"),
    ]


def test_init_alias_link_uses_mars_link_when_mars_toml_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    captured_mars: list[tuple[tuple[str, ...], str | None]] = []
    (tmp_path / "mars.toml").write_text("", encoding="utf-8")

    monkeypatch.setattr(config_ops, "config_init_sync", lambda _payload: object())

    def _fake_run_mars_passthrough(
        args: list[str] | tuple[str, ...],
        *,
        output_format: str | None = None,
        **_kwargs: object,
    ) -> None:
        captured_mars.append((tuple(args), output_format))

    monkeypatch.setattr(mars_passthrough, "run_mars_passthrough", _fake_run_mars_passthrough)

    cli_main.init_alias(path=tmp_path.as_posix(), link=".claude")

    expected_root = tmp_path.resolve().as_posix()
    assert captured_mars == [
        (("--root", expected_root, "link", ".claude"), "text"),
    ]


def test_agent_root_help_restricted_surface_contract() -> None:
    for visible in (
        "Meridian is a coordination layer",
        "For automation, use --format json",
        "spawn    Create and manage subagent runs",
        "work     Work item dashboard and coordination",
        "config   Show resolved configuration and sources",
        "doctor   Health check and orphan reconciliation",
        "mars     Package management and agent materialization",
    ):
        assert visible in AGENT_ROOT_HELP

    normalized_help = AGENT_ROOT_HELP.lower()
    for hidden in (
        "init",
        "completion",
        "serve",
        "claude",
        "codex",
        "opencode",
    ):
        assert hidden not in normalized_help


def test_main_prints_cached_doctor_warning_for_text_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("MERIDIAN_DEPTH", raising=False)
    monkeypatch.setattr(cli_main, "maybe_bootstrap_runtime_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli_main,
        "consume_doctor_cache_warning",
        lambda: "meridian doctor: 1 other warning.",
    )
    monkeypatch.setattr(cli_main, "maybe_start_background_doctor_scan", lambda: False)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["doctor", "--help"])

    assert exc_info.value.code == 0
    assert "meridian doctor: 1 other warning." in capsys.readouterr().err


def test_main_suppresses_cached_doctor_warning_for_json_command(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("MERIDIAN_DEPTH", raising=False)
    monkeypatch.setattr(cli_main, "maybe_bootstrap_runtime_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        cli_main,
        "consume_doctor_cache_warning",
        lambda: "meridian doctor: 1 other warning.",
    )
    monkeypatch.setattr(cli_main, "maybe_start_background_doctor_scan", lambda: False)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["--format", "json", "doctor", "--help"])

    assert exc_info.value.code == 0
    assert "meridian doctor:" not in capsys.readouterr().err


def test_main_starts_background_doctor_scan_only_for_app_launch_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MERIDIAN_DEPTH", raising=False)
    monkeypatch.setattr(cli_main, "maybe_bootstrap_runtime_state", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli_main, "consume_doctor_cache_warning", lambda: None)
    starts: list[str] = []
    monkeypatch.setattr(
        cli_main,
        "maybe_start_background_doctor_scan",
        lambda: starts.append("started") or True,
    )

    cli_main._GLOBAL_OPTIONS.set(None)
    with pytest.raises(SystemExit) as dry_run_exit:
        cli_main.main(["--dry-run"])
    assert dry_run_exit.value.code == 0
    cli_main._GLOBAL_OPTIONS.set(None)
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["doctor", "--help"])
    cli_main._GLOBAL_OPTIONS.set(None)
    with pytest.raises(SystemExit) as help_exit:
        cli_main.main(["--help"])

    assert exc_info.value.code == 0
    assert help_exit.value.code == 0
    assert starts == ["started"]
