"""Unit tests for context-backend auto-migration helpers."""

from pathlib import Path

from meridian.lib.context.migration import auto_migrate_contexts


def test_auto_migrate_moves_fs_to_kb_when_kb_missing(tmp_path: Path) -> None:
    runtime_root = tmp_path / ".meridian"
    fs_dir = runtime_root / "fs"
    fs_dir.mkdir(parents=True)
    (fs_dir / "note.txt").write_text("legacy", encoding="utf-8")

    auto_migrate_contexts(runtime_root)

    assert not fs_dir.exists()
    assert (runtime_root / "kb").is_dir()
    assert (runtime_root / "kb" / "note.txt").read_text(encoding="utf-8") == "legacy"


def test_auto_migrate_moves_work_archive_to_archive_work(tmp_path: Path) -> None:
    runtime_root = tmp_path / ".meridian"
    old_archive = runtime_root / "work-archive"
    old_archive.mkdir(parents=True)
    (old_archive / "item.md").write_text("done", encoding="utf-8")

    auto_migrate_contexts(runtime_root)

    assert not old_archive.exists()
    new_archive = runtime_root / "archive" / "work"
    assert new_archive.is_dir()
    assert (new_archive / "item.md").read_text(encoding="utf-8") == "done"


def test_auto_migrate_does_not_overwrite_existing_targets(tmp_path: Path) -> None:
    runtime_root = tmp_path / ".meridian"
    fs_dir = runtime_root / "fs"
    kb_dir = runtime_root / "kb"
    old_archive = runtime_root / "work-archive"
    new_archive = runtime_root / "archive" / "work"

    fs_dir.mkdir(parents=True)
    kb_dir.mkdir(parents=True)
    old_archive.mkdir(parents=True)
    new_archive.mkdir(parents=True)
    (fs_dir / "legacy.txt").write_text("legacy", encoding="utf-8")
    (kb_dir / "current.txt").write_text("current", encoding="utf-8")
    (old_archive / "legacy-archive.txt").write_text("legacy", encoding="utf-8")
    (new_archive / "current-archive.txt").write_text("current", encoding="utf-8")

    auto_migrate_contexts(runtime_root)
    auto_migrate_contexts(runtime_root)

    assert (fs_dir / "legacy.txt").read_text(encoding="utf-8") == "legacy"
    assert (kb_dir / "current.txt").read_text(encoding="utf-8") == "current"
    assert (old_archive / "legacy-archive.txt").read_text(encoding="utf-8") == "legacy"
    assert (new_archive / "current-archive.txt").read_text(encoding="utf-8") == "current"
