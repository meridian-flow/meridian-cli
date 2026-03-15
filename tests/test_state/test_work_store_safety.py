from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import pytest

import meridian.lib.state.work_store as work_store
from meridian.lib.state.atomic import atomic_write_text
from meridian.lib.state.event_store import utc_now_iso
from meridian.lib.state.paths import StateRootPaths
from meridian.lib.state.work_store import WorkRenameIntent


def _state_root(tmp_path: Path) -> Path:
    state_dir = tmp_path / ".meridian"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir


def _ensure_shared_task_name(_: int, *, state_root: Path) -> str:
    return work_store.ensure_work_item_metadata(state_root, "shared-task").name


def test_ensure_work_item_metadata_holds_lock_with_concurrent_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _state_root(tmp_path)

    original_lock_file = work_store.lock_file
    lock_calls = 0
    counter_lock = threading.Lock()

    @contextmanager
    def counting_lock(lock_path: Path):
        nonlocal lock_calls
        with counter_lock:
            lock_calls += 1
        with original_lock_file(lock_path) as handle:
            yield handle

    monkeypatch.setattr(work_store, "lock_file", counting_lock)

    total = 24
    with ThreadPoolExecutor(max_workers=8) as pool:
        names = list(
            pool.map(partial(_ensure_shared_task_name, state_root=state_root), range(total))
        )

    assert len(names) == total
    assert set(names) == {"shared-task"}
    assert lock_calls == total


def test_create_work_item_rejects_existing_slug(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    work_store.create_work_item(state_root, "Shared task")

    with pytest.raises(ValueError, match="already exists"):
        work_store.create_work_item(state_root, "Shared task")


def test_rename_work_item_writes_and_cleans_intent_journal(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    paths = StateRootPaths.from_root_dir(state_root)

    item = work_store.create_work_item(state_root, "old-name")
    renamed = work_store.rename_work_item(state_root, item.name, "new-name")

    assert renamed.name == "new-name"
    assert not paths.work_items_rename_intent.exists()
    assert (paths.work_items_dir / "new-name.json").exists()
    assert not (paths.work_items_dir / "old-name.json").exists()


def test_rename_work_item_moves_archived_scratch_dir(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    paths = StateRootPaths.from_root_dir(state_root)

    item = work_store.create_work_item(state_root, "old-name")
    archived_dir = paths.work_archive_dir / item.name
    archived_dir.mkdir(parents=True, exist_ok=True)
    (archived_dir / "notes.md").write_text("archived", encoding="utf-8")

    renamed = work_store.rename_work_item(state_root, item.name, "new-name")

    assert renamed.name == "new-name"
    assert not archived_dir.exists()
    assert (paths.work_archive_dir / "new-name" / "notes.md").read_text(
        encoding="utf-8"
    ) == "archived"


def test_rename_work_item_crash_recovery_old_dir_exists_new_missing(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    paths = StateRootPaths.from_root_dir(state_root)

    old_item = work_store.create_work_item(state_root, "old-name")
    old_dir = paths.work_dir / old_item.name
    old_dir.mkdir(parents=True, exist_ok=True)
    intent = WorkRenameIntent(
        old_work_id=old_item.name,
        new_work_id="new-name",
        started_at=utc_now_iso(),
    )
    atomic_write_text(paths.work_items_rename_intent, intent.model_dump_json(indent=2) + "\n")

    work_store.reconcile_work_store(state_root)

    new_dir = paths.work_dir / "new-name"
    recovered = work_store.get_work_item(state_root, "new-name")

    assert not old_dir.exists()
    assert new_dir.exists()
    assert recovered is not None
    assert recovered.name == "new-name"
    assert (paths.work_items_dir / "new-name.json").exists()
    assert not (paths.work_items_dir / "old-name.json").exists()
    assert not paths.work_items_rename_intent.exists()


def test_rename_work_item_crash_recovery_new_dir_already_exists(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    paths = StateRootPaths.from_root_dir(state_root)

    old_item = work_store.create_work_item(state_root, "old-name")
    old_dir = paths.work_dir / old_item.name
    old_dir.mkdir(parents=True, exist_ok=True)
    new_dir = paths.work_dir / "new-name"
    new_dir.mkdir(parents=True, exist_ok=True)

    intent = WorkRenameIntent(
        old_work_id=old_item.name,
        new_work_id="new-name",
        started_at=utc_now_iso(),
    )
    atomic_write_text(paths.work_items_rename_intent, intent.model_dump_json(indent=2) + "\n")

    work_store.reconcile_work_store(state_root)

    assert not paths.work_items_rename_intent.exists()
    assert old_dir.exists()
    assert new_dir.exists()
    assert (paths.work_items_dir / "new-name.json").exists()
    assert not (paths.work_items_dir / "old-name.json").exists()


def test_rename_work_item_crash_recovery_neither_dir_exists(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    paths = StateRootPaths.from_root_dir(state_root)

    intent = WorkRenameIntent(
        old_work_id="old-missing",
        new_work_id="new-missing",
        started_at=utc_now_iso(),
    )
    atomic_write_text(paths.work_items_rename_intent, intent.model_dump_json(indent=2) + "\n")

    work_store.reconcile_work_store(state_root)

    assert not paths.work_items_rename_intent.exists()


def test_update_work_item_re_reads_after_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_root = _state_root(tmp_path)
    item = work_store.create_work_item(state_root, "my-work")

    original_get = work_store.get_work_item

    lock_held = False
    observed: list[str] = []

    @contextmanager
    def recording_lock(_lock_path: Path):
        nonlocal lock_held
        lock_held = True
        observed.append("lock-enter")
        try:
            yield object()
        finally:
            observed.append("lock-exit")
            lock_held = False

    def wrapped_get(root: Path, work_id: str):
        observed.append(f"get-lock-held={lock_held}")
        return original_get(root, work_id)

    monkeypatch.setattr(work_store, "lock_file", recording_lock)
    monkeypatch.setattr(work_store, "get_work_item", wrapped_get)

    updated = work_store.update_work_item(state_root, item.name, status="done")

    assert updated.status == "done"
    assert observed[0] == "lock-enter"
    assert "get-lock-held=True" in observed
    assert "get-lock-held=False" not in observed


def test_list_work_items_reconciles_before_listing(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    paths = StateRootPaths.from_root_dir(state_root)

    old_item = work_store.create_work_item(state_root, "old-name")
    old_dir = paths.work_dir / old_item.name
    old_dir.mkdir(parents=True, exist_ok=True)
    intent = WorkRenameIntent(
        old_work_id=old_item.name,
        new_work_id="new-name",
        started_at=utc_now_iso(),
    )
    atomic_write_text(paths.work_items_rename_intent, intent.model_dump_json(indent=2) + "\n")

    items = work_store.list_work_items(state_root)

    assert [item.name for item in items] == ["new-name"]
    assert not old_dir.exists()
    assert (paths.work_dir / "new-name").exists()
    assert (paths.work_items_dir / "new-name.json").exists()
    assert not (paths.work_items_dir / "old-name.json").exists()
    assert not paths.work_items_rename_intent.exists()


def test_update_work_item_not_found_raises_value_error(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)

    with pytest.raises(ValueError, match="not found"):
        work_store.update_work_item(state_root, "missing-work")


def test_work_rename_intent_serialization_round_trip() -> None:
    intent = WorkRenameIntent(
        old_work_id="old-work",
        new_work_id="new-work",
        started_at="2026-03-12T00:00:00Z",
    )

    encoded = intent.model_dump_json(indent=2)
    decoded = WorkRenameIntent.model_validate_json(encoded)

    assert decoded == intent


def test_reconcile_work_store_tolerates_malformed_intent_file(tmp_path: Path) -> None:
    state_root = _state_root(tmp_path)
    paths = StateRootPaths.from_root_dir(state_root)

    atomic_write_text(paths.work_items_rename_intent, "not json")

    work_store.reconcile_work_store(state_root)

    assert not paths.work_items_rename_intent.exists()


def test_get_work_item_remains_unlocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_root = _state_root(tmp_path)
    item = work_store.create_work_item(state_root, "read-only-item")

    @contextmanager
    def failing_lock(_lock_path: Path):
        raise AssertionError("get_work_item should not acquire work-items.flock")
        yield

    monkeypatch.setattr(work_store, "lock_file", failing_lock)

    loaded = work_store.get_work_item(state_root, item.name)
    assert loaded is not None
    assert loaded.name == item.name
