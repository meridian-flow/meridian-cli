# Decision Log

## D-01: Use login_tty() Instead of Manual TIOCSCTTY

**Decision:** Replace manual `setsid()` + `dup2()` sequence with `os.login_tty(slave_fd)`.

**Reasoning:**
- `login_tty()` is the standard POSIX function for this exact use case
- Python 3.11+ exposes it as `os.login_tty()`
- Meridian requires Python >= 3.12, so it's always available
- Python's own `pty.fork()` uses `login_tty()` in its fallback path
- Single function call replaces 6 lines and eliminates edge case bugs

**Alternatives Rejected:**

1. **Manual `ioctl(TIOCSCTTY)`** — rejected because `login_tty()` handles edge cases (setsid failure, fd duplication order) that we'd have to reimplement
2. **Switch to `os.forkpty()`** — rejected because current code structure (pre-fork winsize sync, parent callbacks) would require more restructuring
3. **Use `pty.fork()` from stdlib** — rejected because it doesn't give us control over the pre-fork winsize sync or post-fork callbacks

**Constraints Discovered:**
- `TIOCSCTTY` is Linux-specific (different value on BSD/macOS)
- `login_tty()` abstracts this platform difference
- Windows doesn't have POSIX PTYs at all (already handled by bypass)

---

## D-02: Preserve Existing SIGWINCH Handler Architecture

**Decision:** Keep the current `_install_winsize_forwarding()` approach unchanged.

**Reasoning:**
- Current handler correctly syncs winsize on parent's master_fd
- With CTTY fix, kernel now delivers SIGWINCH to child's foreground process group
- No additional parent-side work needed
- Handler chaining preserves any previous SIGWINCH handlers

**Alternatives Rejected:**
- **Remove SIGWINCH handler** — rejected because parent must update master_fd winsize
- **Send SIGWINCH directly to child** — rejected because kernel does this automatically when child has CTTY

---

## D-03: No Refactor Agenda Required

**Decision:** This is a minimal bug fix, not a structural change.

**Reasoning:**
- The fix is a single-line replacement in one function
- No new abstractions needed
- No cross-cutting changes
- No test infrastructure changes
- Adjacent code (raw mode, select loop, terminal restoration) is correct

**Implications:**
- Implementation is low-risk
- Review can focus narrowly on the fix itself
- No preparatory refactoring needed

---

## D-04: Smoke Test Classification Protocol

**Decision:** Every smoke test must run baseline (raw harness) before Meridian test to classify failures.

**Reasoning:**
- Harness TUIs have their own bugs
- Meridian shouldn't be blamed for upstream issues
- Meridian shouldn't hide behind "upstream bug" without evidence
- Classification requires empirical comparison, not assumption

**Categories:**
- `MERIDIAN-CAUSED` — fails under Meridian, passes under raw harness
- `UPSTREAM-ONLY` — fails identically under both
- `PASS` — passes under both

---

## D-05: Issue is Signal Delivery, Not Winsize Propagation

**Decision:** Frame the root cause as missing signal delivery, not missing winsize propagation.

**Reasoning:**
- Review probes confirmed: slave PTY dimensions ARE updated when master receives TIOCSWINSZ
- What's missing is SIGWINCH delivery to the child's foreground process group
- Without CTTY, there is no foreground process group to notify
- This affects both SIGWINCH and terminal-generated SIGINT

**Implications:**
- Parent-side `_sync_pty_winsize()` and `_install_winsize_forwarding()` are correct
- Fix is entirely child-side: acquire CTTY so signals can be delivered

---

## D-06: Spec Uses Behavioral Language, Architecture Specifies Mechanism

**Decision:** Revised EARS statements to describe observable behavior, not implementation mechanism.

**Reasoning:**
- Initial spec said "make the child a session leader" — that's mechanism, not behavior
- Revised to "deliver the corresponding signal to the child" — observable outcome
- Architecture documents how `os.login_tty()` achieves the behavioral requirement

**Example change:**
- Before: "the system shall make the child a session leader with the slave PTY as its controlling terminal"
- After: "the system shall deliver the corresponding signal to the child harness process"
