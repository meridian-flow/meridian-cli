from pathlib import Path

import pytest

from meridian.lib.state.work_store import (
    create_work_item,
    rename_work_item,
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
