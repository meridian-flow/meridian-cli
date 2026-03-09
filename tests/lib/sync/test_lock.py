import json
import subprocess
import sys

import pytest

from meridian.lib.sync.lock import (
    SyncLockEntry,
    SyncLockFile,
    lock_file_guard,
    read_lock_file,
    write_lock_file,
)


_LOCK_PROBE = """
import fcntl
import sys
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
with path.open("a+b") as handle:
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit(2)
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
raise SystemExit(0)
"""


def _entry() -> SyncLockEntry:
    return SyncLockEntry(
        source_name="personal",
        source_type="repo",
        source_value="haowjy/meridian-skills",
        source_item_name="github-issues",
        requested_ref="main",
        locked_commit="abc123def456",
        item_kind="skill",
        dest_path=".agents/skills/github-issues",
        tree_hash="sha256:0123456789abcdef",
        synced_at="2026-03-08T12:34:56Z",
    )


def test_read_lock_file_returns_empty_for_missing_file(tmp_path):
    lock = read_lock_file(tmp_path / ".meridian" / "sync.lock")

    assert lock == SyncLockFile()


def test_read_lock_file_reads_valid_json(tmp_path):
    lock_path = tmp_path / ".meridian" / "sync.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        json.dumps(
            {
                "version": 1,
                "items": {
                    "skills/github-issues": _entry().model_dump(mode="json"),
                },
            }
        ),
        encoding="utf-8",
    )

    lock = read_lock_file(lock_path)

    assert lock.version == 1
    assert lock.items == {"skills/github-issues": _entry()}


def test_read_lock_file_raises_for_corrupt_json(tmp_path):
    lock_path = tmp_path / ".meridian" / "sync.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        read_lock_file(lock_path)


def test_write_lock_file_roundtrip_and_cleans_tmp_file(tmp_path):
    lock_path = tmp_path / ".meridian" / "sync.lock"
    lock = SyncLockFile(items={"skills/github-issues": _entry()})

    write_lock_file(lock_path, lock)

    assert lock_path.exists()
    assert not lock_path.with_name("sync.lock.tmp").exists()
    assert read_lock_file(lock_path) == lock


def test_lock_file_guard_acquires_and_releases_lock(tmp_path):
    lock_path = tmp_path / ".meridian" / "sync.lock"
    flock_path = lock_path.with_name("sync.lock.flock")

    with lock_file_guard(lock_path):
        assert flock_path.exists()
        held = subprocess.run(
            [sys.executable, "-c", _LOCK_PROBE, str(flock_path)],
            check=False,
        )
        assert held.returncode == 2

    released = subprocess.run(
        [sys.executable, "-c", _LOCK_PROBE, str(flock_path)],
        check=False,
    )
    assert released.returncode == 0
