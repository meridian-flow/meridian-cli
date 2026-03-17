from pathlib import Path

from meridian.cli.main import main


def test_main_help_bootstraps_project_state(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.chdir(repo_root)
    monkeypatch.delenv("MERIDIAN_REPO_ROOT", raising=False)
    monkeypatch.delenv("MERIDIAN_STATE_ROOT", raising=False)
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)

    try:
        main(["--help"])
    except SystemExit as exc:  # pragma: no cover - cyclopts may exit after help
        assert exc.code in (0, None)

    state_root = repo_root / ".meridian"
    assert (state_root / "config.toml").is_file()
    assert "!config.toml" in (state_root / ".gitignore").read_text(encoding="utf-8")
    assert "Multi-agent orchestration" in capsys.readouterr().out
