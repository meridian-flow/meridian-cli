# Refactor Agenda

Structural rearrangements that must precede or accompany feature implementation. Sequencing these early enables parallel feature work.

---

## REF-001: Extract Terminal Transport from process.py

**Priority**: Low (follow-up, not MVP blocking)

**MVP Note**: Web UI researchers don't need interactive terminal support — spawns via web UI use pipe-based execution. This refactor is needed for CLI primary launch with PTY, which is follow-up work.

**Current state**: `process.py` mixes:
- Spawn/session bookkeeping
- PTY allocation (`pty.openpty()`, `os.fork()`)
- Stdin raw-mode handling (`termios`, `tty`)
- Resize forwarding (`SIGWINCH`, `ioctl`)
- Transcript capture
- Exit-code collection

**Target state**: Clean separation:
1. `process.py` retains spawn lifecycle orchestration
2. `terminal/protocol.py` defines `InteractiveTransport` protocol
3. `terminal/posix_transport.py` encapsulates Unix PTY machinery
4. `terminal/windows_transport.py` encapsulates ConPTY machinery
5. `terminal/pipe_fallback.py` encapsulates non-TTY path

**Rationale**: Cannot add Windows terminal support without first extracting the abstraction boundary. Current code has no seam to inject an alternative implementation.

**Test coverage needed**:
- Child sees terminal semantics
- Initial size is correct at startup
- Resize propagation works
- Stdout is mirrored and captured
- Parent terminal state is restored

---

## REF-002: Consolidate File Locking into Platform Module

**Priority**: High (import-time blocker)

**Current state**: `fcntl` imports scattered across:
- `event_store.py` (lines 5, 54, 60)
- `session_store.py` (lines 3, 293, 301, 310, 361, 441, 445, 606, 666)
- `process.py` (lines 3, 221, 233)

**Target state**: Single `platform/locking.py` module:
- Exports `lock_file()` context manager
- Platform dispatch inside the module
- No `fcntl` imports at module load time anywhere

**Rationale**: Without this refactor, meridian cannot even be imported on Windows.

**Migration path**:
1. Create `platform/locking.py` with current Unix implementation
2. Add Windows implementation using `msvcrt.locking()`
3. Update all callsites to use new module
4. Delete direct `fcntl` usage

---

## REF-003: Consolidate Process Termination into Shared Helper

**Priority**: Medium (enables clean feature work)

**Current state**: Termination logic duplicated across:
- `claude_ws.py:405-422` (`_terminate_process()`)
- `codex_ws.py:534-565` (`_cleanup_resources()`)
- `opencode_http.py:669-687` (`_cleanup_runtime()`)
- `signals.py:21-40` (`signal_process_group()`)
- `runner_helpers.py:259-278` (`terminate_process()`)

Each implements terminate → wait → kill pattern independently.

**Target state**: Single `terminate.py` module with:
- `terminate_tree()` async helper using psutil
- Children-first ordering
- Re-snapshot before escalation
- Shared grace period handling

**Rationale**: Process tree termination is cross-platform via psutil. Consolidation eliminates Windows-specific fixes in 5+ locations.

---

## REF-004: Extract Platform-Aware Harness Storage Resolution

**Priority**: Medium (required for session discovery)

**Current state**: Hardcoded paths in adapters:
- `claude.py:71`: `Path.home() / ".claude" / "projects"`
- `codex.py`: `~/.codex` (implicit)
- `opencode.py:70`: `Path.home() / ".local" / "share" / "opencode" / "log"`

**Target state**: `platform/storage.py` module with:
- `claude_projects_root() -> Path`
- `codex_storage_root() -> Path`
- `opencode_storage_root() -> Path`

Each returns platform-appropriate paths (XDG on Unix, AppData on Windows).

**Rationale**: Harness storage conventions differ by platform. Centralizing makes the policy explicit and testable.

---

## REF-005: Standardize IPC Transport Selection

**Priority**: Medium (required for control/app transport)

**Current state**: Unix domain socket usage scattered across:
- `control_socket.py:32`: `asyncio.start_unix_server()`
- `app_cmd.py:45`: `uvicorn.run(..., uds=...)`
- `signal_canceller.py:145`: `aiohttp.UnixConnector()`

**Target state**: `platform/ipc.py` module with:
- `ServerAddress` dataclass (unix_path or tcp_port)
- `resolve_control_address(user_state_root, spawn_id)` — read address from port file (Windows) or derive socket path (Unix)
- `resolve_app_address(user_state_root)` — same pattern for app server
- `connect_to_control(address)` — return `(StreamReader, StreamWriter)`
- Address-to-uvicorn/aiohttp conversion methods

**Transport choice**:
- Unix: `asyncio.start_unix_server()` / `asyncio.open_unix_connection()` with socket paths
- Windows: `asyncio.start_server()` / `asyncio.open_connection()` with TCP localhost (`127.0.0.1:<port>`)

Both use the same high-level asyncio streams API. No named pipes — Python's asyncio lacks a high-level streams API for named pipes.

**Port file convention** (under user state root, resolved via project UUID):
- Control socket: `~/.meridian/projects/<UUID>/spawns/{spawn_id}/control.port`
- App server: `~/.meridian/app.port` (user-global, not per-project)

Windows equivalents:
- Control socket: `%LOCALAPPDATA%\meridian\projects\<UUID>\spawns\{spawn_id}\control.port`
- App server: `%LOCALAPPDATA%\meridian\app.port`

**Rationale**: IPC transport is inherently platform-specific, but the asyncio streams API is shared. Centralizing address resolution keeps harness and spawn code transport-agnostic while using the simplest implementation path on each platform.

---

## REF-006: Platform Guard for Directory Fsync

**Priority**: Low (runtime blocker, but simple fix)

**Current state**: `atomic.py:10-20` has `_fsync_directory()` that opens a directory with `os.O_DIRECTORY` and calls `os.fsync()`. This fails on Windows where directories cannot be opened as files.

**Target state**: Add platform guard:
```python
def _fsync_directory(path: Path) -> None:
    if IS_WINDOWS:
        return  # NTFS is journaling; os.replace() is durable
    # ... existing Unix implementation
```

**Rationale**: Windows does not allow opening directories as files. The directory fsync is a durability optimization for Unix filesystems that may reorder metadata updates. NTFS provides equivalent guarantees via journaling. Skipping the call on Windows is safe for Meridian's crash-only design.

**Test coverage needed**:
- Atomic write tests on Windows verify file replacement works
- No explicit fsync verification (observing durability guarantees requires power-loss testing)

---

## REF-007: Deferred Import Pattern for Unix-Only Modules

**Priority**: High (import-time blocker)

**Current state**: Top-level imports in:
- `process.py:3-14`: `fcntl`, `pty`, `termios`, `tty`, `select`
- `event_store.py:5`: `fcntl`
- `session_store.py:3`: `fcntl`

**Target state**: All Unix-only stdlib imports either:
1. Behind `if IS_POSIX:` guards at module level, or
2. Deferred to function bodies where used

**Rationale**: Python imports execute at module load. Any Unix-only import at top level makes the entire module unimportable on Windows.

**Note**: This refactor must happen alongside or before REF-001 and REF-002.

---

## Refactor Dependency Graph (MVP Focus)

```
REF-007 (deferred imports) [MVP BLOCKING]
    |
    +---> REF-002 (file locking) [MVP BLOCKING]
              |
              +---> WIN-LOCK-* features

REF-003 (termination helper) [MVP BLOCKING]
    |
    +---> WIN-TERM-* features

REF-004 (storage paths) [MVP BLOCKING]
    |
    +---> WIN-STORAGE-* features

REF-005 (IPC transport) [MVP BLOCKING]
    |
    +---> WIN-CONTROL-* features (app server)

REF-006 (directory fsync guard) [MVP BLOCKING]
    |
    +---> WIN-LOCK-* features (atomic writes work on Windows)

REF-001 (terminal transport) [FOLLOW-UP]
    |
    +---> WIN-LAUNCH-* features (CLI primary launch)
```

REF-007 blocks REF-002 (locking needs deferred Unix imports).
REF-003, REF-004, REF-005, REF-006 have no blocker dependencies — can start immediately.
REF-001 is follow-up work, not MVP blocking.

---

## Implementation Order Recommendation (MVP)

1. **Phase 0** (foundational): REF-007 (deferred imports)
2. **Phase 1** (parallel, can start immediately):
   - REF-003 (termination helper)
   - REF-004 (storage paths)
   - REF-005 (IPC transport)
   - REF-006 (directory fsync guard)
3. **Phase 2** (after Phase 0): REF-002 (file locking)
4. **Follow-up** (post-MVP): REF-001 (terminal transport for CLI primary launch)

The MVP path enables web UI researchers: app server runs, spawns execute via pipes, state persists correctly. CLI primary launch with interactive terminal is follow-up work.
