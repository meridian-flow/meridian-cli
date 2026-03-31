from pathlib import Path

import pytest

from meridian.lib.state.work_store import (
    archive_work_item,
    create_work_item,
    get_work_item,
    rename_work_item,
    reopen_work_item,
    slugify,
)


def _state_root(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def test_slugify_normalizes_and_truncates() -> None:
    assert slugify("Hello_world  2026!!!") == "hello-world-2026"
    assert slugify("___") == ""
    assert slugify("a" * 80) == "a" * 64


def test_rename_work_item_rejects_invalid_name_collision_and_missing_source(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    create_work_item(state_root, "my feature")
    create_work_item(state_root, "beta")

    with pytest.raises(ValueError, match="Invalid work item name"):
        rename_work_item(state_root, "my-feature", "Better Name")

    with pytest.raises(ValueError, match="already exists"):
        rename_work_item(state_root, "my-feature", "beta")

    with pytest.raises(ValueError, match="not found"):
        rename_work_item(state_root, "nonexistent", "new-name")


def test_work_item_archive_and_reopen_preserves_metadata(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    item = create_work_item(state_root, "My feature")

    assert get_work_item(state_root, item.name) is not None
    assert (state_root / "work-items" / f"{item.name}.json").exists()
    active_dir = state_root / "work" / item.name
    assert not active_dir.exists()

    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "notes.md").write_text("hello", encoding="utf-8")

    archived = archive_work_item(state_root, item.name)
    archived_dir = state_root / "work-archive" / item.name
    assert archived.status == "done"
    assert not active_dir.exists()
    assert (archived_dir / "notes.md").read_text(encoding="utf-8") == "hello"

    reopened = reopen_work_item(state_root, item.name)
    assert reopened.status == "open"
    assert not archived_dir.exists()
    assert (active_dir / "notes.md").read_text(encoding="utf-8") == "hello"
