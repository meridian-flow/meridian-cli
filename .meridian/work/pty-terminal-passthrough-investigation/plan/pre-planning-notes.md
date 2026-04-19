# Pre-Planning Notes: PTY Terminal Passthrough Fix

## Runtime Observations

### Code Review: Current Implementation (process.py lines 203-217)

Current PTY child setup:
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
        os.chdir(cwd)
        os.execvpe(command[0], command, env)
```

**Confirmed Gap:** Missing `TIOCSCTTY` ioctl after `setsid()`. Child becomes session leader but has no controlling terminal.

### Fix Scope

Single-line replacement in child fork path:
- Remove: `os.setsid()` + 4x `dup2()` calls + conditional `close()`
- Add: `os.login_tty(slave_fd)`

All parent-side code is correct and unchanged:
- `_sync_pty_winsize()` — works
- `_install_winsize_forwarding()` — works
- `_copy_primary_pty_output()` — works
- Terminal restoration — works

### Design Correction

Smoke matrix (smoke-matrix.md) uses `-H` for harness selection. Should be `--harness` per CLI convention. Apply during phase blueprint creation.

Affected tests: T-09, T-10, T-11 harness selection examples.

### Phasing Hypothesis

This is a minimal bug fix with associated verification work. Likely phases:

1. **Implementation Phase:** Single-line fix to `os.login_tty()` + basic verification
2. **Smoke Verification Phase:** Execute smoke matrix, classify failures by baseline comparison

Both phases can be implemented serially — implementation must complete before smoke verification makes sense.

### Testing Approach

Per design:
- Each smoke test runs baseline (raw harness) first to establish whether failure is Meridian-caused or upstream-only
- Cross-harness tests (T-09, T-10, T-11) verify parity across claude, codex, opencode
- Windows test (T-12) verifies fallback path still works

### Staffing Notes

- @coder for implementation — straightforward single-file change
- @smoke-tester for verification — manual interactive testing required (resize, Ctrl-C, etc.)
- No @unit-tester — this is PTY/terminal behavior not suitable for automated unit tests
- @verifier for build health (pyright, ruff)
