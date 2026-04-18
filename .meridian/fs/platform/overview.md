# Platform

Cross-platform OS primitives used across the codebase. Collapses OS-specific branches that used to live inline in multiple modules behind narrow adapters so callers stay OS-neutral.

Source: `src/meridian/lib/platform/`

## Why This Module Exists

Windows support is a product requirement (CLAUDE.md #6). Before this module, platform branches (`fcntl` vs `msvcrt`, signal handling, fsync) were scattered inline across `state/`, `launch/`, and `streaming/`. Concentrating them here follows CLAUDE.md #7 (prefer cross-platform abstractions over handwritten branches): callers import `lock_file` or `terminate_tree` and never touch OS conditionals.

## Module Map

```
src/meridian/lib/platform/
├── __init__.py    — IS_WINDOWS / IS_POSIX detection constants
├── locking.py     — lock_file() context manager: exclusive file lock, thread-local reentrant
└── terminate.py   — terminate_tree() async helper: SIGTERM → grace → SIGKILL process tree kill
```

## OS Detection — `__init__.py`

```python
IS_WINDOWS: bool   # sys.platform == "win32"
IS_POSIX:   bool   # not IS_WINDOWS
```

Prefer these over inline `sys.platform` comparisons — consistent spelling, importable as a named concept, easy to grep.

## File Locking — `locking.py`

```python
@contextmanager
def lock_file(lock_path: Path) -> Iterator[IO[bytes]]: ...
```

Acquires an exclusive file lock for the duration of the `with` block. Used by state stores to serialize concurrent writes. Confirmed callers: `state/event_store.py` (JSONL appends for spawns/sessions), `state/session_store.py` (session event writes and session-id-counter), `state/work_store.py` (work item mutations), `state/user_paths.py` (UUID creation under `id.lock`). `state/atomic.py` does NOT call `lock_file`.

**Behavior:**
- **Thread-local reentrancy:** a thread that already holds the lock can re-enter `lock_file` on the same path without deadlocking. A per-thread depth counter tracks nesting; the underlying OS lock is released only on the outermost exit.
- **POSIX:** `fcntl.flock(LOCK_EX)` — advisory, kernel-backed.
- **Windows:** `msvcrt.locking(LK_NBLCK, 1)` with a retry loop (50 ms sleep). Locks a 1-byte region at offset 0 (NTFS requires a non-zero-length file; the implementation writes a guard byte and flushes before locking). Released via `LK_UNLCK`.

`fcntl` is imported inside `_acquire_posix_lock`/`_release_posix_lock` (not at module top) so the package imports cleanly on Windows. Same deferred-import pattern applies to `msvcrt` on POSIX. See [deferred imports](#deferred-import-pattern) below.

## Process Tree Termination — `terminate.py`

```python
async def terminate_tree(
    process: asyncio.subprocess.Process,
    *,
    grace_secs: float = 5.0,
) -> None: ...
```

Terminates `process` and all its descendants. Used by the launch layer when a spawn is cancelled or times out.

**Sequence:**
1. Snapshot root + children via `psutil` *before* sending signals (avoids races where children fork after the root exits).
2. Send `SIGTERM` (Windows: `TerminateProcess` via psutil) to every process in the tree, children first.
3. `asyncio.to_thread(psutil.wait_procs, tree, timeout=grace_secs)` — async-safe wait.
4. If any processes survive: send `SIGKILL` / force-kill and wait up to 1 second.

**Why psutil:** it already handles cross-platform PID/tree semantics and process-not-found races (`NoSuchProcess`, `AccessDenied`) without additional transitive dependencies. Avoids hand-rolling OS-specific child enumeration (`/proc` on Linux, `NtQueryInformationProcess` on Windows).

Returns immediately if `process.returncode is not None` (already exited).

## Deferred-Import Pattern

`fcntl`, `pty`, `termios`, `tty`, and `msvcrt` are POSIX-only or Windows-only stdlib modules that raise `ImportError` on the other platform if imported at module top. Two patterns gate these imports:

**(a) Module-level lazy proxy (`_DeferredUnixModule`):** `launch/process.py` and `state/session_store.py` declare module-level proxy objects (e.g. `fcntl = _DeferredUnixModule("fcntl")`, `termios = _DeferredUnixModule("termios")`). The proxy forwards attribute access to the real module on first use, so the package imports cleanly on Windows while preserving the ergonomics of normal module-level references.

**(b) Inline function-local import:** `platform/locking.py` imports `fcntl` and `msvcrt` inside the POSIX/Windows acquire and release functions (`_acquire_posix_lock`, `_release_posix_lock`, etc.). Other affected files: `launch/runner_helpers.py`, `launch/signals.py`.

Both patterns make all platform modules importable on all OSes, enabling `import meridian` to succeed without branching the import path.

## Directory fsync

Directory fsync (syncing the parent directory after a file rename) is skipped on Windows. NTFS is a journaling filesystem and does not require the caller to fsync the parent directory to guarantee rename durability — attempting it raises `PermissionError`. The guard is in `state/atomic.py`.
