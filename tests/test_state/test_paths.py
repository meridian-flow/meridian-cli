from pathlib import Path

import pytest

from meridian.lib.state.paths import ensure_gitignore


def test_ensure_gitignore_tracks_project_config_and_respects_state_root_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = tmp_path / "custom-state"
    monkeypatch.setenv("MERIDIAN_STATE_ROOT", state_root.as_posix())

    gitignore_path = ensure_gitignore(repo_root)

    assert gitignore_path == state_root / ".gitignore"
    assert gitignore_path.is_file()
    assert "!config.toml" in gitignore_path.read_text(encoding="utf-8")
    assert "!models.toml" in gitignore_path.read_text(encoding="utf-8")


def test_ensure_gitignore_repairs_missing_models_toml_entry(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    state_root = repo_root / ".meridian"
    state_root.mkdir()
    gitignore_path = state_root / ".gitignore"
    gitignore_path.write_text(
        "\n".join(
            [
                "# Ignore everything by default",
                "*",
                "",
                "# Track .gitignore itself",
                "!.gitignore",
                "",
                "# Track manifest and lock (committed for reproducible installs)",
                "!agents.toml",
                "!agents.lock",
                "!config.toml",
                "",
            ]
        ),
        encoding="utf-8",
    )

    ensure_gitignore(repo_root)

    updated = gitignore_path.read_text(encoding="utf-8")
    assert "!models.toml" in updated
    assert "# Added by Meridian to keep required project state tracked" in updated
