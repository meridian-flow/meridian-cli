from pathlib import Path

import pytest

from meridian.lib.state.paths import resolve_work_dir
from meridian.lib.state.work_store import (
    create_work_item,
    get_work_item,
    list_work_items,
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

    with pytest.raises(KeyError):
        update_work_item(state_root, "missing")
