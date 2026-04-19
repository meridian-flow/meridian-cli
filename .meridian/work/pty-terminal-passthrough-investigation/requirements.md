# PTY Terminal Passthrough Investigation

## User Intent

Investigate and design a fix for Meridian's interactive CLI terminal passthrough path when launching a primary harness via `meridian`, with emphasis on terminal-resize behavior corrupting the display.

This is about CLI terminal passthrough behavior, not command-line argument passthrough.

## Problem Statement

When the user launches `meridian` interactively and resizes the terminal window, the display can become badly corrupted or fail to redraw correctly.

Local investigation suggests the issue is in the PTY passthrough layer under `src/meridian/lib/launch/process.py`, especially around PTY session setup, controlling-terminal ownership, and resize notification delivery.

## Scope

In scope:

- Primary interactive launch path used by plain `meridian`
- PTY open/fork/session/control-terminal setup
- Window-size propagation and `SIGWINCH`
- Byte passthrough between parent terminal and child PTY
- Raw-mode handling and terminal restoration
- Interrupt/EOF/cleanup behavior adjacent to the same passthrough layer
- Smoke testing that distinguishes Meridian bugs from upstream harness UI bugs

Out of scope:

- Generic command-line argument passthrough after `--`
- Harness-internal TUI bugs that reproduce the same way when running the raw harness outside Meridian
- Windows-specific PTY behavior unless design work finds the fix would impact Windows fallback behavior

## Constraints

- Prefer the smallest change that restores normal terminal semantics
- Keep Meridian a thin coordination layer; do not add a large custom terminal subsystem
- Preserve current non-PTY fallback behavior
- Preserve Windows behavior unless a deliberate cross-platform design change is justified
- Design should identify whether `login_tty`, `TIOCSCTTY`, `forkpty`, or another narrow PTY correction is the right fix

## Success Criteria

The design package should:

1. Describe the current PTY passthrough path and name the broken invariant(s)
2. Identify any adjacent PTY/terminal risks beyond resize corruption
3. Propose the minimal correct PTY/session/control-terminal fix
4. Define a smoke matrix that exercises resize, active output, Ctrl-C, EOF, raw-mode restoration, child exit, and cross-harness parity
5. Clearly separate Meridian-caused failures from upstream harness-only failures

Implementation will be considered complete only when:

- Terminal resize no longer corrupts interactive Meridian display due to Meridian's PTY passthrough layer
- Relevant smoke coverage exists for this terminal behavior surface
- Remaining failures, if any, are classified with evidence as upstream-only or intentionally deferred
