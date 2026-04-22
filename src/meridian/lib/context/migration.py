"""Auto-migration for context backend paths."""

from pathlib import Path


def auto_migrate_contexts(runtime_root: Path) -> None:
    """Migrate old paths to the context-backend directory shape.

    Performs idempotent startup migration before context resolution:
    - ``.meridian/fs`` -> ``.meridian/kb``
    - ``.meridian/work-archive`` -> ``.meridian/archive/work``
    """

    fs_path = runtime_root / "fs"
    kb_path = runtime_root / "kb"
    if fs_path.exists() and not kb_path.exists():
        fs_path.rename(kb_path)

    old_archive = runtime_root / "work-archive"
    new_archive = runtime_root / "archive" / "work"
    if old_archive.exists() and not new_archive.exists():
        new_archive.parent.mkdir(parents=True, exist_ok=True)
        old_archive.rename(new_archive)
