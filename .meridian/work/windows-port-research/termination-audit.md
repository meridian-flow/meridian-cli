# Termination Audit: Unix Process Groups vs `psutil` Descendant Trees

Date: 2026-04-16

## Scope and current file map

The prompt names `src/meridian/lib/launch/runner.py` and `src/meridian/lib/launch/timeout.py`, but those source files do not exist in this checkout. `rg --files -g 'runner.py' -g 'timeout.py' src/meridian` returns no matches. The live code is split across:

- `src/meridian/lib/launch/signals.py`
- `src/meridian/lib/launch/runner_helpers.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/streaming/spawn_manager.py`
- `src/meridian/lib/harness/connections/{claude_ws.py,codex_ws.py,opencode_http.py}`
- `src/meridian/lib/launch/process.py`

That matters because the current `killpg` helper is not on the main streaming execution path anymore.

## Executive summary

1. The explicit process-group machinery lives in `signals.py` and `runner_helpers.py`, but in the current source tree it is effectively legacy code. `signal_process_group()` is only referenced from `signals.py` itself and `runner_helpers.py`; there are no production callsites of `SignalForwarder`, and `wait_for_process_exit()` / `terminate_process()` currently have no production callers.
2. The live managed-spawn path is the streaming path in `streaming_runner.py` plus `SpawnManager.stop_spawn()`. That path does **not** use `killpg`. It cancels through `session.connection.send_cancel()` and then calls `session.connection.stop()`, and each harness adapter currently only terminates the top-level harness subprocess with `process.terminate()` then `process.kill()`.
3. Replacing only `os.killpg(os.getpgid(pid), ...)` with `psutil.Process(pid).children(recursive=True)` in `signals.py` / `runner_helpers.py` would not fix the leak for the path that actually runs today. The per-harness connection cleanup methods also need to switch to tree termination.
4. `psutil` is already a project dependency (`pyproject.toml`, `uv.lock`) and is already used for cross-platform PID liveness in `src/meridian/lib/state/liveness.py`, so adding a launch-side tree-kill helper does not add a new dependency.
5. There is configuration drift today: `ExecutionBudget.kill_grace_secs` is persisted in `src/meridian/lib/launch/request.py:29-36` and filled in `src/meridian/lib/ops/spawn/prepare.py:171-193`, but there are no reads of `request.budget.kill_grace_secs` anywhere in the current source tree. The live streaming termination path therefore does not honor the request-level kill grace budget today.

## 1. `src/meridian/lib/launch/signals.py`

### What it currently does

`signals.py` contains two distinct concerns:

1. Process-group signaling helpers
2. Parent-signal coordination / exit-code mapping

Relevant code:

- `signal_process_group(process, signum)` in `src/meridian/lib/launch/signals.py:21-40`
  - early-returns if `process.returncode` is already set
  - reads `pid = process.pid`
  - resolves `pgid = os.getpgid(pid)`
  - sends the signal with `os.killpg(pgid, signum)`
  - treats `ProcessLookupError` as an expected race

- `signal_to_exit_code()` / `map_process_exit_code()` in `src/meridian/lib/launch/signals.py:50-82`
  - `SIGINT -> 130`
  - `SIGTERM -> 143`
  - negative subprocess return codes are mapped back through `signal.Signals(-raw_return_code)`

- `SignalForwarder` in `src/meridian/lib/launch/signals.py:85-116`
  - stores the last received signal
  - forwards the first signal via `signal_process_group(...)`
  - escalates to `SIGKILL` on the second forwarded signal

- `SignalCoordinator` in `src/meridian/lib/launch/signals.py:118-237`
  - installs process-global handlers for `SIGINT` and `SIGTERM`
  - fans signals out to registered `SignalForwarder` instances
  - supports `mask_sigterm()` to ignore `SIGTERM` in critical sections
  - when no forwarders are active, re-dispatches the prior/default handler and re-emits the signal to self with `os.kill(os.getpid(), signum)`

### What the signal-process-group machinery is, concretely

The machinery is:

- `signal_process_group(process, signum)`
- `SignalForwarder.forward_signal()`
- `SignalCoordinator.register_forwarder()/unregister_forwarder()`
- `SignalCoordinator._on_signal()`

The intended model is:

1. register a `SignalForwarder` around an active child process
2. intercept parent `SIGINT` / `SIGTERM`
3. forward those signals to the child process group
4. escalate to `SIGKILL` on repeated termination signals

### Important current-state finding

In this checkout, that forwarding stack is mostly dormant:

- `SignalForwarder(...)` is only referenced in `tests/exec/test_signals.py`
- `signal_process_group(...)` is only referenced in:
  - `src/meridian/lib/launch/signals.py`
  - `src/meridian/lib/launch/runner_helpers.py`

So the process-group helper still exists, but it is not the thing driving cancellation for streaming spawns today.

### What should change if adopting `psutil`

If the helper is kept, `signal_process_group()` should be replaced by a tree-oriented primitive, not a group-oriented primitive. Example rename:

- `signal_process_group(...)` -> `terminate_tree(...)` or `signal_process_tree(...)`

The coordinator / exit-code mapping logic can stay. The broken assumption is the target selection mechanism (`pgid`), not the exit-code semantics.

## 2. `src/meridian/lib/launch/runner_helpers.py`

### What it currently does

This module contains generic subprocess helpers. The termination-specific pieces are:

- `DEFAULT_KILL_GRACE_SECONDS = MeridianConfig().kill_grace_minutes * 60.0`
  - `src/meridian/lib/launch/runner_helpers.py:29`

- `wait_for_process_returncode(...)`
  - `src/meridian/lib/launch/runner_helpers.py:237-256`
  - busy-polls `process.returncode` until set
  - raises `SpawnTimeoutError` on timeout

- `terminate_process(process, grace_seconds=...)`
  - `src/meridian/lib/launch/runner_helpers.py:259-278`
  - current behavior:
    1. return immediately if process already exited
    2. `signal_process_group(process, signal.SIGTERM)`
    3. wait for process returncode for `grace_seconds`
    4. if still alive, `signal_process_group(process, signal.SIGKILL)`
    5. wait without timeout for final exit

- `wait_for_process_exit(process, timeout_seconds, kill_grace_seconds=...)`
  - `src/meridian/lib/launch/runner_helpers.py:280-295`
  - waits for normal completion
  - on timeout, calls `terminate_process(...)`
  - then re-raises `SpawnTimeoutError`

### Current usage

In the current tree:

- `terminate_process(...)` has no production callsites
- `wait_for_process_exit(...)` has no production callsites
- `SpawnTimeoutError` is defined here but the actual live timeout path is in `streaming_runner.py`

So this module still documents the old intended behavior, but it is not where managed spawns are being killed today.

### What a `psutil` conversion here would mean

If the classic helper path is retained, `terminate_process()` becomes the natural home for:

- snapshot descendants with `psutil.Process(process.pid).children(recursive=True)`
- send `terminate()` to descendants + parent
- wait `grace_seconds`
- then `kill()` remaining descendants + parent

But changing this helper alone is insufficient, because the active adapters bypass it.

## 3. `src/meridian/lib/launch/streaming_runner.py`

### How timeout handling works now

The live managed-spawn timeout logic is in `_run_streaming_attempt(...)`:

- `timeout_task = asyncio.create_task(asyncio.sleep(timeout_seconds))`
  - `src/meridian/lib/launch/streaming_runner.py:601-602`
- `_run_streaming_attempt()` waits on:
  - completion
  - parent signal
  - budget breach
  - timeout
  - report watchdog
  - terminal event
  - `src/meridian/lib/launch/streaming_runner.py:612-623`

On timeout:

- `timed_out = True`
- `await manager.stop_spawn(..., status="failed", exit_code=3, error="timeout")`
  - `src/meridian/lib/launch/streaming_runner.py:642-650`

On parent signal:

- if already completed, it waits briefly for a late terminal event
- otherwise it calls `manager.stop_spawn(..., status="cancelled", exit_code=<130|143>, error="cancelled")`
  - `src/meridian/lib/launch/streaming_runner.py:669-693`

On report-watchdog expiry:

- `await manager.stop_spawn(..., status="cancelled", exit_code=1, error="report_watchdog")`
  - `src/meridian/lib/launch/streaming_runner.py:356-384`

### How that interacts with finalization

After each attempt:

- `attempt.timed_out` maps to `failure_reason = "timeout"`
  - `src/meridian/lib/launch/streaming_runner.py:941-942`
- parent `SIGINT` / `SIGTERM` map to `failure_reason = "cancelled"` / `"terminated"` if no harness terminal event won the race
  - `src/meridian/lib/launch/streaming_runner.py:943-950`
- durable report + report-watchdog is treated as success to avoid retrying a post-report cleanup kill
  - `src/meridian/lib/launch/streaming_runner.py:1047-1057`
- final state resolution happens under `signal_coordinator().mask_sigterm()`
  - `src/meridian/lib/launch/streaming_runner.py:1173-1231`

### Important finding

`streaming_runner.py` does not kill OS process groups itself. It delegates stop/termination to `SpawnManager.stop_spawn()`. That means any real fix has to propagate through the manager and then into adapter `stop()` methods.

## 4. `src/meridian/lib/streaming/spawn_manager.py`

### Where termination happens in the live path

`SpawnManager.stop_spawn()` is the live termination orchestrator:

- `src/meridian/lib/streaming/spawn_manager.py:532-592`

Its sequence is:

1. if cancelling and `cancel_sent` is false:
   - call `session.connection.send_cancel()`
   - emit one synthetic `cancelled` terminal event exactly once
2. resolve the completion future immediately with the requested terminal outcome
3. call `await session.connection.stop()`
4. cancel / await the drain task
5. stop control server and heartbeat
6. drop session registry entries

The crucial point: actual subprocess cleanup is adapter-owned in `session.connection.stop()`.

### Race/contract behavior already preserved here

Tests show several contracts that a new implementation must keep:

- `stop_spawn()` resolves a completion outcome without directly finalizing spawn-store rows
  - `tests/test_spawn_manager.py:776-888`
- cancelling emits a single synthetic `cancelled` terminal event even if stop is called twice
  - `tests/test_spawn_manager.py:890-990`
- cancel-vs-completion races preserve "first terminal wins" while still writing both event types to `output.jsonl`
  - `tests/test_spawn_manager.py:1001-1144`

Any new tree-kill logic must stay below this contract boundary. `SpawnManager.stop_spawn()` should still be responsible for status semantics; process-tree cleanup should stay inside connection cleanup or a shared helper it calls.

## 5. Per-harness adapters: where real subprocess termination happens today

### Claude

`src/meridian/lib/harness/connections/claude_ws.py`

- startup subprocess: `asyncio.create_subprocess_exec(...)`
  - `src/meridian/lib/harness/connections/claude_ws.py:332-357`
- cancel / interrupt:
  - `send_interrupt()` sends `SIGINT` directly to the subprocess via `process.send_signal(signal.SIGINT)`
    - `src/meridian/lib/harness/connections/claude_ws.py:178-199`
- stop / cleanup:
  - `_terminate_process()` closes stdin, then:
    - `process.terminate()`
    - `await asyncio.wait_for(process.wait(), timeout=_PROCESS_KILL_GRACE_SECONDS)`
    - fallback `process.kill()`
    - `await process.wait()`
  - `src/meridian/lib/harness/connections/claude_ws.py:405-422`

### Codex

`src/meridian/lib/harness/connections/codex_ws.py`

- startup subprocess: `asyncio.create_subprocess_exec(...)`
  - `src/meridian/lib/harness/connections/codex_ws.py:232-246`
- cancel:
  - `send_cancel()` does **not** kill the subprocess directly; it closes the websocket and transitions stopping
  - `src/meridian/lib/harness/connections/codex_ws.py:347-359`
- stop / cleanup:
  - `_cleanup_resources()`:
    - `process.terminate()`
    - wait for `_STOP_WAIT_TIMEOUT_SECONDS`
    - fallback `process.kill()`
  - `src/meridian/lib/harness/connections/codex_ws.py:534-565`

### OpenCode

`src/meridian/lib/harness/connections/opencode_http.py`

- startup subprocess: `asyncio.create_subprocess_exec(...)`
  - `src/meridian/lib/harness/connections/opencode_http.py:314-339`
- cancel:
  - `send_cancel()` posts an HTTP cancel action; no direct OS signal
  - `src/meridian/lib/harness/connections/opencode_http.py:220-240`
- stop / cleanup:
  - `_cleanup_runtime()`:
    - `process.terminate()`
    - wait for `_STOP_GRACE_SECONDS`
    - fallback `process.kill()`
  - `src/meridian/lib/harness/connections/opencode_http.py:669-687`

### Conclusion from adapter audit

Even if `signals.py` / `runner_helpers.py` are fixed, descendant leaks remain unless these adapter cleanup methods also switch from "kill the parent process only" to "kill the process tree rooted at the parent subprocess".

## 6. `src/meridian/lib/launch/process.py`

This is the primary foreground launch path, not the managed streaming path, but it is relevant to a Windows-port audit because it contains a large amount of Unix-only PTY/session machinery and some direct termination logic.

### What it currently does

- non-PTY path:
  - uses `subprocess.Popen(...)`
  - on `KeyboardInterrupt`, sends `SIGINT` only to the direct child process with `process.send_signal(signal.SIGINT)`
  - `src/meridian/lib/launch/process.py:151-171`

- PTY path:
  - `pty.openpty()`
  - `os.fork()`
  - child calls `os.setsid()`
  - child duplicates slave FD onto stdin/stdout/stderr with `os.dup2()`
  - child `os.execvpe(...)`
  - parent proxies data with `select.select()`, `os.read()`, `os.write()`
  - if `on_child_started(...)` fails, parent sends `SIGTERM` to the child PID only with `os.kill(child_pid, signal.SIGTERM)`
  - `src/meridian/lib/launch/process.py:173-215`

### Relevance to psutil tree termination

This path does not use `signal_process_group()`, but it still has the same top-process-only assumption. If the primary harness itself spawns descendants that move to a new session/process group, direct `SIGINT` / `SIGTERM` to only the top process will not clean those descendants up.

If this path remains in scope for Windows-port parity, it will need a separate redesign. A shared `terminate_tree(...)` helper can cover some of it, but the PTY / `fork` / `setsid` machinery is itself Unix-only and likely needs a broader Windows replacement strategy.

## 7. All Unix-specific APIs used in the audited path

Below is the full list I found in the relevant code, split into "strictly Unix/POSIX-only" vs "cross-platform API with Unix-specific semantics in this code".

### Strictly Unix/POSIX-only or unavailable on Windows in this form

From `src/meridian/lib/launch/signals.py`:

- `os.getpgid()` (`signals.py:37`)
- `os.killpg()` (`signals.py:38`)
- `signal.signal()` for process-global handlers (`signals.py:164`, `181`, `198`, `204`)
- `signal.getsignal()` (`signals.py:163`)

From `src/meridian/lib/launch/process.py`:

- `fcntl.ioctl()` (`process.py:221`, `233`)
- `pty.openpty()` (`process.py:175`)
- `select.select()` on PTY/stdin FDs (`process.py:114`)
- `termios.tcgetattr()` / `termios.tcsetattr()` / `termios.TCSADRAIN` (`process.py:106`, `136`)
- `termios.TIOCGWINSZ` / `termios.TIOCSWINSZ` (`process.py:221`, `233`)
- `tty.setraw()` (`process.py:107`)
- `os.fork()` (`process.py:178`)
- `os.setsid()` (`process.py:182`)
- `os.dup2()` (`process.py:183-185`)
- `os.waitpid()` / `os.waitstatus_to_exitcode()` (`process.py:138-139`, `203-204`)

From `src/meridian/lib/ops/spawn/execute.py`:

- `subprocess.Popen(..., start_new_session=True)` (`execute.py:692-700`)

From `src/meridian/lib/launch/streaming_runner.py`:

- `loop.add_signal_handler()` / `loop.remove_signal_handler()`
  - `streaming_runner.py:132-147`
  - `add_signal_handler` is not available on the default Windows asyncio event loop

From `src/meridian/lib/streaming/signal_canceller.py`:

- use of Unix-domain socket connector for app cancel lane:
  - `aiohttp.UnixConnector(path=...)`
  - `signal_canceller.py:144-152`

### Cross-platform APIs, but used with Unix signal semantics here

- `signal.SIGINT`, `signal.SIGTERM`, `signal.SIGKILL`, `signal.SIGWINCH`, `signal.SIG_DFL`, `signal.SIG_IGN`
- `os.kill(os.getpid(), signum)` in `signals.py:200`
- `os.kill(child_pid, signal.SIGTERM)` in `process.py:202`
- `process.send_signal(signal.SIGINT)` in:
  - `process.py:169`
  - `claude_ws.py:398`
- `process.terminate()` / `process.kill()` in:
  - `claude_ws.py:416-421`
  - `codex_ws.py:546-551`
  - `opencode_http.py:681-686`
- `os.kill(runner_pid, signal.SIGTERM)` in `signal_canceller.py:98-99`

For the Windows-port question, the real portability hazard is not just "uses `signal.*`" but "assumes POSIX signal/session/process-group semantics".

## 8. Draft `terminate_tree(proc, grace_secs)` primitive using `psutil`

This is the primitive I would introduce in a shared launch module, likely alongside or replacing the current helper in `runner_helpers.py`.

```python
import asyncio
from contextlib import suppress

import psutil


def _snapshot_process_tree(root_pid: int) -> tuple[psutil.Process | None, list[psutil.Process]]:
    try:
        root = psutil.Process(root_pid)
    except psutil.NoSuchProcess:
        return None, []

    with suppress(psutil.Error):
        children = root.children(recursive=True)
        # children first, root last
        dedup: dict[int, psutil.Process] = {proc.pid: proc for proc in children}
        dedup[root.pid] = root
        ordered = [proc for pid, proc in dedup.items() if pid != root.pid]
        return root, ordered + [root]

    return root, [root]


def _terminate_snapshot(procs: list[psutil.Process]) -> None:
    for proc in procs:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
            proc.terminate()


def _kill_snapshot(procs: list[psutil.Process]) -> None:
    for proc in procs:
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
            proc.kill()


async def terminate_tree(
    process: asyncio.subprocess.Process,
    *,
    grace_secs: float,
) -> None:
    if process.returncode is not None:
        return

    root, first_snapshot = _snapshot_process_tree(process.pid)
    if root is None:
        return

    _terminate_snapshot(first_snapshot)
    _gone, alive = await asyncio.to_thread(psutil.wait_procs, first_snapshot, timeout=grace_secs)

    if alive:
        # Re-snapshot once to catch descendants forked during shutdown.
        _root, second_snapshot = _snapshot_process_tree(process.pid)
        victims = second_snapshot or alive
        _kill_snapshot(victims)
        await asyncio.to_thread(psutil.wait_procs, victims, timeout=max(grace_secs, 0.1))

    with suppress(ProcessLookupError):
        await process.wait()
```

### Notes on the sketch

- Children-first ordering is deliberate. It avoids killing the root first and then losing the easiest route to descendants that are still attached.
- `psutil.wait_procs(...)` is blocking; it should run in `asyncio.to_thread(...)`.
- Re-snapshotting before `kill()` is worth doing. A one-time tree snapshot can miss descendants that fork during shutdown.
- `AccessDenied` should be suppressed the same way the existing code suppresses `ProcessLookupError`. It is a real edge on cross-user or hardened environments.
- I would keep the primitive focused on "best-effort stop tree rooted at this subprocess", not on status semantics. Exit-code mapping stays at the runner layer.

### Possible API shape improvement

Because the repo has both `asyncio.subprocess.Process` and `subprocess.Popen` callsites, a more reusable version may accept a pid plus an optional awaitable waiter:

```python
async def terminate_tree_pid(
    pid: int,
    *,
    grace_secs: float,
    wait: Callable[[], Awaitable[object]] | None = None,
) -> None:
    ...
```

That would let:

- adapters pass `process.pid` and `process.wait`
- classic sync PTY code pass `child_pid` and perhaps no waiter

## 9. Callsites that would need to change

### Direct changes required for the current managed-spawn path

1. `src/meridian/lib/harness/connections/claude_ws.py:405-422`
   - replace `_terminate_process()` parent-only `terminate()/kill()` logic with shared `terminate_tree(...)`

2. `src/meridian/lib/harness/connections/codex_ws.py:534-565`
   - replace `_cleanup_resources()` parent-only `terminate()/kill()` logic with shared `terminate_tree(...)`

3. `src/meridian/lib/harness/connections/opencode_http.py:669-687`
   - replace `_cleanup_runtime()` parent-only `terminate()/kill()` logic with shared `terminate_tree(...)`

These are the highest-priority callsites because `SpawnManager.stop_spawn()` routes through them today.

### Legacy/classic helper path

4. `src/meridian/lib/launch/signals.py:21-40`
   - replace or remove `signal_process_group(...)`

5. `src/meridian/lib/launch/signals.py:111-115`
   - `SignalForwarder.forward_signal()` should call the new tree helper or be deleted if no longer used

6. `src/meridian/lib/launch/runner_helpers.py:259-278`
   - replace `terminate_process()` group signaling with tree termination

7. `src/meridian/lib/launch/runner_helpers.py:280-295`
   - `wait_for_process_exit()` should continue to call the updated helper if this path is kept alive

### Additional non-streaming cleanup callsites worth auditing in the same change

8. `src/meridian/lib/launch/process.py:167-170`
   - non-PTY foreground `KeyboardInterrupt` only signals the direct child with `SIGINT`

9. `src/meridian/lib/launch/process.py:201-204`
   - PTY startup error path only sends `SIGTERM` to the direct `child_pid`

10. `src/meridian/lib/streaming/signal_canceller.py:98-99`
   - this only signals the runner process, not the harness/tool tree directly
   - this may be acceptable if runner-side cleanup is reliable, but it is another POSIX-signal assumption relevant to Windows-port work

### Cleanup opportunity

11. `src/meridian/lib/launch/request.py:29-36` plus `src/meridian/lib/ops/spawn/prepare.py:171-193`
   - `kill_grace_secs` is persisted but currently unused
   - once `terminate_tree(...)` exists in the live path, thread `request.budget.kill_grace_secs` into adapter stop/cleanup or delete the field

## 10. Edge cases and race conditions the current code handles that a replacement must preserve

### A. Process disappeared between observation and signal delivery

Current behavior:

- `signal_process_group()` treats `ProcessLookupError` as expected
  - `signals.py:27-29`, `39-40`

Preserve:

- `terminate_tree(...)` must suppress `psutil.NoSuchProcess` / `ProcessLookupError` at every step

### B. First signal graceful, second signal hard-kill

Current behavior:

- `SignalForwarder.forward_signal()` escalates to `SIGKILL` on the second forwarded signal
  - `signals.py:113-115`

Preserve:

- if the signal-forwarding path remains, repeated parent interrupts should still bypass grace and force-kill the tree

### C. Parent-signal exit-code semantics

Current behavior:

- `SIGINT -> 130`
- `SIGTERM -> 143`
- negative raw return codes are mapped back through signal numbers
  - `signals.py:50-82`

Preserve:

- switching the kill mechanism must not change exit-code mapping or cancel/finalize semantics

### D. Finalization critical sections must ignore incoming `SIGTERM`

Current behavior:

- `signal_coordinator().mask_sigterm()` wraps final cleanup / finalize windows in `streaming_runner.py`
  - `streaming_runner.py:522-533`
  - `streaming_runner.py:1195-1231`

Preserve:

- a new termination helper should not punch through those critical sections or introduce awaits in the wrong layer that widen the race window

### E. Completion-vs-signal race in streaming path

Current behavior:

- if completion and signal land together, runner waits briefly for a late terminal frame before deciding status
  - `streaming_runner.py:653-684`
- tests cover the race
  - `tests/exec/test_streaming_runner.py:997-1085`

Preserve:

- connection stop/tree-kill must remain downstream of this status-resolution logic

### F. Cancel terminal event emitted once

Current behavior:

- `SpawnManager.stop_spawn()` emits one synthetic `cancelled` event exactly once
  - `spawn_manager.py:548-560`, `594-620`
- test coverage:
  - `tests/test_spawn_manager.py:890-990`

Preserve:

- moving cleanup into a shared tree-kill helper must not duplicate cancel events

### G. "First terminal wins" in cancel-vs-completion races

Current behavior:

- completion future is resolved once; later outcomes do not overwrite it
  - `spawn_manager.py:718-728`
- tests cover both orderings
  - `tests/test_spawn_manager.py:1001-1144`

Preserve:

- do not let a delayed tree-kill completion overwrite an already-resolved terminal outcome

### H. Durable-report watchdog success special case

Current behavior:

- if watchdog kills a lingering connection after a durable report already exists, the attempt is treated as success
  - `streaming_runner.py:1047-1057`

Preserve:

- tree-kill cleanup after durable completion must still map to success, not a synthetic failure

### I. Descendants created during shutdown

Current code does not explicitly handle this, but the `killpg` model implicitly targeted "whatever is still in the process group at signal time". A tree-based replacement should emulate that best-effort breadth by re-snapshotting before escalation to `kill()`.

### J. PID reuse

The repo already has a PID reuse guard in `src/meridian/lib/state/liveness.py:5-25`. For a launch-time helper working on a live `asyncio.subprocess.Process`, PID reuse is much less likely than in persisted state reconciliation, but if the helper is generalized to stored runner PIDs later, the `create_time` guard pattern is worth reusing.

## 11. Practical recommendation

If the goal is "replace current Unix process-group termination with psutil-based recursive descendant termination", the minimal correct plan is:

1. Add a shared async `terminate_tree(...)` helper in the launch/runtime layer using `psutil`.
2. Switch the live adapter cleanup methods to use it:
   - `claude_ws.py`
   - `codex_ws.py`
   - `opencode_http.py`
3. Switch legacy `signals.py` / `runner_helpers.py` to use the same helper or delete dead process-group code if it is truly retired.
4. Thread `request.budget.kill_grace_secs` into the live stop path, or delete it if the project no longer wants per-request kill grace.
5. Add tests around:
   - children-first terminate/kill ordering
   - `NoSuchProcess` / `AccessDenied`
   - re-snapshot-on-escalation behavior
   - adapter cleanup invoking the shared helper

## 12. Net answer to the original question

Replacing `killpg(top_pgid)` with `psutil.Process.children(recursive=True) -> terminate -> wait -> kill` is directionally correct, and `psutil` is already available in the repo.

But in the current codebase, the main work is **not** in `signals.py`. The active managed-spawn termination path is:

- `streaming_runner.py` timeout/signal/watchdog handling
- `SpawnManager.stop_spawn()`
- per-harness adapter `stop()` cleanup

So a real fix must land in the adapters and probably centralize there, with `signals.py` / `runner_helpers.py` updated secondarily for consistency or dead-code cleanup.
