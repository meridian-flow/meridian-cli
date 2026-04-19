# PTY Scroll Regression Investigation Report

## Summary

The likely Meridian-side cause is not argv passthrough and not a scroll-specific byte mangling bug. The likely cause is that Meridian's primary interactive launch path inserts a PTY-owning relay between the real terminal and the harness TUI, which changes terminal semantics in a way that behaves more like a multiplexer than a direct harness launch.

This is centered in [`src/meridian/lib/launch/process.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/process.py:105), especially:

- `_run_primary_process_with_capture()`
- `_copy_primary_pty_output()`
- the `pty.openpty()` + `fork()` + `login_tty()` child launch path

## What I Checked

- Read the work item requirements: [`requirements.md`](/home/jimyao/gitrepos/meridian-cli/.meridian/work/pty-scroll-regression-investigation/requirements.md:1)
- Read the existing PTY design/spec artifacts:
  - [`design/spec/pty-passthrough.md`](/home/jimyao/gitrepos/meridian-cli/.meridian/work/pty-terminal-passthrough-investigation/design/spec/pty-passthrough.md:1)
  - [`design/architecture/pty-passthrough.md`](/home/jimyao/gitrepos/meridian-cli/.meridian/work/pty-terminal-passthrough-investigation/design/architecture/pty-passthrough.md:1)
- Inspected the current PTY bridge code in [`process.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/process.py:105)
- Checked recent PTY history:
  - `4fbce6f` on 2026-04-16: `pty.fork()` replaced with `pty.openpty()` + manual fork for initial winsize correctness
  - `c42736a` on 2026-04-18: manual child setup replaced with `os.login_tty(slave_fd)` for controlling-terminal acquisition
- Checked current tests in [`tests/test_launch_process.py`](/home/jimyao/gitrepos/meridian-cli/tests/test_launch_process.py:31)
- Ran short terminal transcript probes with `script` for direct `codex` and `meridian --harness codex`
- Spawned [`p72`](</home/jimyao/.meridian/projects/71e6b90f-b8c2-4dd6-b608-4dd8f7bf37d5/spawns/p72/report.md>) to mine PTY history and prior design artifacts

## Findings

### 1. Meridian's bridge is byte-relay code, not scroll-aware terminal mediation

The parent-side bridge in [`_copy_primary_pty_output()`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/process.py:105) does three things:

- sets the real parent stdin to raw mode
- copies bytes from parent stdin to the PTY master
- copies bytes from PTY master to parent stdout while logging them

There is no Meridian code here that interprets, rewrites, or manages:

- alternate-screen entry/exit
- mouse reporting modes
- scrollback integration
- cursor-position response handling beyond transparent byte passthrough

That makes a dedicated Meridian "scroll logic bug" unlikely. The more plausible issue is the terminal topology Meridian creates.

### 2. Meridian changes the terminal topology from direct-TTY to nested PTY relay

Direct `codex` and direct `claude` talk to the user's real terminal. Under Meridian, the harness talks to a PTY slave created by Meridian, while Meridian itself remains attached to the real terminal and relays bytes between the two.

That means Meridian is not just "launching the same process with extra args". It is acting like a lightweight terminal multiplexer/relay. Scroll behavior can differ even if byte passthrough is correct.

### 3. The 2026-04-18 `login_tty()` change is probably not the primary bug

[`c42736a`](2026-04-18) changed child setup from manual `setsid()`/`dup2()` to `os.login_tty(slave_fd)` in [`_run_primary_process_with_capture()`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/process.py:199). That matches the earlier PTY design work: its purpose was to restore controlling-terminal semantics so SIGWINCH and SIGINT reach the child correctly.

That explains why resize and Ctrl-C behavior improved. It does not introduce any explicit scrollback, mouse, or alternate-screen handling. I do not see evidence that `login_tty()` itself is the scroll regression.

What it likely did do is make the harness's PTY environment more "real", which can encourage full TUI behavior on the child PTY. If the harness then relies on alternate-screen or mouse behavior that differs under nested PTY relays, Meridian now exposes that difference more reliably.

### 4. The likely mechanism is alternate-screen / multiplexer-style semantics, not parent raw mode

The strongest evidence here is upstream `codex` behavior. `codex --help` documents:

> `--no-alt-screen` disables alternate screen mode and preserves terminal scrollback history, and is useful in terminal multiplexers like Zellij that disable scrollback in alternate screen buffers.

That does not prove Codex is the bug source. It does show the exact symptom class: scrollback behavior changes when the TUI is not attached directly to the user's terminal. Meridian's PTY bridge creates that kind of mediated environment.

I also ran short `script` transcript probes against direct `codex` and `meridian --harness codex`. Both emitted the same early terminal control setup (`?2004h`, `?1004h`, `6n`) and I did not find evidence that Meridian rewrites those startup bytes. That again points away from a byte-corruption bug and toward a higher-level terminal-semantics mismatch.

Parent raw mode alone is less likely to be the root cause:

- a TUI directly attached to a terminal typically also uses raw or cbreak-style input handling
- Meridian's raw mode is limited to the real parent stdin side
- the observed regression is shared across harnesses, while the parent raw-mode code is generic and byte-transparent

### 5. The likely Meridian-owned code surface is still `process.py`

Even if the symptom is "alternate screen" or "mouse-wheel capture", the Meridian-owned surface is still the PTY relay implementation in [`src/meridian/lib/launch/process.py`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/process.py:105), because that is what changes the terminal from direct attachment to mediated attachment.

The most relevant surfaces are:

- [`_copy_primary_pty_output()`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/process.py:105): raw parent mode + transparent byte relay
- [`_run_primary_process_with_capture()`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/process.py:160): PTY creation, child fork, `login_tty()`
- [`_install_winsize_forwarding()`](/home/jimyao/gitrepos/meridian-cli/src/meridian/lib/launch/process.py:269): resize propagation, relevant only as adjacent PTY transport logic

## Assessment Against Candidate Causes

- Parent raw mode: possible contributor, but not the strongest explanation
- PTY slave initialization: `login_tty()` is important for correctness, but not the likeliest scroll-specific defect
- Alternate-screen behavior: likely part of the user-visible symptom
- Mouse reporting: plausible secondary symptom, but I found no Meridian code that explicitly enables or transforms it
- Another terminal-semantics difference introduced by Meridian: most likely

The best description is:

> Meridian's nested PTY relay changes the harness from a direct-terminal app into a multiplexer-style child terminal. Scrollback and wheel behavior then diverge, especially when the harness uses alternate-screen-style TUI behavior.

## Recommended Next Step

Do a scoped design/probe round, not an immediate patch.

Recommended probe:

1. Reproduce with a minimal full-screen or alternate-screen terminal program under raw direct launch vs Meridian PTY relay, without involving Codex/Claude-specific app logic.
2. Capture whether the broken behavior is:
   - outer terminal scrollback loss
   - mouse-wheel events being forwarded but ignored
   - mouse-wheel events not being generated by the outer terminal in the nested topology
   - alternate-screen persistence/mediation mismatch
3. Decide whether Meridian should:
   - stay a dumb PTY relay and document the limitation
   - add a supported "inline/no-alt-screen" policy for harnesses when running under Meridian
   - implement richer terminal mediation comparable to a multiplexer

I do **not** recommend starting by changing argv passthrough. The problem appears to be the terminal bridge semantics themselves.
