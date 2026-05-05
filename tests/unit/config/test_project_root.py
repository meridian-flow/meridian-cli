import logging
from pathlib import Path

import pytest

from meridian.lib.config.project_root import resolve_user_config_path


def test_resolve_user_config_path_treats_inaccessible_implicit_default_as_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "blocked" / "config.toml"
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)
    monkeypatch.setattr(
        "meridian.lib.state.user_paths.get_user_home",
        lambda: config_path.parent,
    )

    original_is_file = Path.is_file

    def _raise_on_target(self: Path) -> bool:
        if self == config_path:
            raise PermissionError("sandbox denied")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", _raise_on_target)

    assert resolve_user_config_path(None) is None


def test_resolve_user_config_path_warns_when_nested_default_probe_is_inaccessible(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config_path = tmp_path / "blocked" / "config.toml"
    monkeypatch.setenv("MERIDIAN_DEPTH", "1")
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)
    monkeypatch.setattr(
        "meridian.lib.state.user_paths.get_user_home",
        lambda: config_path.parent,
    )

    original_is_file = Path.is_file

    def _raise_on_target(self: Path) -> bool:
        if self == config_path:
            raise PermissionError("sandbox denied")
        return original_is_file(self)

    monkeypatch.setattr(Path, "is_file", _raise_on_target)

    with caplog.at_level(logging.WARNING, logger="meridian.lib.config.project_root"):
        assert resolve_user_config_path(None) is None

    assert any(str(config_path) in record.message for record in caplog.records)


@pytest.mark.parametrize(
    ("explicit_path", "env_path"),
    [
        pytest.param(True, False, id="explicit-argument"),
        pytest.param(False, True, id="env-var"),
    ],
)
def test_resolve_user_config_path_requires_explicit_paths_to_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    explicit_path: bool,
    env_path: bool,
) -> None:
    missing_path = tmp_path / "missing.toml"
    monkeypatch.delenv("MERIDIAN_CONFIG", raising=False)
    if env_path:
        monkeypatch.setenv("MERIDIAN_CONFIG", missing_path.as_posix())

    with pytest.raises(FileNotFoundError):
        resolve_user_config_path(missing_path if explicit_path else None)
