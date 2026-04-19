# PTY Scroll Regression Investigation

## User Intent

Investigate a newly observed Meridian-only interactive terminal regression: scroll works in raw `claude` and raw `codex`, but does not work when those harnesses are launched through `meridian`.

## Problem Statement

After the PTY controlling-terminal fix (`os.login_tty(slave_fd)`), interactive resize behavior improved, but scroll behavior is now wrong specifically under Meridian-wrapped Claude and Codex.

The user reports:

- raw `claude`: scroll works
- raw `codex`: scroll works
- `meridian --harness claude`: scroll does not work
- `meridian --harness codex`: scroll does not work

This suggests a Meridian PTY bridge or terminal-mode regression rather than an upstream harness bug.

## Scope

In scope:

- primary interactive PTY bridge in `src/meridian/lib/launch/process.py`
- parent raw-mode handling
- PTY initialization and child terminal/session setup
- differences between raw harness launch and Meridian-wrapped launch that could affect scrollback, mouse-wheel behavior, alternate-screen behavior, or terminal input handling
- evidence gathering for both Claude and Codex

Out of scope:

- command-line argument passthrough after `--`
- Windows-specific PTY behavior
- fixing the issue in this phase; this work is investigation and diagnosis only

## Success Criteria

The investigation should:

1. Confirm whether Claude and Codex share the same Meridian-side root cause
2. Identify the most likely PTY/terminal-behavior mechanism behind broken scroll under Meridian
3. Distinguish scrollback loss, mouse-wheel capture, alternate-screen behavior, and raw-mode side effects instead of collapsing them into one label
4. Point to the likely Meridian code surface responsible
5. Recommend whether the next step should be a design round, a scoped implementation, or additional probes
