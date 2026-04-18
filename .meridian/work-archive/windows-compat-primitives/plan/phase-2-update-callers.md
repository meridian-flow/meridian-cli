# Phase 2: Update Callers to Use Platform Locking

## Scope
Update event_store.py, session_store.py, and process.py to use the platform locking module and defer Unix-only imports.

## Dependencies
- Phase 1 must be complete (platform module must exist)

## Files to Modify

### 1. Update `src/meridian/lib/state/event_store.py`

Changes:
- Remove `import fcntl` from top
- Replace local `lock_file()` implementation with import from platform module

```python
# Before:
import fcntl
# ...
def _held_locks() -> ...: ...
@contextmanager
def lock_file(lock_path: Path) -> ...: ...

# After:
from meridian.lib.platform.locking import lock_file
# Remove: import fcntl
# Remove: _THREAD_LOCAL, _held_locks(), lock_file() definitions
```

Keep everything else (append_event, read_events, utc_now_iso) unchanged.

### 2. Update `src/meridian/lib/state/session_store.py`

Changes:
- Remove `import fcntl` from top
- Replace all direct fcntl usage with platform abstractions
- Import lock_file from platform module (it's already imported from event_store, but after refactor will come from platform)

Key fcntl usages to update:
- Line 293-301: `_acquire_session_lock()` - uses fcntl.flock
- Line 310-311: `_release_session_lock()` - uses fcntl.flock  
- Line 361: `start_session()` error path - uses fcntl.flock
- Line 441-445: `list_active_sessions()` - uses fcntl.flock with LOCK_NB
- Line 606, 666: `cleanup_stale_sessions()` - uses fcntl.flock

For session-specific locking (not event store locking), create platform-aware helpers:
- `_posix_acquire_session_lock()` and `_win_acquire_session_lock()`
- `_posix_release_session_lock()` and `_win_release_session_lock()`
- `_posix_try_lock_nonblocking()` and `_win_try_lock_nonblocking()`

### 3. Update `src/meridian/lib/launch/process.py`

Changes:
- Move Unix-only imports (`fcntl`, `pty`, `termios`, `tty`, `select`) behind platform guards
- The PTY-related code only runs when stdin/stdout are TTYs, so guard the imports

```python
# Before (top of file):
import fcntl
import pty
import select
import termios
import tty

# After:
# Remove these top-level imports
# Add at function level where needed:

def _copy_primary_pty_output(...):
    import select
    import termios
    import tty
    # ... rest of function

def _read_winsize(fd: int) -> bytes | None:
    import fcntl
    import termios
    # ... rest of function

def _sync_pty_winsize(...):
    import fcntl
    import termios
    # ... rest of function

def _run_primary_process_with_capture(...):
    # Guard PTY path
    if output_log_path is None or not sys.stdin.isatty() or not sys.stdout.isatty():
        # subprocess.Popen path - no Unix imports needed
        ...
    else:
        # PTY path - import Unix modules here
        import pty
        # ... rest of PTY code
```

## Exit Criteria
- No `import fcntl` at module level in event_store.py, session_store.py, or process.py
- No `import pty`, `import termios`, `import tty` at module level in process.py
- All functionality preserved on Unix
- `uv run python -c "from meridian.lib.state import event_store, session_store; from meridian.lib.launch import process"` works (conceptually on Windows)
- All existing tests pass
- `uv run pyright` passes
