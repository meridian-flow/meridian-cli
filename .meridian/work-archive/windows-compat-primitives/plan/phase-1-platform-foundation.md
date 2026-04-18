# Phase 1: Platform Foundation

## Scope
Create the platform abstraction module with constants and cross-platform file locking. Also add the fsync guard.

## Files to Create/Modify

### 1. Create `src/meridian/lib/platform/__init__.py`
```python
"""Platform detection constants for cross-platform code."""

import sys

IS_WINDOWS = sys.platform == "win32"
IS_POSIX = sys.platform != "win32"

__all__ = ["IS_WINDOWS", "IS_POSIX"]
```

### 2. Create `src/meridian/lib/platform/locking.py`

Cross-platform file locking module. Key requirements:
- Exports `lock_file()` context manager matching the existing signature in event_store.py
- Support thread-local reentrancy tracking (copy pattern from event_store.py)
- On POSIX: use `fcntl.flock()`
- On Windows: use `msvcrt.locking()`

```python
"""Cross-platform file locking for JSONL event stores."""

from __future__ import annotations

import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator

IS_WINDOWS = sys.platform == "win32"

_THREAD_LOCAL = threading.local()


def _held_locks() -> dict[Path, tuple[IO[bytes], int]]:
    """Return the thread-local dict tracking held lock handles and depths."""
    held = getattr(_THREAD_LOCAL, "held", None)
    if held is None:
        held = {}
        _THREAD_LOCAL.held = held
    return held


@contextmanager
def lock_file(lock_path: Path) -> Iterator[IO[bytes]]:
    """Cross-platform exclusive file lock with reentrancy support.
    
    On POSIX: uses fcntl.flock()
    On Windows: uses msvcrt.locking()
    """
    key = lock_path.resolve()
    held = _held_locks()
    existing = held.get(key)
    
    # Handle reentrant lock acquisition
    if existing is not None:
        handle, depth = existing
        held[key] = (handle, depth + 1)
        try:
            yield handle
        finally:
            current_handle, current_depth = held[key]
            if current_depth <= 1:
                held.pop(key, None)
            else:
                held[key] = (current_handle, current_depth - 1)
        return

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    
    if IS_WINDOWS:
        yield from _win_lock_file(lock_path, key, held)
    else:
        yield from _posix_lock_file(lock_path, key, held)


def _posix_lock_file(
    lock_path: Path,
    key: Path,
    held: dict[Path, tuple[IO[bytes], int]],
) -> Iterator[IO[bytes]]:
    """POSIX file locking using fcntl.flock()."""
    import fcntl
    
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        held[key] = (handle, 1)
        try:
            yield handle
        finally:
            held.pop(key, None)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _win_lock_file(
    lock_path: Path,
    key: Path,
    held: dict[Path, tuple[IO[bytes], int]],
) -> Iterator[IO[bytes]]:
    """Windows file locking using msvcrt.locking()."""
    import msvcrt
    import time
    
    handle = lock_path.open("a+b")
    try:
        # msvcrt.locking() locks a region of the file.
        # We lock 1 byte at position 0 to simulate whole-file lock.
        # LK_NBLCK = non-blocking, LK_LOCK = blocking with retry.
        # We use a retry loop for blocking behavior.
        fd = handle.fileno()
        
        # Seek to start for consistent locking region
        handle.seek(0)
        
        # Retry loop for blocking lock (msvcrt.locking is non-blocking)
        max_retries = 100
        for _ in range(max_retries):
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            # Final attempt with blocking
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
        
        held[key] = (handle, 1)
        try:
            yield handle
        finally:
            held.pop(key, None)
            handle.seek(0)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            handle.close()
    except Exception:
        handle.close()
        raise


__all__ = ["lock_file"]
```

### 3. Update `src/meridian/lib/state/atomic.py`

Add Windows guard to `_fsync_directory()`:

```python
def _fsync_directory(path: Path) -> None:
    """Fsync a directory entry so a completed replace survives a crash."""
    import sys
    
    # NTFS is journaling; os.replace() is durable without explicit fsync
    if sys.platform == "win32":
        return
    
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    directory_fd = os.open(path, flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
```

## Exit Criteria
- `src/meridian/lib/platform/__init__.py` exists with IS_WINDOWS, IS_POSIX
- `src/meridian/lib/platform/locking.py` exports `lock_file()` context manager
- `atomic.py` skips directory fsync on Windows
- All existing tests pass
- `uv run pyright` passes
