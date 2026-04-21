from pathlib import Path

import pytest

from meridian.lib.launch.reference import load_reference_items


def test_load_reference_items_raises_on_unreadable_top_level_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()

    real_iterdir = Path.iterdir

    def _iterdir_with_top_level_permission_denied(path: Path):  # type: ignore[no-untyped-def]
        if path == root:
            raise PermissionError("permission denied")
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", _iterdir_with_top_level_permission_denied)

    with pytest.raises(PermissionError, match="permission denied"):
        load_reference_items([root])


def test_load_reference_items_skips_unreadable_nested_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    nested = root / "nested"
    root.mkdir()
    nested.mkdir()
    (root / "visible.txt").write_text("visible", encoding="utf-8")
    (nested / "hidden.txt").write_text("hidden", encoding="utf-8")

    real_iterdir = Path.iterdir

    def _iterdir_with_nested_permission_denied(path: Path):  # type: ignore[no-untyped-def]
        if path == nested:
            raise PermissionError("permission denied")
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", _iterdir_with_nested_permission_denied)

    loaded = load_reference_items([root])

    assert len(loaded) == 1
    assert loaded[0].kind == "directory"
    assert loaded[0].warning is None
    assert "root/" in loaded[0].body
    assert "visible.txt" in loaded[0].body
