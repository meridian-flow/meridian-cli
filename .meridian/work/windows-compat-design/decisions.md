# Design Decisions

Key judgment calls made during Windows compatibility design.

---

## D-012: MVP Scope — Web UI First, CLI Terminal Later

**Decision**: Target web UI researchers as MVP. Defer CLI primary launch with interactive terminal to follow-up work.

**Rationale**: Web UI spawns use pipe-based execution (no PTY needed). The terminal transport extraction (REF-001) and ConPTY/pywinpty integration add significant complexity. Deferring them unblocks Windows support for the primary persona faster.

**What MVP includes**:
- App server on Windows (TCP localhost)
- Pipe-based spawn execution
- State locking (msvcrt)
- Atomic writes (skip directory fsync)
- IPC transport (TCP localhost)
- Harness storage resolution

**What MVP defers**:
- ConPTY/pywinpty terminal transport
- CLI primary launch with PTY semantics
- Terminal resize propagation

---

## D-013: Align with UUID-Based State Model

**Decision**: Adopt workspace-config-design's UUID model for state paths.

**State layout**:
- Project UUID in `.meridian/id`, generated on first write
- User state root: `~/.meridian/` (Unix) or `%LOCALAPPDATA%\meridian\` (Windows)
- Project ephemeral state: `~/.meridian/projects/<UUID>/`
- App server state: user root level (user-global, serves multiple projects)

**What this replaces**:
- No project_key derivation from git remote or path hash
- No complex path normalization

**Rationale**: Simpler model, survives project folder renames, no derivation algorithm to maintain.

---

## D-001: Thin Platform Adapters over Deep Rewrites

**Decision**: Use thin platform dispatch modules (`platform/locking.py`, `platform/ipc.py`, `platform/storage.py`) rather than rewriting core modules for cross-platform behavior.

**Alternatives considered**:
- Rewrite each affected module with inline platform checks
- Use a cross-platform abstraction library (e.g., `portalocker`)

**Rationale**: Thin adapters keep platform-specific code isolated and testable. Inline checks scatter platform logic. Third-party deps add maintenance burden for stdlib-equivalent functionality.

---

## D-002: msvcrt.locking() over portalocker

**Decision**: Use stdlib `msvcrt.locking()` for Windows file locking rather than adding `portalocker` dependency.

**Alternatives considered**:
- `portalocker` (cross-platform locking library)
- `filelock` (another cross-platform option)

**Rationale**: Current locking needs are simple (exclusive locks on state files). `msvcrt` is stdlib, zero new dependencies. Can upgrade to a library if edge cases emerge.

---

## D-003: TCP Localhost for All Windows IPC

**Decision**: Use TCP localhost (`127.0.0.1:<port>`) for both per-spawn control sockets and app server on Windows.

**Alternatives considered**:
- Named pipes for control sockets, TCP for app server (original proposal)
- Named pipes for everything (lower latency, native Windows IPC)

**Rationale**: Python's asyncio does not provide a high-level streams API for Windows named pipes. The available options are:

1. **`loop.start_serving_pipe()` / `loop.create_pipe_connection()`** — low-level protocol-based APIs that require writing protocol classes, not compatible with the `StreamReader`/`StreamWriter` pattern used by `start_unix_server()`. Would require significant code divergence between platforms.

2. **TCP localhost** — uses the identical `asyncio.start_server()` / `asyncio.open_connection()` API as Unix sockets, works with uvicorn and aiohttp out of the box, minimal platform-specific code.

The original design incorrectly assumed `asyncio.start_server(..., pipe=pipe_name)` exists — it does not. TCP localhost is the simplest implementation that preserves API parity across platforms.

**Security**: Binding to `127.0.0.1` restricts connections to the local machine, equivalent to Unix domain socket access control. Port numbers are persisted to files under `.meridian/` with the same filesystem permissions as Unix socket paths.

**Latency**: The latency difference between TCP localhost and named pipes is measured in microseconds — negligible for control traffic that occurs at human interaction frequency.

---

## D-004: pywinpty as Windows Terminal Backend

**Decision**: Use `pywinpty` (ConPTY wrapper) for Windows interactive terminal transport.

**Alternatives considered**:
- Raw ConPTY via ctypes/cffi
- winpty (older pseudo-console library)
- Skip interactive terminal support on Windows

**Rationale**: pywinpty is maintained (Spyder team), provides ConPTY with fallback to winpty, has clean Python API. Raw ConPTY is complex; winpty alone is legacy; skipping interactive support breaks primary launch UX.

---

## D-005: signal.signal() over loop.add_signal_handler()

**Decision**: Use `signal.signal()` for shutdown signal handling instead of `loop.add_signal_handler()`.

**Alternatives considered**:
- Use ProactorEventLoop with IOCP integration
- Accept Ctrl+C only (simplest)
- Third-party async signal library

**Rationale**: `signal.signal()` works on both platforms for SIGINT. `add_signal_handler()` is POSIX-only. ProactorEventLoop adds complexity. SIGINT (Ctrl+C) is the primary cancellation signal anyway.

---

## D-006: Symlink Fallback to File Copy

**Decision**: When symlink creation fails on Windows due to privilege restrictions, fall back to file copying for Claude session bridging.

**Alternatives considered**:
- Require symlink privileges (Developer Mode or elevation)
- Skip bridging entirely
- Use directory junctions (Windows-specific)

**Rationale**: Symlinks are an optimization for session access across cwd boundaries. File copy achieves the same functional result with slight IO overhead. Not requiring elevation improves out-of-box experience.

---

## D-007: Extend Env Allowlist Rather Than Replace

**Decision**: Add Windows environment variables to the existing allowlist rather than creating separate per-platform lists.

**Alternatives considered**:
- Separate `_UNIX_ENV_ALLOWLIST` and `_WINDOWS_ENV_ALLOWLIST`
- Dynamic allowlist based on platform detection

**Rationale**: Many cross-platform tools check both Unix and Windows env vars. A unified allowlist is simpler and handles WSL/Git Bash scenarios where both may be present.

---

## D-008: Deferred Imports at Function Level

**Decision**: Defer Unix-only imports (`fcntl`, `pty`, `termios`, `tty`) to function bodies rather than using module-level `if IS_POSIX:` guards.

**Alternatives considered**:
- Module-level conditional imports
- Separate `.py` files per platform imported dynamically

**Rationale**: Function-level deferral is simpler and keeps code in one place. Module-level guards are cleaner but require more careful import ordering. Separate files fragment related logic.

---

## D-009: Process Tree Termination via psutil

**Decision**: Use `psutil.Process.children(recursive=True)` for process tree enumeration and termination.

**Alternatives considered**:
- Windows Job Objects for child process management
- Keep per-adapter termination logic

**Rationale**: psutil is already a dependency (used in `liveness.py`). It provides cross-platform process tree operations. Job Objects are Windows-only and require setup at process creation time. Per-adapter logic duplicates the same pattern.

---

## D-010: Skip Directory Fsync on Windows

**Decision**: Skip the directory fsync step in `atomic.py` on Windows rather than attempting a Windows-specific equivalent.

**Alternatives considered**:
- Use `FlushFileBuffers` via ctypes on parent directory handle
- Use `SetFileInformationByHandle` with `FileBasicInfo` to force metadata flush
- Require NTFS transactional writes (TxF)

**Rationale**: Windows does not allow opening a directory as a file (`os.open(dir_path, ...)` fails), so the current `_fsync_directory()` pattern cannot work.

The directory fsync is a belt-and-suspenders measure for Unix filesystems that may reorder metadata updates. NTFS is a journaling filesystem that guarantees metadata consistency after `os.replace()` completes. The remaining durability gap (data written to disk but directory entry lost on power failure) is:
1. A narrow window that requires precise power-loss timing
2. Already handled by Meridian's crash-only reconciliation on next startup
3. Not worth adding ctypes complexity for

---

## D-011: Windows 10 1809+ as Minimum Version

**Decision**: Target Windows 10 version 1809 (October 2018 Update) as minimum for full interactive support.

**Alternatives considered**:
- Support older Windows with degraded behavior
- Require Windows 11 only

**Rationale**: ConPTY was introduced in Windows 10 1809. Older versions would require winpty fallback or non-interactive mode. 1809 is 6+ years old — reasonable baseline. Non-interactive spawns work on older versions.
