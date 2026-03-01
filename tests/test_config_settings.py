"""Slice 1 config-settings tests."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

import pytest

from meridian.lib.config.settings import MeridianConfig, PrimaryConfig, load_config


def _install_config(repo_root: Path, content: str) -> None:
    config_path = repo_root / ".meridian" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content, encoding="utf-8")


def test_load_config_from_fixture_toml(package_root: Path, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    fixture_path = package_root / "tests" / "fixtures" / "config" / "settings.toml"
    config_path = repo_root / ".meridian" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture_path, config_path)

    loaded = load_config(repo_root)

    assert loaded == MeridianConfig(
        max_depth=7,
        max_retries=4,
        retry_backoff_seconds=0.5,
        kill_grace_seconds=1.5,
        guardrail_timeout_seconds=45.0,
        wait_timeout_seconds=900.0,
        default_permission_tier="workspace-write",
        default_primary_agent="lead-primary",
        default_agent="worker-agent",
        primary=PrimaryConfig(
            autocompact_pct=61,
            permission_tier="workspace-write",
        ),
    )


def test_load_config_missing_file_returns_defaults(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True, exist_ok=True)

    loaded = load_config(repo_root)

    assert loaded == MeridianConfig()


def test_load_config_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _install_config(
        repo_root,
        (
            "[defaults]\n"
            "max_depth = 2\n"
            "max_retries = 3\n"
            "\n"
            "[permissions]\n"
            "default_tier = 'read-only'\n"
        ),
    )
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "9")
    monkeypatch.setenv("MERIDIAN_DEFAULT_AGENT", "env-agent")

    loaded = load_config(repo_root)

    assert loaded.max_depth == 9
    assert loaded.default_agent == "env-agent"
    assert loaded.max_retries == 3


def test_load_config_accepts_legacy_primary_agent_key(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _install_config(
        repo_root,
        "[defaults]\n"
        "primary_agent = 'legacy-primary'\n",
    )

    loaded = load_config(repo_root)

    assert loaded.default_primary_agent == "legacy-primary"
    assert loaded.primary_agent == "legacy-primary"


def test_load_config_legacy_primary_agent_env_alias(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _install_config(
        repo_root,
        "[defaults]\n"
        "default_primary_agent = 'from-file'\n",
    )
    monkeypatch.setenv("MERIDIAN_PRIMARY_AGENT", "legacy-env")

    loaded = load_config(repo_root)

    assert loaded.default_primary_agent == "legacy-env"


def test_load_config_warns_on_unknown_keys(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _install_config(
        repo_root,
        (
            "[defaults]\n"
            "max_depth = 5\n"
            "unknown_default = 1\n"
            "\n"
            "[mystery]\n"
            "value = 123\n"
        ),
    )
    caplog.set_level(logging.WARNING, logger="meridian.lib.config.settings")

    loaded = load_config(repo_root)

    assert loaded.max_depth == 5
    messages = [record.getMessage() for record in caplog.records]
    assert any("defaults.unknown_default" in message for message in messages)
    assert any("mystery" in message for message in messages)


def test_load_config_rejects_danger_default_tier(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _install_config(
        repo_root,
        "[permissions]\n"
        "default_tier = 'danger'\n",
    )

    with pytest.raises(ValueError, match="default_permission_tier"):
        load_config(repo_root)


def test_load_config_rejects_danger_primary_permission_tier(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _install_config(
        repo_root,
        "[primary]\n"
        "permission_tier = 'danger'\n",
    )

    with pytest.raises(ValueError, match=r"primary\.permission_tier"):
        load_config(repo_root)


def test_load_config_rejects_type_errors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    _install_config(
        repo_root,
        "[defaults]\n"
        "max_depth = 'three'\n",
    )
    with pytest.raises(ValueError, match=r"defaults\.max_depth.*expected int"):
        load_config(repo_root)

    _install_config(repo_root, "")
    monkeypatch.setenv("MERIDIAN_MAX_DEPTH", "three")
    with pytest.raises(ValueError, match=r"MERIDIAN_MAX_DEPTH.*expected int"):
        load_config(repo_root)


def test_load_config_rejects_primary_section_type_errors(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _install_config(
        repo_root,
        "[primary]\n"
        "autocompact_pct = 'sixty-five'\n",
    )
    with pytest.raises(ValueError, match=r"primary\.autocompact_pct.*expected int"):
        load_config(repo_root)

    _install_config(
        repo_root,
        "[primary]\n"
        "permission_tier = 1\n",
    )
    with pytest.raises(ValueError, match=r"primary\.permission_tier.*expected str"):
        load_config(repo_root)


@pytest.mark.parametrize("value", (-1, 0, 101))
def test_load_config_rejects_primary_autocompact_out_of_range(
    tmp_path: Path,
    value: int,
) -> None:
    repo_root = tmp_path / "repo"
    _install_config(
        repo_root,
        "[primary]\n"
        f"autocompact_pct = {value}\n",
    )

    with pytest.raises(ValueError, match=r"primary\.autocompact_pct.*between 1 and 100"):
        load_config(repo_root)
