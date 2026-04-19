# PTY Audit: Windows Port Research

## Verdict

The PTY path is **load-bearing**, but only for **foreground primary launches**. It is not the general spawn runner, and it is not where harness-specific session logic lives.

Current state:

- The PTY code is concentrated in `src/meridian/lib/launch/process.py`.
- The code **does not use `pty.fork()` anymore**. Commit `4fbce6f` replaced it with `pty.openpty()` + manual `os.fork()` so the child sees the correct viewport size before `exec`.
- There is **no terminal/PTY abstraction layer** yet. `run_harness_process()` owns launch policy and directly calls raw Unix PTY/syscall machinery.

The PTY exists for four concrete reasons:

1. Make the harness process see a real TTY for primary interactive mode.
2. Preserve TUI-style interaction by forwarding stdin/stdout over the PTY.
3. Mirror terminal output into `output.jsonl` for later report/session extraction.
4. Keep the PTY viewport synchronized with the parent terminal.

Session ID extraction is only **partially coupled** to the PTY path. The PTY transcript is one input to session observation, but the actual session-resolution contract lives in the harness adapter layer and already has non-PTY fallbacks.

## PTY-Related Code in `src/meridian/lib/launch/`

### Direct PTY/terminal machinery

- `src/meridian/lib/launch/process.py:3-14`
  - Imports raw Unix terminal/process APIs: `fcntl`, `pty`, `select`, `signal`, `struct`, `termios`, `tty`.
- `src/meridian/lib/launch/process.py:91-139`
  - `_copy_primary_pty_output()`:
    - switches parent stdin to raw mode
    - runs a `select.select()` loop over `master_fd` and `stdin_fd`
    - copies child output to both terminal and `output.jsonl`
    - forwards user input from stdin into the PTY
    - restores resize handler and tty state
- `src/meridian/lib/launch/process.py:142-215`
  - `_run_primary_process_with_capture()`:
    - falls back to plain `subprocess.Popen` when stdin/stdout are not TTYs
    - otherwise allocates a PTY, forks, wires the slave to fd `0/1/2`, and runs the child under that PTY
- `src/meridian/lib/launch/process.py:217-265`
  - `_read_winsize()`, `_sync_pty_winsize()`, `_install_winsize_forwarding()`
  - handles initial viewport sync and future `SIGWINCH` forwarding

### Primary-launch policy that depends on the PTY machinery

- `src/meridian/lib/launch/process.py:268-539`
  - `run_harness_process()` is the only caller.
  - It creates the primary spawn row, launches the child, persists `output.jsonl`, finalizes spawn state, then calls adapter-owned session observation.

### Tests pinning current behavior

- `tests/test_launch_process.py:31-89`
  - Tests immediate winsize sync and `SIGWINCH` handler restore behavior.

## What the PTY Is Used For

### 1. Harness `isatty()` / terminal detection

Yes. This is the primary reason.

- `build_launch_context()` marks primary launches as `interactive=True` in `src/meridian/lib/launch/context.py:655-670`.
- Harness projections use that flag to choose their primary interactive CLI form, for example Codex in `src/meridian/lib/harness/projections/project_codex_subprocess.py:177-204`.
- The PTY backend in `process.py` then makes stdin/stdout/stderr look like a real terminal to that interactive harness process by duping the PTY slave onto fds `0/1/2` (`src/meridian/lib/launch/process.py:178-189`).

Without the PTY, the primary harness would see pipes, not a terminal.

### 2. Session ID extraction from captured output

Secondary, not primary.

- The PTY path writes raw output to `output.jsonl` (`src/meridian/lib/launch/process.py:109-125`, `454-458`).
- Adapter session observation happens later via `observe_session_id()` in `src/meridian/lib/harness/adapter.py:216-241`, `343-388`.
- Artifact extraction is only one step in that contract:
  1. live connection session id
  2. artifact extraction
  3. primary-session detection from harness-owned session files/logs
  4. current known session id

The generic artifact extractor reads `output.jsonl` and tries JSON keys and optional text regexes (`src/meridian/lib/harness/common.py:444-484`).

Important nuance:

- Codex and OpenCode explicitly support text-pattern extraction from raw terminal transcripts:
  - `src/meridian/lib/harness/codex.py:273-285`
  - `src/meridian/lib/harness/opencode.py:149-159`
- But all three harnesses also support filesystem/log-based fallback detection:
  - Codex: `src/meridian/lib/harness/codex.py:181-207`, `380-388`
  - Claude: `src/meridian/lib/harness/claude.py:128-147`, `412-420`
  - OpenCode: `src/meridian/lib/harness/opencode.py:65-109`, `276-288`

So the PTY transcript helps session extraction, but it is not the sole owner of session identity.

### 3. TUI rendering / interactive UX

Yes. This is load-bearing.

The primary-launch path exists to run the harness in its native interactive mode. The PTY loop preserves that by:

- giving the child a terminal
- forwarding keystrokes into the PTY
- streaming rendered output back to the parent terminal in real time

The `4fbce6f` commit message makes this explicit: wrong PTY initialization caused incorrect viewport size for the child TUI at startup.

### 4. Window resize forwarding

Yes. Explicitly and intentionally.

- Initial size copy happens before `fork`/`exec`: `src/meridian/lib/launch/process.py:173-176`
- Future resizes are forwarded via `SIGWINCH`: `src/meridian/lib/launch/process.py:250-265`
- Tests pin both immediate sync and handler restoration: `tests/test_launch_process.py:31-89`

This behavior is load-bearing for curses/full-screen/TUI-style harness UIs.

## Unix-Specific APIs in the Current PTY Path

All of the following are Unix/POSIX-specific or Unix-shaped enough that they need a Windows replacement layer:

| API | Where | Purpose | Windows port note |
| --- | --- | --- | --- |
| `pty.openpty()` | `process.py:175` | allocate master/slave PTY pair | replace with ConPTY/winpty allocation |
| `os.fork()` | `process.py:178` | split parent/child after PTY creation | no direct Windows equivalent |
| `os.setsid()` | `process.py:182` | make child a session leader | no direct Windows equivalent |
| `os.dup2()` | `process.py:183-185` | attach PTY slave to stdin/stdout/stderr | Windows needs ConPTY pipe attachment, not fd duping |
| `os.execvpe()` | `process.py:189` | exec harness in-place | Windows uses process creation APIs |
| `os.waitpid()` / `os.waitstatus_to_exitcode()` | `process.py:138-139` | wait/reap child | different Windows process semantics |
| `termios.tcgetattr()` / `tcsetattr()` | `process.py:106`, `135` | save/restore parent tty mode | Windows console mode APIs instead |
| `tty.setraw()` | `process.py:107` | parent stdin raw mode for byte-forwarding | Windows console mode equivalent needed |
| `select.select()` on fds | `process.py:114` | mux stdin + PTY master | Windows `select` does not work for console handles |
| `os.read()` / `os.write()` on tty fds | `process.py:118`, `125`, `128`, `132` | byte shuttling | Windows handle/pipe I/O semantics differ |
| `fcntl.ioctl(..., TIOCGWINSZ)` | `process.py:221` | read parent terminal size | replace with Windows console/ConPTY size query |
| `fcntl.ioctl(..., TIOCSWINSZ)` | `process.py:233` | push size to child PTY | replace with ConPTY resize call |
| `signal.SIGWINCH` | `process.py:254-263` | resize notification | no portable Windows equivalent |
| `signal.SIGTERM` / `SIGINT` in this file | `process.py:169`, `202` | cleanup/interrupt fallback | partly portable, but semantics differ |

Related but separate portability surface:

- `src/meridian/lib/launch/signals.py` uses Unix process-group signaling (`os.getpgid`, `os.killpg`).
- That is adjacent launch portability work, but it is not part of the PTY transport itself.

## Is There an Existing Abstraction Layer?

### Terminal transport abstraction

No.

`src/meridian/lib/launch/process.py` directly mixes:

- spawn/session bookkeeping
- PTY allocation
- fork/exec
- stdin raw-mode handling
- resize forwarding
- transcript capture
- exit-code collection

There is no `TerminalSession`, `InteractiveTransport`, or platform adapter boundary around that mechanism.

### What is already abstracted

Session observation is already abstracted correctly at the harness layer:

- `observe_session_id()` in `src/meridian/lib/harness/adapter.py:216-241`, `343-388`
- artifact extraction in `src/meridian/lib/harness/common.py:444-484`
- harness-owned primary-session detection in each adapter

That boundary should stay separate from any PTY/ConPTY porting work.

## Could `ptyprocess` / `pywinpty` Replace the Hand-Rolled Code?

## `ptyprocess` on Unix

Probably yes, for the low-level PTY mechanics.

Why it is a reasonable fit:

- The project exists specifically to run subprocesses inside a PTY and interact through it.
- Its docs expose exactly the primitives Meridian needs: spawn, read/write, `isatty()`, `getwinsize()`, `setwinsize()`, `wait()`.
- It already owns the ugly Unix PTY details Meridian is hand-rolling now.

Sources:

- `ptyprocess` GitHub README: <https://github.com/pexpect/ptyprocess>
- `ptyprocess` API/docs: <https://ptyprocess.readthedocs.io/en/stable/api.html>

Caveats:

- It is still Unix-oriented, not cross-platform.
- Meridian would still need its own policy wrapper for:
  - output mirroring into `output.jsonl`
  - `on_child_started` callback integration
  - spawn-store/session-store updates
  - KeyboardInterrupt policy
  - cleanup/finalization
- `ptyprocess` latest GitHub release is old (`0.7.0` from 2020), so this is a pragmatic dependency, not a fast-moving one.

My read: `ptyprocess` could delete most of the Unix syscall glue in `process.py`, but not the launch policy around it.

## `pywinpty` on Windows

Probably yes, for the Windows terminal mechanism.

Why it is a reasonable fit:

- It is explicitly a Windows pseudoterminal wrapper.
- It supports native ConPTY and winpty fallback.
- It exposes high-level `PtyProcess.spawn(...)` and lower-level PTY APIs with `read`, `write`, `set_size`, and `isalive`.

Sources:

- `pywinpty` GitHub README: <https://github.com/andfoy/pywinpty>
- `pywinpty` v3.0.0 release notes: <https://github.com/andfoy/pywinpty/releases/tag/v3.0.0>

Caveats:

- It does not remove the need for a Meridian-owned abstraction boundary.
- Its API shape is not identical to `ptyprocess`.
- Windows console control/interrupt semantics still need Meridian policy decisions.

My read: `pywinpty` is a credible backend for a Windows interactive transport.

## Combined evaluation

Using `ptyprocess` for Unix and `pywinpty` for Windows is plausible, but only if Meridian introduces its own tiny internal transport interface.

Without that internal boundary, replacing raw syscalls with two different libraries just moves the platform split around.

## What the Abstraction Boundary Should Look Like

The right split is:

### Keep in `run_harness_process()` / launch policy

- primary spawn row creation
- work/session attachment
- log-dir selection
- child-start callback -> `mark_spawn_running()`
- artifact persistence to store
- finalization and exit-code mapping
- post-run `observe_session_id()`

### Move behind a new terminal transport boundary

- allocate interactive terminal backend
- launch child attached to terminal
- shuttle stdin -> child
- shuttle child output -> stdout + transcript file
- sync initial viewport
- propagate later resize events
- restore parent terminal state on exit

Possible shape:

```python
class InteractiveTerminalTransport(Protocol):
    def run(
        self,
        *,
        command: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        output_log_path: Path,
        on_child_started: Callable[[int], None] | None,
    ) -> TerminalRunResult: ...
```

Where `TerminalRunResult` carries at least:

- `exit_code`
- `child_pid`

Suggested implementations:

- `PosixInteractiveTransport`
  - current manual code, or `ptyprocess`-backed
- `WindowsInteractiveTransport`
  - `pywinpty` / ConPTY-backed
- `PipeFallbackTransport`
  - current `subprocess.Popen` path when stdin/stdout are not attached to a terminal

Why this is the correct boundary:

- `interactive` is already launcher policy, not harness-specific mechanism.
- session extraction is already adapter-owned and should stay out of the terminal driver.
- the portability problem is specifically "how do we host an interactive terminal child", not "how do harnesses build argv".

## Load-Bearing Edge Cases the Current Code Handles

These are the behaviors a Windows port must preserve:

### Initial viewport size before exec

Load-bearing.

- `process.py:173-176`
- Commit `4fbce6f` exists because syncing size after child startup was too late.

### Live resize forwarding

Load-bearing.

- `process.py:250-265`
- `tests/test_launch_process.py:51-89`

### Parent stdin raw mode + restoration

Load-bearing.

- `process.py:105-107`, `133-136`

This is what makes byte-for-byte interactive forwarding work. It also changes Ctrl-C behavior: in PTY mode, Ctrl-C is sent through the terminal path to the child instead of being handled solely as a parent-side Python `KeyboardInterrupt`.

### Real-time dual-write of child output

Load-bearing.

- `process.py:123-125`

The current code does not just capture output. It mirrors it live to the user terminal and persists it for later extraction.

### Non-TTY fallback

Load-bearing.

- `process.py:150-171`

If stdin/stdout are not TTYs, Meridian does not try to fake interactivity. It falls back to plain `subprocess.Popen`.

### Callback failure cleanup

Handled today and should be preserved.

- PTY path: `process.py:197-205`
- pipe path: `process.py:157-164`

If `on_child_started` fails, Meridian tries to stop the child immediately rather than leaking it.

### Best-effort cleanup/restoration

Handled today and should be preserved.

- restore previous `SIGWINCH` handler
- restore tty attrs
- close master fd
- finalize spawn even if post-run observation fails

### Crash-only compatibility

Mostly preserved above the PTY layer.

`run_harness_process()` persists `output.jsonl`, updates spawn state, finalizes status, and then best-effort persists session identity. The Windows port should avoid moving those responsibilities into a platform driver.

## Incidental vs Load-Bearing

### Load-bearing

- child sees a TTY in primary interactive mode
- interactive I/O forwarding
- initial viewport sync before child starts
- live resize forwarding
- transcript capture for later extraction/debugging
- restoration of parent terminal state

### Incidental / replaceable

- raw `openpty` + `fork` + `dup2` implementation details
- raw `select.select()` loop implementation
- manual `ioctl(TIOCGWINSZ/TIOCSWINSZ)` calls
- direct `termios` / `tty.setraw()` handling

Those are mechanisms, not requirements.

## Recommendation

1. Do not port `process.py` line-for-line to Windows.
2. Extract a launcher-owned interactive transport boundary first.
3. Keep session extraction/observation outside that boundary.
4. Treat these as separate backends:
   - Unix interactive transport
   - Windows interactive transport
   - non-interactive pipe fallback
5. Evaluate `ptyprocess` as the Unix backend only if deleting the manual syscall code is worth the dependency.
6. Evaluate `pywinpty` as the Windows backend; it looks like the closest off-the-shelf fit for ConPTY-style behavior.
7. Add contract tests around:
   - child gets terminal semantics
   - initial size is correct at startup
   - resize propagation works
   - stdout is mirrored and captured
   - parent terminal state is restored

## Related Tracking

- Existing issue: `#24 Unexpected: top-level spawn termination misses Codex descendants in their own sessions`
  - related launch portability work, but distinct from the PTY transport problem
