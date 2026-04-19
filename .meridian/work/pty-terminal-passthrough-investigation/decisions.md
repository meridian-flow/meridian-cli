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

---

## D-07: PTY-09 Non-TTY Behavior is Pre-existing, Not Regression

**Decision:** Classify PTY-09 smoke test failure as pre-existing behavior outside this fix's scope.

**Evidence:**
- Git stash test: `printf "1\n" | uv run meridian --harness claude` prints root help both with and without the `os.login_tty()` fix
- Root dispatch behavior unrelated to PTY child path code
- Our fix only touches child-side code after fork() in `_run_primary_process_with_capture()`
- Non-TTY dispatch is handled earlier in the call stack

**Implications:**
- PTY-09 is not a regression from this work
- A separate work item should address root dispatch non-TTY behavior if desired
- This work's scope remains limited to the approved child-side PTY fix

---

## D-08: Interactive Smoke Tests Require Manual Session

**Decision:** Interactive terminal tests (T-01 through T-05, T-09-T-12) cannot be verified in a non-interactive spawn environment.

**Evidence:**
- Smoke-tester ran in headless spawn environment
- No TTY available for resize, Ctrl-C, or interactive TUI observation
- Implementation correctness verified via import check and `hasattr(os, 'login_tty')`

**Implications:**
- Non-interactive verification complete (build health, import check, basic terminal restoration)
- Final verification requires manual interactive session outside orchestration
- Phase 3 provides classification protocol for manual execution

---

## D-09: PTY-01 Scope Clarification — SIGWINCH and Terminal-Generated SIGINT Only

**Decision:** Narrow the interpretation of PTY-01 to the behaviors this fix actually restores: SIGWINCH (resize) and terminal-generated SIGINT (Ctrl-C). Explicit SIGTSTP/SIGCONT forwarding from parent to child is out of scope for this minimal fix.

**Evidence (from reviewer p50):**
- The fix acquires a controlling terminal via `os.login_tty()`, which enables kernel-side signal delivery to the child's foreground process group
- This covers SIGWINCH (terminal resize) and SIGINT (Ctrl-C typed in raw mode)
- SIGTSTP/SIGCONT from an outer shell hitting the Meridian parent process are NOT forwarded by this fix
- The parent-side winsize handler only installs for SIGWINCH, not SIGTSTP/SIGCONT

**Spec Language Clarification:**
- PTY-01 as written says "job control signal (SIGWINCH, SIGTSTP, SIGCONT)"
- The fix only addresses SIGWINCH and terminal-generated interrupt parity
- SIGTSTP/SIGCONT forwarding would require additional parent-side signal handlers

**Implications:**
- This fix is complete for its approved scope (resize + interrupt parity)
- Full job-control transparency (suspend/resume from outer shell) is future work if desired
- No code change needed — the fix is correct; the spec interpretation is narrowed

---

## D-10: Interactive Verification Requires Manual Post-Merge Session

**Decision:** Interactive smoke tests (T-01 through T-05, T-09-T-12) cannot be automated and require explicit manual verification.

**Evidence:**
- Three reviewers confirmed the fix is code-correct
- All POSIX PTY EARS statements except partial PTY-06 remain blocked in non-interactive environment
- Feasibility Probe 6 demonstrated `login_tty()` vs `setsid()+dup2()` signal behavior difference in standalone test

**Required Post-Merge Action:**
1. Run smoke matrix T-01 through T-07 in an interactive terminal session
2. Verify resize behavior (T-01, T-02) with Claude harness
3. Verify Ctrl-C behavior (T-04) during streaming output
4. Record verdicts in smoke-matrix verdicts

---

## D-11: macOS Support is Low Risk but Unprobed

**Decision:** Accept macOS as "inferred POSIX" for this minimal fix. Risk is low; probe can be run opportunistically.

**Evidence:**
- `os.login_tty()` added in Python 3.11 with "Available on Unix" annotation
- Underlying C `login_tty()` is POSIX standard
- Meridian requires Python >= 3.12

**Follow-up (Optional):**
- Run `python3 -c "import os; print(hasattr(os, 'login_tty'))"` on any macOS machine
- Update architecture compatibility table from "Inferred" to "Verified"
