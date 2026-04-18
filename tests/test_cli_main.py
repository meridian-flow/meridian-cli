import importlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["models"], False),
        (["spawn", "report", "show", "spawn-id"], False),
        (["spawn", "report", "search", "foo"], False),
        (["models", "list"], False),
        (["models", "show", "gpt-5.4"], False),
        (["doctor"], False),
        (["config", "show"], False),
        (["models", "refresh"], True),
        (["config", "set", "harness", "codex"], True),
    ],
)
def test_should_startup_bootstrap_command_matrix(argv: list[str], expected: bool) -> None:
    assert cli_main._should_startup_bootstrap(argv) is expected


def test_init_alias_without_link_emits_config_init_result(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_mod: Any = importlib.import_module("meridian.lib.ops.config")
    captured: dict[str, str | None] = {}
    emitted: list[object] = []
    result = object()

    def _fake_config_init_sync(payload: object) -> object:
        captured["repo_root"] = payload.repo_root  # type: ignore[attr-defined]
        return result

    def _fake_emit(payload: object) -> None:
        emitted.append(payload)

    monkeypatch.setattr(config_mod, "config_init_sync", _fake_config_init_sync)
    monkeypatch.setattr(cli_main, "emit", _fake_emit)

    cli_main.init_alias(path=tmp_path.as_posix())

    assert captured["repo_root"] == tmp_path.resolve().as_posix()
    assert emitted == [result]


def test_init_alias_link_shells_through_mars_init_with_link_when_mars_toml_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_mod: Any = importlib.import_module("meridian.lib.ops.config")
    calls: list[tuple[list[str], str | None]] = []
    emitted: list[object] = []

    def _fake_config_init(_payload: object) -> object:
        return object()

    def _fake_emit(payload: object) -> None:
        emitted.append(payload)

    monkeypatch.setattr(config_mod, "config_init_sync", _fake_config_init)
    monkeypatch.setattr(cli_main, "emit", _fake_emit)

    def _fake_run_mars(
        args: list[str] | tuple[str, ...], *, output_format: str | None = None
    ) -> None:
        calls.append((list(args), output_format))

    monkeypatch.setattr(cli_main, "_run_mars_passthrough", _fake_run_mars)

    cli_main.init_alias(path=tmp_path.as_posix(), link=".claude")

    expected_root = tmp_path.resolve().as_posix()
    assert calls == [(["--root", expected_root, "init", "--link", ".claude"], "text")]
    assert emitted == []


def test_init_alias_link_uses_mars_link_when_mars_toml_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_mod: Any = importlib.import_module("meridian.lib.ops.config")
    calls: list[tuple[list[str], str | None]] = []
    emitted: list[object] = []
    (tmp_path / "mars.toml").write_text("", encoding="utf-8")

    def _fake_config_init(_payload: object) -> object:
        return object()

    def _fake_emit(payload: object) -> None:
        emitted.append(payload)

    monkeypatch.setattr(config_mod, "config_init_sync", _fake_config_init)
    monkeypatch.setattr(cli_main, "emit", _fake_emit)

    def _fake_run_mars(
        args: list[str] | tuple[str, ...], *, output_format: str | None = None
    ) -> None:
        calls.append((list(args), output_format))

    monkeypatch.setattr(cli_main, "_run_mars_passthrough", _fake_run_mars)

    cli_main.init_alias(path=tmp_path.as_posix(), link=".claude")

    expected_root = tmp_path.resolve().as_posix()
    assert calls == [(["--root", expected_root, "link", ".claude"], "text")]
    assert emitted == []


def test_init_help_mentions_link_flag(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MERIDIAN_REPO_ROOT", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["init", "--help"])

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--link" in captured.out


def test_init_alias_json_link_emits_single_payload_for_mars_init_with_link(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_mod: Any = importlib.import_module("meridian.lib.ops.config")
    config_result = config_mod.ConfigInitOutput(
        path=(tmp_path / "meridian.toml").as_posix(),
        created=True,
    )
    emitted: list[object] = []
    executed: list[tuple[str, ...]] = []

    def _fake_config_init(_payload: object) -> object:
        return config_result

    def _fake_emit(payload: object) -> None:
        emitted.append(payload)

    def _fake_execute(
        request: Any,
    ) -> object:
        mars_args: tuple[str, ...] = request.mars_args
        executed.append(mars_args)
        return cli_main._MarsPassthroughResult(
            request=request,
            returncode=0,
            stdout_text='{"step": "bootstrap"}\n{"step": "link"}\n',
        )

    monkeypatch.setattr(config_mod, "config_init_sync", _fake_config_init)
    monkeypatch.setattr(cli_main, "emit", _fake_emit)
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(cli_main, "_execute_mars_passthrough", _fake_execute)
    monkeypatch.setattr(
        cli_main,
        "get_global_options",
        lambda: cli_main.GlobalOptions(output=cli_main.OutputConfig(format="json")),
    )

    cli_main.init_alias(path=tmp_path.as_posix(), link=".claude")

    expected_root = tmp_path.resolve().as_posix()
    assert executed == [("--json", "--root", expected_root, "init", "--link", ".claude")]
    assert emitted == [
        {
            "ok": True,
            "config": config_result.model_dump(),
            "mars": {
                "mode": "init",
                "target": ".claude",
                "exit_code": 0,
                "output": [{"step": "bootstrap"}, {"step": "link"}],
            },
        },
    ]


def test_init_alias_json_link_uses_link_subcommand_when_mars_toml_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_mod: Any = importlib.import_module("meridian.lib.ops.config")
    config_result = config_mod.ConfigInitOutput(
        path=(tmp_path / "meridian.toml").as_posix(),
        created=True,
    )
    emitted: list[object] = []
    executed: list[tuple[str, ...]] = []
    (tmp_path / "mars.toml").write_text("", encoding="utf-8")

    def _fake_config_init(_payload: object) -> object:
        return config_result

    def _fake_emit(payload: object) -> None:
        emitted.append(payload)

    def _fake_execute(request: Any) -> object:
        mars_args: tuple[str, ...] = request.mars_args
        executed.append(mars_args)
        return cli_main._MarsPassthroughResult(
            request=request,
            returncode=0,
            stdout_text='{"step": "link"}\n',
        )

    monkeypatch.setattr(config_mod, "config_init_sync", _fake_config_init)
    monkeypatch.setattr(cli_main, "emit", _fake_emit)
    monkeypatch.setattr(cli_main, "_resolve_mars_executable", lambda: "/usr/bin/mars")
    monkeypatch.setattr(cli_main, "_execute_mars_passthrough", _fake_execute)
    monkeypatch.setattr(
        cli_main,
        "get_global_options",
        lambda: cli_main.GlobalOptions(output=cli_main.OutputConfig(format="json")),
    )

    cli_main.init_alias(path=tmp_path.as_posix(), link=".claude")

    expected_root = tmp_path.resolve().as_posix()
    assert executed == [("--json", "--root", expected_root, "link", ".claude")]
    assert emitted == [
        {
            "ok": True,
            "config": config_result.model_dump(),
            "mars": {
                "mode": "link",
                "target": ".claude",
                "exit_code": 0,
                "output": {"step": "link"},
            },
        },
    ]


def test_agent_root_help_mentions_init_command() -> None:
    assert "init     Initialize repo config; optional --link wiring for tool directories" in (
        cli_main._AGENT_ROOT_HELP
    )
