# PTY Terminal Passthrough Specification

## Overview

This specification defines the behavioral contract for Meridian's primary interactive terminal passthrough when launching harnesses via plain `meridian`. The PTY layer must present correct terminal semantics to child harness processes.

## Scope

- **In scope:** Primary interactive launch path (`run_harness_process`), PTY session setup, controlling terminal ownership, resize notification, byte passthrough, interrupt/EOF, cleanup
- **Out of scope:** Background spawn paths (streaming_runner), Windows PTY emulation, harness-internal TUI bugs

---

## EARS Statements

### PTY-01: Terminal Signal Delivery

**When** the parent terminal receives a job control signal (SIGWINCH, SIGTSTP, SIGCONT) or the user types an interrupt character (Ctrl-C),
**the system shall** deliver the corresponding signal to the child harness process.

**Rationale:** TUI applications rely on terminal-generated signals for resize notification, suspend/resume, and interrupt handling. Without correct signal delivery, resize corrupts the display and Ctrl-C may not interrupt the harness.

### PTY-02: Initial Window Size

**When** the child harness process starts,
**the child shall** be able to query the correct terminal dimensions matching the parent terminal's current size.

**Rationale:** Child processes query terminal size at startup. Incorrect dimensions cause TUI layout corruption.

### PTY-03: Window Resize Notification

**When** the parent terminal is resized,
**the child harness process shall** be notified and be able to query the updated terminal dimensions.

**Rationale:** TUI applications handle SIGWINCH by querying new dimensions and redrawing. The child must both receive notification and see correct dimensions.

### PTY-04: Interrupt Parity

**When** the user types Ctrl-C in the parent terminal,
**the child harness process shall** receive the interrupt and handle it the same way as when running without Meridian.

**Rationale:** Interrupt behavior must be transparent. Users expect Ctrl-C to stop or interrupt the harness regardless of whether Meridian wraps it.

### PTY-05: Bidirectional Byte Passthrough

**While** the child process is running,
**the system shall** copy bytes from parent stdin to PTY master and from PTY master to parent stdout without modification.

**Rationale:** Harness TUIs output raw terminal escape sequences. Any modification corrupts display.

### PTY-06: Raw Mode Entry and Restoration

**When** the passthrough loop starts,
**the system shall** place the parent terminal in raw mode.

**When** the passthrough loop exits (normally or via exception),
**the system shall** restore the parent terminal to its original mode.

**Rationale:** Raw mode prevents line buffering and signal generation from interfering with passthrough. Restoration prevents leaving the user's terminal in a broken state.

### PTY-07: EOF Handling

**When** the parent terminal signals EOF (stdin closes),
**the system shall** stop reading from stdin and continue draining PTY master output until the child exits.

**Rationale:** EOF from parent indicates user closed input channel. Child may still produce output.

### PTY-08: Child Exit Detection

**When** the child process exits,
**the system shall** drain remaining PTY master output, close the master fd, restore terminal mode, and return the child's exit code.

**Rationale:** Correct cleanup prevents orphaned fds and corrupted terminal state.

### PTY-09: Non-TTY Fallback

**Where** stdin or stdout is not a TTY,
**the system shall** bypass PTY wrapping and launch the harness via direct subprocess with inherited stdio.

**Rationale:** PTY passthrough is only meaningful for interactive terminals. Non-interactive contexts (pipes, cron) should not fail due to PTY setup.

### PTY-10: Windows Fallback

**Where** the platform is Windows,
**the system shall** bypass PTY wrapping and use direct subprocess launch.

**Rationale:** POSIX PTY APIs are not available on Windows. ConPTY is out of scope.

---

## Cross-Harness Parity

All EARS statements apply uniformly to every registered harness (claude, codex, opencode). The PTY layer is harness-agnostic; harness-specific TUI behavior is out of scope.

## Distinguishing Meridian Bugs from Upstream Bugs

A failure is **Meridian-caused** if it reproduces under `meridian` but not when running the raw harness command directly. A failure is **upstream-only** if it reproduces identically with or without Meridian.

The smoke matrix must include baseline runs without Meridian to establish this distinction.
