# Phase 1: Child PTY `login_tty()` Fix

## Task

Replace the child-side `os.setsid()` + `os.dup2()` sequence with `os.login_tty(slave_fd)` in `src/meridian/lib/launch/process.py`.

## Current Code (lines 203-217)

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

## Required Change

Replace lines 206-211 (the `os.setsid()` + `os.dup2()` + conditional close) with a single call:

```python
os.login_tty(slave_fd)
```

The resulting code should be:

```python
if child_pid == 0:
    try:
        os.close(master_fd)
        os.login_tty(slave_fd)
        os.chdir(cwd)
        os.execvpe(command[0], command, env)
```

## Why This Works

`os.login_tty(slave_fd)` performs:
1. `setsid()` — create new session, become session leader
2. `ioctl(fd, TIOCSCTTY, 0)` — acquire fd as controlling terminal
3. `dup2(fd, 0/1/2)` — redirect stdin/stdout/stderr
4. `close(fd)` — close original fd

This is exactly what Python's own `pty.fork()` does. The current code is missing step 2, which causes resize signals (SIGWINCH) to never be delivered to the child.

## Scope Boundaries

- ONLY modify the child-side PTY setup in `_run_primary_process_with_capture()`
- Preserve `os.close(master_fd)` before the login_tty call
- Preserve `os.chdir(cwd)` and `os.execvpe(...)` after
- Do NOT modify any parent-side logic
- Do NOT modify Windows/non-TTY fallback paths
- Do NOT add any new imports (os module already imported)

## Exit Criteria

- `os.login_tty(slave_fd)` replaces the setsid/dup2/close sequence
- No parent-side PTY behavior changed
- Diff is minimal and limited to the approved surface
