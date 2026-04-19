# Phase 1: Child PTY `login_tty()` Fix

## Scope and Boundaries

Implement the approved minimal PTY child-path correction in `src/meridian/lib/launch/process.py`.

In scope:

- replace the child-side `os.setsid()` + `os.dup2()` + conditional `os.close()` sequence with `os.login_tty(slave_fd)`
- preserve `os.close(master_fd)`, `os.chdir(cwd)`, `os.execvpe(...)`, and the existing child exit-code behavior
- preserve the existing Windows and non-TTY bypass guards

Out of scope:

- any parent-side PTY logic changes (`_sync_pty_winsize()`, `_install_winsize_forwarding()`, `_copy_primary_pty_output()`)
- switching to `forkpty()`
- new abstractions, refactors, or smoke-matrix document edits

## Touched Files and Modules

- `src/meridian/lib/launch/process.py`

## Claimed EARS Statement IDs

- none

This phase changes the implementation mechanism that later evidence will verify. Behavioral ownership stays in Phase 3 so the EARS ledger remains exclusive.

## Touched Refactor IDs

- none

## Dependencies

- none

## Tester Lanes

- none in-phase
- follow-on verification is owned by Phase 2 (`@verifier`) and Phase 3 (`@smoke-tester`)

## Execution Notes

- Keep the change minimal; do not widen the diff if the approved design does not require it.
- Treat the design's child-side diagnosis as settled: the bug is missing controlling-terminal acquisition, not missing winsize propagation.
- If the patch appears to require edits outside `process.py`, stop and escalate instead of inventing a broader refactor.

## Exit Criteria

- `process.py` uses `os.login_tty(slave_fd)` in the PTY child path
- no parent-side PTY behavior is changed
- the diff remains limited to the approved surface in `process.py`
