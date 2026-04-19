# PTY Terminal Passthrough Architecture

## Current Implementation Analysis

### Location

`src/meridian/lib/launch/process.py`, function `_run_primary_process_with_capture()`

### Current Flow (lines 196-238)

```
1. pty.openpty() → master_fd, slave_fd
2. _sync_pty_winsize(stdout → master_fd)
3. os.fork()
4. Child:
   a. os.close(master_fd)
   b. os.setsid()                    # Creates new session
   c. os.dup2(slave_fd, 0/1/2)       # Redirect stdio
   d. os.close(slave_fd) if > 2
   e. os.chdir(cwd)
   f. os.execvpe(...)
5. Parent:
   a. os.close(slave_fd)
   b. _copy_primary_pty_output(...)
```

### Broken Invariant

**After step 4b (`os.setsid()`), the child is a session leader with no controlling terminal.**

The current code does NOT acquire a controlling terminal for the slave PTY. Without a controlling terminal:

- **Signal delivery fails:** SIGWINCH is not delivered to the child's foreground process group when the parent's terminal resizes
- **Interrupt generation fails:** Terminal-generated SIGINT (from Ctrl-C typed in raw mode) is not delivered to the child
- **Note:** The PTY slave's window size (`TIOCGWINSZ`) IS correctly updated by the parent's `TIOCSWINSZ` on the master fd. The issue is that the child never receives the SIGWINCH notification to re-query.
- Result: display corruption on terminal resize, and Ctrl-C may not interrupt the harness as expected

### Why This Matters

POSIX terminal signal delivery:

```
Terminal resize
    ↓
Kernel sends SIGWINCH to foreground process group of controlling terminal
    ↓
Process group members handle SIGWINCH and query new size via TIOCGWINSZ
    ↓
TUI redraws with correct dimensions
```

Without a controlling terminal, the "foreground process group of controlling terminal" is undefined, so the kernel has no target for SIGWINCH delivery.

---

## Proposed Fix

### Change

Replace the manual `setsid()` + `dup2()` sequence with `os.login_tty(slave_fd)`.

### What login_tty() Does

The C library's `login_tty()` (exposed as `os.login_tty()` in Python 3.11+) performs:

1. `setsid()` — create new session, become session leader
2. `ioctl(fd, TIOCSCTTY, 0)` — acquire fd as controlling terminal
3. `dup2(fd, 0/1/2)` — redirect stdin/stdout/stderr
4. `close(fd)` — close original fd

This is exactly what Python's own `pty.fork()` does in its fallback path.

### Code Change (process.py)

**Before (lines 203-211):**
```python
if child_pid == 0:
    try:
        os.close(master_fd)
        os.setsid()
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        if slave_fd > 2:
            os.close(slave_fd)
```

**After:**
```python
if child_pid == 0:
    try:
        os.close(master_fd)
        os.login_tty(slave_fd)
```

### Why This Is Sufficient

- `os.login_tty()` is available in Python 3.11+
- Meridian requires Python >= 3.12
- `login_tty()` handles all the edge cases:
  - `setsid()` may fail if already session leader — `login_tty()` handles this
  - `TIOCSCTTY` requires specific conditions — `login_tty()` handles this
  - fd duplication and close order — `login_tty()` handles this

### Compatibility

| Platform | Availability | Behavior | Evidence |
|----------|--------------|----------|----------|
| Linux | `os.login_tty()` available | Full PTY support | Directly probed |
| macOS | `os.login_tty()` available | Full PTY support | Inferred (POSIX) |
| Windows | PTY path bypassed | No change needed | Code review |

**Note:** macOS compatibility is inferred from `os.login_tty()` being a standard POSIX function. Python exposes it on all POSIX platforms. Direct macOS probing was not performed but is low risk.

---

## Architecture Invariants Preserved

1. **PTY path only for interactive terminals** — unchanged, guarded by `sys.stdin.isatty() and sys.stdout.isatty()`
2. **Windows bypass** — unchanged, guarded by `IS_WINDOWS`
3. **SIGWINCH forwarding** — unchanged, `_install_winsize_forwarding()` still syncs master fd
4. **Raw mode management** — unchanged, `_copy_primary_pty_output()` still handles this
5. **Child process isolation** — unchanged, child still becomes session leader

## Adjacent Behaviors

| Behavior | Current | After Fix | Notes |
|----------|---------|-----------|-------|
| EOF handling | stdin_open flag | No change | Works regardless of CTTY |
| Ctrl-C byte passthrough | 0x03 in raw mode | No change | Byte still passes through |
| Ctrl-C signal generation | **BROKEN** | **FIXED** | With CTTY, kernel generates SIGINT |
| Terminal restoration | tcsetattr in finally | No change | Parent-side only |
| Bidirectional copy | select loop | No change | Independent of CTTY |
| Winsize initial sync | Before fork | No change | Independent of CTTY |
| Winsize propagation | TIOCSWINSZ works | No change | Slave sees new size |
| Resize notification | **BROKEN** | **FIXED** | With CTTY, SIGWINCH delivered |

---

## Risk Assessment

### Low Risk

- Fix is a single-line replacement using a well-tested stdlib function
- `login_tty()` is what Python's own `pty.fork()` uses
- No new dependencies
- No changes to parent-side logic
- No changes to non-PTY paths

### Testing Required

See `smoke-matrix.md` for verification plan.
