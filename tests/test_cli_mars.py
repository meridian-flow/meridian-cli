import importlib
from pathlib import Path

import pytest

cli_main = importlib.import_module("meridian.cli.main")


def test_resolve_mars_executable_prefers_current_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scripts_dir = tmp_path / "bin"
    scripts_dir.mkdir()
    (scripts_dir / "mars").write_text("", encoding="utf-8")
    monkeypatch.setattr(cli_main.sys, "executable", str(scripts_dir / "python"))
    monkeypatch.setattr(cli_main.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/mars")

    resolved = cli_main._resolve_mars_executable()

    assert resolved == str(scripts_dir / "mars")


def test_resolve_mars_executable_falls_back_to_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    scripts_dir = tmp_path / "bin"
    scripts_dir.mkdir()
    monkeypatch.setattr(cli_main.sys, "executable", str(scripts_dir / "python"))
    monkeypatch.setattr(cli_main.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/mars")

    resolved = cli_main._resolve_mars_executable()

    assert resolved == "/usr/bin/mars"


def test_resolve_mars_executable_uses_symlink_parent_not_resolved_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tool_bin = tmp_path / "tool-bin"
    real_bin = tmp_path / "real-bin"
    tool_bin.mkdir()
    real_bin.mkdir()
    (tool_bin / "mars").write_text("", encoding="utf-8")
    (tool_bin / "python3").symlink_to(real_bin / "python3")

    monkeypatch.setattr(cli_main.sys, "executable", str(tool_bin / "python3"))
    monkeypatch.setattr(cli_main.shutil, "which", lambda *_args, **_kwargs: "/usr/bin/mars")

    resolved = cli_main._resolve_mars_executable()

    assert resolved == str(tool_bin / "mars")
