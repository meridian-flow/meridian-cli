from pathlib import Path

from meridian.lib.state.paths import ensure_gitignore


def test_ensure_gitignore_tracks_project_config_and_respects_state_root_override(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = tmp_path / "custom-state"
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", state_root.as_posix())

    gitignore_path = ensure_gitignore(repo_root)

    assert gitignore_path == state_root / ".gitignore"
    assert gitignore_path.is_file()
    assert "!config.toml" in gitignore_path.read_text(encoding="utf-8")
