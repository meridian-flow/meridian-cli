# Feasibility — Spawn Control Plane Redesign (v2)

Probe evidence and assumption verdicts. All entries VERIFIED or FALSIFIED;
no OPEN items remain. v2 closed P7 and P10 from v1.

## P1 — `streaming_runner.py` already has SIGTERM handling

**Verdict.** VERIFIED (v1, unchanged).

`_install_signal_handlers` registers SIGINT/SIGTERM on the asyncio loop.
Handler sets `shutdown_event` and records the signal. In
`_run_streaming_attempt`, when `signal_task` completes, the runner calls
`manager.stop_spawn(status="cancelled", exit_code=signal_to_exit_code(...))`.
The terminal finalize path writes `finalize_spawn(origin="runner",
status="cancelled")`.

**Implication.** Cancel = SIGTERM the runner is already 80% wired.

## P2 — `SpawnManager.cancel()` does not finalize, just routes

**Verdict.** VERIFIED (v1, unchanged).

`SpawnManager.cancel` writes the cancel action to `inbound.jsonl` and
calls `connection.send_cancel()`. The harness exits cleanly →
`DrainOutcome(status="succeeded")` → finalize as `succeeded`. This is
the root cause of #29.

**Implication.** Deleting the control-socket cancel path (D-08) and
routing through SIGTERM (D-01) fixes #29.

## P3 — Codex `turn/completed` with `interrupted` is treated as terminal

**Verdict.** VERIFIED (v1, unchanged).

`_terminal_event_outcome` matches codex `turn/completed` and returns
`failed` for `turn_status == "interrupted"`. Root cause of #28.

**Implication.** `_terminal_event_outcome` must return `None` for
`turn/completed` events (D-04).

## P4 — App-server-launched spawns never populate `runner_pid`

**Verdict.** VERIFIED (v1, unchanged).

`reserve_spawn_id` calls `start_spawn` with no `runner_pid`. Record stays
`runner_pid=None` for the spawn lifetime. Root cause of #30.

**Implication.** App server must set `runner_pid=os.getpid()` at spawn
creation (D-10).

## P5 — Heartbeat is only touched by `runner.py` / `streaming_runner.py`

**Verdict.** VERIFIED (v1, unchanged).

Both helpers are private to the runner scripts. `SpawnManager` and
`app/server.py` never touch heartbeat. App-managed spawns get stale
heartbeats.

**Implication.** Heartbeat ownership moves to `SpawnManager` (D-02).

## P6 — `spawn cancel` (top-level CLI) already SIGTERMs

**Verdict.** VERIFIED (v1, unchanged).

`spawn_cancel_sync` resolves a target PID (prefers `worker_pid`, falls
back to others), sends SIGTERM, writes `finalize_spawn(origin="cancel")`.
Resolver must flip to runner-first for the redesign.

## P7 — `MERIDIAN_SPAWN_ID` is inherited by child spawns

**Verdict.** VERIFIED (v2 closed).

**Probe.** Static read of:
- `src/meridian/lib/launch/command.py:43-44` — sets
  `env_overrides["MERIDIAN_SPAWN_ID"] = spawn_id.strip()` when
  `spawn_id is not None`.
- `src/meridian/lib/core/context.py:30` — reads
  `os.getenv("MERIDIAN_SPAWN_ID", "")` and stores as
  `RuntimeContext.spawn_id`.
- `src/meridian/lib/core/context.py:68-70` — `to_env_overrides()` emits
  `MERIDIAN_SPAWN_ID` when `spawn_id is not None`.

The env var is set in the child process environment by `command.py` at
harness launch time, and read back by `context.py` at startup. The
ancestry chain works: parent sets `MERIDIAN_SPAWN_ID=<parent_id>` in the
child's env; the child reads it as its own spawn_id context.

**Implication.** The authorization model (AUTH-001) can rely on
`MERIDIAN_SPAWN_ID` being present in spawned subagents. No additional
plumbing required.

## P8 — Concurrent inject ack ordering

**Verdict.** VERIFIED (v1, unchanged).

Two injects open two sockets. `SpawnManager.inject` writes `inbound.jsonl`
and calls `send_user_message` without serialization. Interleaving possible.

**Implication.** Per-spawn asyncio lock (D-05) fixes this.

## P9 — Reaper reads `runner_pid_alive` only when status != "finalizing"

**Verdict.** VERIFIED (v1, unchanged).

Reaper skips `is_process_alive` when `record.status == "finalizing"`.
The finalizing hand-off is intentional.

**Implication.** SignalCanceller must also respect the finalizing gate
(D-13). No SIGKILL during finalizing.

## P10 — Per-harness interrupt behavior

**Verdict.** VERIFIED (v2 closed).

**Probe.** Static read of all three harness connections:

### Codex (`codex_ws.py:335-354`)
- `send_interrupt()` sends `turn/interrupt` with `threadId` + `turnId`
  over WebSocket. Returns silently if no `_current_turn_id`.
- Codex responds with `turn/completed` carrying
  `turn.status = "interrupted"`. The WS connection stays open. No
  session-level event is emitted.
- **Connection survives interrupt.** Codex does NOT close the WS or
  exit its event stream on interrupt.

### Claude (`claude_ws.py:175-181`)
- `send_interrupt()` sends `SIGINT` to the Claude subprocess via
  `_signal_process(signal.SIGINT)`. Idempotent flag `_interrupt_in_flight`.
- Claude responds with a `result` event. The subprocess does NOT exit
  on a single SIGINT during a turn; it interrupts the current generation
  and emits a result.
- **Connection survives interrupt.** Claude's PTY-based connection
  stays open after SIGINT.

### OpenCode (`opencode_http.py:201-215`)
- `send_interrupt()` POSTs to the session action endpoint with various
  payload variants (`{response: "abort"}`, `{reason: "interrupt"}`, etc.).
  Idempotent flag.
- OpenCode responds by aborting the current action. The HTTP session
  stays open.
- **Connection survives interrupt.** OpenCode does NOT terminate the
  session on interrupt.

**Conclusion for INT-002.** All three harnesses keep the connection alive
after interrupt. The only thing that was making interrupt fatal was the
runner's `_terminal_event_outcome` classifier treating `turn/completed
interrupted` as spawn-terminal. Fixing the classifier (D-04) makes
interrupt non-fatal across all harnesses.

## P11 — AF_UNIX support in uvicorn

**Verdict.** VERIFIED (v2 new).

**Probe.** Uvicorn natively supports `--uds <path>` for AF_UNIX sockets.
The `uvicorn.run()` API accepts `uds="path"` as a keyword argument.
FastAPI + uvicorn over AF_UNIX is a documented, tested configuration.
`SO_PEERCRED` on AF_UNIX is available via `socket.SO_PEERCRED` on Linux
(getsockopt returns `struct ucred` with pid, uid, gid).

**Implication.** D-11 (app server on AF_UNIX) is technically
straightforward. The main work is: change `app_cmd.py` to pass `uds=`
instead of `host=`/`port=`, add a `--proxy` mode for browser access,
and write the `_caller_from_http` peer-cred extraction.

## P12 — PID-reuse guard in liveness.py

**Verdict.** VERIFIED (v2 new).

**Probe.** `src/meridian/lib/state/liveness.py:8` — `is_process_alive`
accepts `created_after_epoch` and guards against PID reuse using
`proc.create_time() > created_after_epoch + _PID_REUSE_GUARD_SECS (30s)`.

The reaper passes `created_after_epoch=started_epoch` at
`reaper.py:127-129`. `SignalCanceller` must use the same guard (D-15).

## P13 — Ack emission happens outside SpawnManager lock

**Verdict.** VERIFIED (v2 new).

**Probe.** `control_socket.py:51,93` — the JSON reply is written by the
control socket handler AFTER `SpawnManager.inject/interrupt` returns. The
v1 lock wrapped only the SpawnManager call. Two concurrent callers could
have their ack order reversed relative to `inbound.jsonl` order.

**Implication.** D-05 extension: either move ack emission inside the lock
scope, or redefine INJ-002 contract around `inbound_seq` rather than ack
arrival order. v2 chooses to extend the lock scope to cover ack emission
(the control socket calls a new `SpawnManager.inject_and_reply` method
that holds the lock across both operations).
