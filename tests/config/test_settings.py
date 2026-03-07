from __future__ import annotations

from pathlib import Path

import pytest

from meridian.lib.config.settings import SearchPathConfig, load_config


def _write_project_config(repo_root: Path, content: str) -> None:
    config_path = repo_root / ".meridian" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content, encoding="utf-8")


def _write_user_config(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_user_aliases(repo_root: Path, content: str) -> None:
    models_path = repo_root / ".meridian" / "models.toml"
    models_path.parent.mkdir(parents=True, exist_ok=True)
    models_path.write_text(content, encoding="utf-8")


def test_load_config_defaults_when_project_config_is_missing(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    loaded = load_config(repo_root)

    assert loaded.max_depth == 3
    assert loaded.max_retries == 3
    assert loaded.default_permission_tier == "read-only"
    assert loaded.default_primary_agent == "primary"
    assert loaded.default_agent == "agent"
    assert loaded.default_model == "gpt-5.3-codex"
    assert loaded.search_paths == SearchPathConfig()


def test_load_config_layers_project_user_and_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _write_project_config(
        repo_root,
        "[defaults]\n"
        "max_depth = 2\n"
        "max_retries = 6\n"
        "\n"
        "[output]\n"
        "show = ['lifecycle', 'error']\n",
    )
    user_config = tmp_path / "user.toml"
    _write_user_config(
        user_config,
        "[defaults]\n"
        "agent = 'overlay-agent'\n"
        "\n"
        "[output]\n"
        "verbosity = 'debug'\n",
    )
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "11")

    loaded = load_config(repo_root, user_config=user_config)

    assert loaded.max_depth == 11
    assert loaded.max_retries == 6
    assert loaded.default_agent == "overlay-agent"
    assert loaded.output.show == ("lifecycle", "error")
    assert loaded.output.verbosity == "debug"


def test_load_config_user_config_param_beats_meridian_config_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _write_project_config(repo_root, "[defaults]\nmax_depth = 2\n")
    env_config = tmp_path / "env.toml"
    _write_user_config(env_config, "[defaults]\nmax_depth = 11\n")
    user_config = tmp_path / "user.toml"
    _write_user_config(user_config, "[defaults]\nmax_depth = 8\n")
    monkeypatch.setenv("MERIDIAN_CONFIG", env_config.as_posix())

    loaded = load_config(repo_root, user_config=user_config)

    assert loaded.max_depth == 8


def test_load_config_uses_meridian_config_env_when_no_param_is_given(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _write_project_config(repo_root, "[defaults]\nmax_retries = 2\n")
    user_config = tmp_path / "user.toml"
    _write_user_config(user_config, "[defaults]\nmax_retries = 9\n")
    monkeypatch.setenv("MERIDIAN_CONFIG", user_config.as_posix())

    loaded = load_config(repo_root)

    assert loaded.max_retries == 9


def test_load_config_normalizes_default_and_harness_model_aliases(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_user_aliases(
        repo_root,
        "[aliases]\n"
        "fast = 'gpt-5.3-codex'\n"
        "smart = 'claude-sonnet-4-6'\n",
    )
    _write_project_config(
        repo_root,
        "[defaults]\n"
        "default_model = 'fast'\n"
        "\n"
        "[harness]\n"
        "claude = 'smart'\n",
    )

    loaded = load_config(repo_root)

    assert loaded.default_model == "gpt-5.3-codex"
    assert loaded.harness.claude == "claude-sonnet-4-6"


def test_load_config_rejects_missing_user_config_file(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_project_config(repo_root, "")

    with pytest.raises(FileNotFoundError, match="User Meridian config file not found"):
        load_config(repo_root, user_config=tmp_path / "does-not-exist.toml")


def test_load_config_rejects_invalid_scalar_types(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _write_project_config(repo_root, "[defaults]\nmax_depth = 'three'\n")

    with pytest.raises(ValueError, match=r"defaults\.max_depth.*expected int"):
        load_config(repo_root)

    _write_project_config(repo_root, "")
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "three")

    with pytest.raises(ValueError, match=r"MERIDIAN_MAX_DEPTH.*expected int"):
        load_config(repo_root)


def test_load_config_rejects_invalid_primary_values(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_project_config(repo_root, "[primary]\npermission_tier = 'danger'\n")

    with pytest.raises(ValueError, match="Unsupported permission tier 'danger'"):
        load_config(repo_root)

    _write_project_config(repo_root, "[primary]\nautocompact_pct = 0\n")

    with pytest.raises(ValueError, match=r"primary\.autocompact_pct.*between 1 and 100"):
        load_config(repo_root)
