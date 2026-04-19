# Planning Request: PTY Terminal Passthrough Fix

## Context

You are planning an implementation for the PTY terminal passthrough fix in Meridian. The design is approved and complete. Your task is to produce an executable implementation plan.

## Design Package Summary

**Problem:** When `meridian` launches interactively, terminal resize corrupts the display. Root cause: child process calls `os.setsid()` but never acquires a controlling terminal, so `SIGWINCH` is never delivered.

**Fix:** Replace manual `setsid()` + `dup2()` sequence with `os.login_tty(slave_fd)` in `src/meridian/lib/launch/process.py` (lines 203-217).

**EARS Statements to verify:**
- PTY-01: Terminal Signal Delivery (SIGWINCH, SIGTSTP, SIGCONT, Ctrl-C)
- PTY-02: Initial Window Size
- PTY-03: Window Resize Notification
- PTY-04: Interrupt Parity (Ctrl-C)
- PTY-05: Bidirectional Byte Passthrough
- PTY-06: Raw Mode Entry and Restoration
- PTY-07: EOF Handling
- PTY-08: Child Exit Detection
- PTY-09: Non-TTY Fallback (POSIX)
- PTY-10: Windows Fallback

## Key Constraints

1. **Minimal change:** Single-line replacement, no refactoring
2. **Parent-side code is correct:** Only child fork path changes
3. **Smoke matrix correction:** Examples using `-H` should use `--harness`
4. **Classification protocol:** Every smoke test must run baseline (raw harness) before Meridian test to distinguish Meridian-caused vs upstream-only failures

## Implementation Scope

1. **Code change:** Replace lines 206-211 in process.py with `os.login_tty(slave_fd)`
2. **Verification:** Execute smoke matrix tests (T-01 through T-12), classifying results
3. **Build verification:** pyright + ruff must pass

## Design Artifacts (read from disk)

- `$MERIDIAN_WORK_DIR/requirements.md` — user intent and scope
- `$MERIDIAN_WORK_DIR/design/spec/pty-passthrough.md` — EARS statements
- `$MERIDIAN_WORK_DIR/design/architecture/pty-passthrough.md` — technical approach
- `$MERIDIAN_WORK_DIR/design/feasibility.md` — validated assumptions
- `$MERIDIAN_WORK_DIR/design/smoke-matrix.md` — verification matrix
- `$MERIDIAN_WORK_DIR/decisions.md` — design decisions
- `$MERIDIAN_WORK_DIR/plan/pre-planning-notes.md` — runtime observations

## Source File

- `src/meridian/lib/launch/process.py` — the file to modify

## Output

Produce:
1. `plan/overview.md` — phase structure, parallelism, staffing
2. `plan/phase-N-<slug>.md` — per-phase blueprints with scope, EARS claims, exit criteria
3. `plan/leaf-ownership.md` — one row per EARS ID with exclusive phase ownership
4. `plan/status.md` — initial phase lifecycle status (all "not-started")

Apply the smoke-matrix correction (`--harness` not `-H`) in the relevant phase blueprint.
