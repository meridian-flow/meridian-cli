from pathlib import Path

from meridian.lib.state.paths import ensure_gitignore, resolve_state_paths


def test_ensure_gitignore_drops_legacy_config_exception(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    gitignore_path = repo_root / ".meridian" / ".gitignore"
    gitignore_path.parent.mkdir(parents=True)
    gitignore_path.write_text(
        "\n".join(
            [
                "# Ignore everything by default",
                "*",
                "!.gitignore",
                "!config.toml",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    ensure_gitignore(repo_root)

    updated = gitignore_path.read_text(encoding="utf-8")
    assert "!config.toml" not in updated
    assert "!.gitignore" in updated
    assert "!fs/" in updated
    assert "!work/" in updated
    assert "!work-archive/" in updated


def test_resolve_state_paths_does_not_expose_project_config_path(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    paths = resolve_state_paths(repo_root)

    assert not hasattr(paths, "config_path")
