from pathlib import Path

import pytest

from meridian.lib.state.paths import resolve_work_dir
from meridian.lib.state.work_store import (
    create_auto_work_item,
    create_work_item,
    get_work_item,
    list_work_items,
    rename_work_item,
    slugify,
    update_work_item,
)


def _state_root(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def test_slugify_normalizes_and_truncates() -> None:
    assert slugify("Hello_world  2026!!!") == "hello-world-2026"
    assert slugify("___") == ""
    assert slugify("a" * 80) == "a" * 64


def test_create_list_and_update_work_items(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    first = create_work_item(state_root, "Hello world", "first item")
    second = create_work_item(state_root, "Hello_world", "second item")

    assert first.name == "hello-world"
    assert second.name == "hello-world-2"
    assert resolve_work_dir(tmp_path) == state_root / "work"

    stored = get_work_item(state_root, first.name)
    assert stored is not None
    assert stored.description == "first item"
    assert stored.status == "open"

    updated = update_work_item(
        state_root,
        first.name,
        status="done",
        description="finished item",
    )
    assert updated.status == "done"
    assert updated.description == "finished item"

    items = list_work_items(state_root)
    assert [item.name for item in items] == [first.name, second.name]

    with pytest.raises(ValueError, match="not found"):
        update_work_item(state_root, "missing")


def test_rename_work_item_moves_directory(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    item = create_work_item(state_root, "Old name", "some desc")
    assert item.name == "old-name"

    renamed = rename_work_item(state_root, "old-name", "new-name")
    assert renamed.name == "new-name"
    assert renamed.description == "some desc"

    # Old directory gone, new directory exists
    assert not (state_root / "work" / "old-name").exists()
    assert (state_root / "work" / "new-name" / "work.json").is_file()

    # Lookup by new name works, old name returns None
    assert get_work_item(state_root, "new-name") is not None
    assert get_work_item(state_root, "old-name") is None


def test_rename_work_item_self_rename_is_noop(tmp_path: Path) -> None:
    """Renaming to the same slug returns the original item unchanged."""
    state_root = _state_root(tmp_path)

    item = create_work_item(state_root, "my feature")
    assert item.name == "my-feature"

    renamed = rename_work_item(state_root, "my-feature", "my-feature")
    assert renamed.name == "my-feature"
    assert (state_root / "work" / "my-feature" / "work.json").is_file()


def test_rename_work_item_rejects_spaces(tmp_path: Path) -> None:
    """Rename requires a valid slug, not a label with spaces."""
    state_root = _state_root(tmp_path)

    create_work_item(state_root, "my feature")

    with pytest.raises(ValueError, match="Invalid work item name"):
        rename_work_item(state_root, "my-feature", "Better Name")


def test_rename_work_item_rejects_collision(tmp_path: Path) -> None:
    """Rename errors if the target name already exists."""
    state_root = _state_root(tmp_path)

    create_work_item(state_root, "alpha")
    create_work_item(state_root, "beta")

    with pytest.raises(ValueError, match="already exists"):
        rename_work_item(state_root, "alpha", "beta")


def test_rename_work_item_missing_raises_value_error(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    with pytest.raises(ValueError, match="not found"):
        rename_work_item(state_root, "nonexistent", "new-name")


def test_create_auto_work_item_sets_auto_generated_flag(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    item = create_auto_work_item(state_root)
    assert item.auto_generated is True
    assert item.name != ""
    assert item.status == "open"
    assert item.description == ""

    # work.json should exist on disk
    assert (state_root / "work" / item.name / "work.json").is_file()

    # Read back and verify
    stored = get_work_item(state_root, item.name)
    assert stored is not None
    assert stored.auto_generated is True


def test_update_work_item_clears_auto_generated(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    item = create_auto_work_item(state_root)
    assert item.auto_generated is True

    updated = update_work_item(state_root, item.name, auto_generated=False)
    assert updated.auto_generated is False

    # Verify persisted
    stored = get_work_item(state_root, item.name)
    assert stored is not None
    assert stored.auto_generated is False


def test_auto_generated_defaults_to_false_for_existing_items(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    item = create_work_item(state_root, "Normal item")
    assert item.auto_generated is False
