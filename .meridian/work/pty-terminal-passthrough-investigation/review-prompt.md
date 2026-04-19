# Final Review: PTY Terminal Passthrough Fix

## Change Summary

A minimal fix to `src/meridian/lib/launch/process.py` that replaces the child-side PTY setup sequence with `os.login_tty(slave_fd)`.

## The Fix

**Before:**
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

**After:**
```python
if child_pid == 0:
    try:
        os.close(master_fd)
        os.login_tty(slave_fd)
        os.chdir(cwd)
        os.execvpe(command[0], command, env)
```

## Design Rationale

The previous code created a new session (`setsid()`) but never acquired a controlling terminal for the PTY slave. Without a controlling terminal:
- SIGWINCH (resize) is never delivered to the child's foreground process group
- Terminal-generated SIGINT (Ctrl-C) doesn't reach the child

`os.login_tty()` performs:
1. `setsid()` — become session leader
2. `ioctl(TIOCSCTTY)` — acquire controlling terminal
3. `dup2(fd, 0/1/2)` — redirect stdio
4. `close(fd)` — close original fd

This is exactly what Python's own `pty.fork()` does in its fallback path.

## Review Focus Areas

1. **Design Alignment:** Does the fix match the approved architecture in `design/architecture/pty-passthrough.md`?
2. **Scope Discipline:** Is the fix limited to child-side PTY setup? No parent-side changes?
3. **Cross-Platform Risk:** Windows and non-TTY fallback paths are unchanged?
4. **Evidence Completeness:** Build health verified? Smoke classification documented?

## Context Files

- `design/spec/pty-passthrough.md` — EARS behavioral contract
- `design/architecture/pty-passthrough.md` — approved fix mechanism
- `design/feasibility.md` — probe evidence validating `os.login_tty()` availability
- `decisions.md` — design rationale and smoke test classification decisions
- `plan/leaf-ownership.md` — evidence coverage table
