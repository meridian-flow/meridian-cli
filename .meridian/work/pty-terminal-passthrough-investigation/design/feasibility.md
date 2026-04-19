# Feasibility Evidence

## Probe Results

### Probe 1: Controlling Terminal Availability

**Question:** Is `os.login_tty()` available in the target Python version?

**Method:**
```python
import os, sys
print('Python version:', sys.version.split()[0])
print('login_tty available:', hasattr(os, 'login_tty'))
print('Meridian requires:', 'Python >= 3.12')
print('login_tty added in:', 'Python 3.11')
```

**Result:**
- Python version: 3.12.3
- login_tty available: True
- Conclusion: **Available, no fallback needed**

### Probe 2: What login_tty() Does

**Question:** Does `login_tty()` perform all required operations?

**Method:** `help(os.login_tty)` documentation review

**Result:**
```
Prepare the tty of which fd is a file descriptor for a new login session.

Make the calling process a session leader; make the tty the
controlling tty, the stdin, the stdout, and the stderr of the
calling process; close fd.
```

- Conclusion: **Exactly what we need — setsid + TIOCSCTTY + dup2 + close**

### Probe 3: Python pty Module Behavior

**Question:** How does Python's own pty.fork() handle this?

**Method:** `inspect.getsource(pty.fork)`

**Result:**
```python
def fork():
    """fork() -> (pid, master_fd)
    Fork and make the child a session leader with a controlling terminal."""

    try:
        pid, fd = os.forkpty()
    except (AttributeError, OSError):
        pass
    else:
        if pid == CHILD:
            try:
                os.setsid()
            except OSError:
                # os.forkpty() already set us session leader
                pass
        return pid, fd

    master_fd, slave_fd = openpty()
    pid = os.fork()
    if pid == CHILD:
        os.close(master_fd)
        os.login_tty(slave_fd)  # <-- This is what we need
    else:
        os.close(slave_fd)

    return pid, fd
```

- Conclusion: **Python stdlib uses login_tty() in the same scenario**

### Probe 4: TIOCSCTTY Availability

**Question:** Is `TIOCSCTTY` the right ioctl for controlling terminal acquisition?

**Method:**
```python
import termios
print('TIOCSCTTY =', hex(termios.TIOCSCTTY))
```

**Result:**
- TIOCSCTTY = 0x540e (Linux)
- Conclusion: **Confirmed, and login_tty() handles this internally**

### Probe 5: Current Code Gap Analysis

**Question:** What exactly is missing in the current implementation?

**Method:** Code review of `process.py` lines 202-217

**Current flow:**
```python
os.close(master_fd)
os.setsid()                    # Session leader, no CTTY
os.dup2(slave_fd, 0)
os.dup2(slave_fd, 1)
os.dup2(slave_fd, 2)
if slave_fd > 2:
    os.close(slave_fd)
```

**Missing:** `ioctl(slave_fd, TIOCSCTTY, 0)` to acquire controlling terminal

**Result:**
- Conclusion: **Confirmed gap — setsid() alone doesn't acquire CTTY**

### Probe 6: Signal vs Size Propagation (Review Finding)

**Question:** Is the issue signal delivery or winsize propagation?

**Method:** PTY probes comparing `setsid()+dup2()` vs `login_tty()`

**Results (from architect review):**
- `setsid()+dup2()` child: did NOT receive SIGWINCH
- `login_tty()` child: DID receive SIGWINCH
- `TIOCGWINSZ` query: returned correct size in BOTH cases

**Conclusion:** The issue is **signal delivery**, not winsize propagation. The slave PTY's dimensions are updated when the master receives `TIOCSWINSZ`, but without a controlling terminal, the kernel has no foreground process group to notify. The child never learns that size changed because it never receives SIGWINCH.

This distinction matters for debugging: the parent-side winsize sync is correct; the fix is entirely in the child-side session/CTTY setup.

---

## Validated Assumptions

| Assumption | Status | Evidence |
|------------|--------|----------|
| Python >= 3.12 is required | **Validated** | `pyproject.toml` line 7: `requires-python = ">=3.12"` |
| `os.login_tty()` is available | **Validated** | Probe 1: hasattr returns True |
| `login_tty()` does what we need | **Validated** | Probe 2: documentation confirms all operations |
| Python stdlib uses same pattern | **Validated** | Probe 3: pty.fork() fallback path |
| Current code is missing TIOCSCTTY | **Validated** | Probe 5: code review confirms gap |

---

## Open Questions

### Q1: Does the fix affect harness behavior?

**Status:** Resolved

The fix only affects terminal semantics visible to the child. All three harnesses (claude, codex, opencode) are terminal TUI applications that rely on correct terminal semantics. The fix makes Meridian behave like a proper terminal wrapper instead of a broken one.

### Q2: What about forkpty() instead of openpty()?

**Status:** Resolved

`os.forkpty()` exists and handles session/CTTY setup automatically. However, the current code structure (pre-fork winsize sync, parent-side callback) makes `openpty()` + `fork()` + `login_tty()` the simpler refactor. `forkpty()` would require restructuring the parent-side logic.

### Q3: Any risk of breaking non-interactive paths?

**Status:** Resolved

Non-interactive paths are guarded by:
```python
if output_log_path is None or not sys.stdin.isatty() or not sys.stdout.isatty():
    # Direct subprocess path, no PTY
```

The fix only affects the PTY path, which is only taken when both stdin and stdout are TTYs.

---

## Fix-or-Preserve Verdicts

| Component | Verdict | Rationale |
|-----------|---------|-----------|
| `pty.openpty()` call | **Preserve** | Correct, provides master/slave pair |
| Pre-fork winsize sync | **Preserve** | Correct, child sees right size at startup |
| `os.fork()` call | **Preserve** | Correct, separates parent and child |
| Child `os.close(master_fd)` | **Preserve** | Correct, child doesn't need master |
| Child `os.setsid()` + `dup2()` sequence | **Fix** | Replace with `os.login_tty(slave_fd)` |
| SIGWINCH handler installation | **Preserve** | Correct, forwards resize to master |
| Parent raw mode handling | **Preserve** | Correct, enables passthrough |
| select() copy loop | **Preserve** | Correct, bidirectional passthrough |
| Terminal restoration | **Preserve** | Correct, cleans up parent terminal |
