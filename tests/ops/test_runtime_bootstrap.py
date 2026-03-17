from pathlib import Path

from meridian.lib.ops.runtime import resolve_runtime_root_and_config


def test_resolve_runtime_root_and_config_bootstraps_project_state(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    resolved_root, _ = resolve_runtime_root_and_config(repo_root.as_posix())

    state_root = repo_root / ".meridian"
    assert resolved_root == repo_root.resolve()
    assert (state_root / "config.toml").is_file()
    assert (state_root / ".gitignore").is_file()
    assert (state_root / "artifacts").is_dir()
    assert (state_root / "work").is_dir()
    assert (state_root / "work-items").is_dir()
