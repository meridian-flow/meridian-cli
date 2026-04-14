# Feasibility — Spawn Control Plane Redesign

Probe evidence and assumption verdicts that ground the spec and architecture. Each
entry is either VERIFIED, FALSIFIED, or OPEN. Rows tagged OPEN must be closed before
implementation begins.

## P1 — `streaming_runner.py` already has SIGTERM handling

**Question.** Does the streaming runner already finalize the spawn as `cancelled`
when its parent process receives SIGTERM?

**Probe.** Static read of
`src/meridian/lib/launch/streaming_runner.py` lines 131–158, 423–506, 686–693.

**Verdict.** VERIFIED. `_install_signal_handlers` registers SIGINT/SIGTERM on the
asyncio loop. The handler sets `shutdown_event` and records the signal. In
`_run_streaming_attempt`, when `signal_task` completes, the runner calls
`manager.stop_spawn(status="cancelled", exit_code=signal_to_exit_code(...) or 130, error="cancelled")`.
The terminal finalize path in `execute_with_streaming` then writes
`finalize_spawn(... origin="runner")` with `status="cancelled"`.

**Implication.** Direction #1 ("cancel = SIGTERM the runner") is already 80% wired
on the rich `execute_with_streaming` path. The naked `run_streaming_spawn` path used
by `meridian streaming serve` finalizes from `streaming_serve.py` with
`origin="launcher"`, also cancelled-by-signal. Both paths converge on the right
behavior **once the cancel control-socket message is removed.**

## P2 — `SpawnManager.cancel()` does not finalize, just routes

**Question.** Why does `meridian spawn inject --cancel` end as `succeeded`
instead of `cancelled`?

**Probe.** Static read of
`src/meridian/lib/streaming/spawn_manager.py:365–382` (`cancel`) and
`src/meridian/lib/streaming/spawn_manager.py:192–296` (`_drain_loop` finally
clause).

**Verdict.** VERIFIED. `SpawnManager.cancel` writes the `cancel` action to
`inbound.jsonl` and calls `connection.send_cancel()`. That gracefully tells the
harness to stop emitting; the harness exits the event stream **cleanly**. The
drain loop's `finally` block then writes
`DrainOutcome(status="succeeded", exit_code=0)` because no exception was raised
and no cancel marker was set on the session. `streaming_serve.py:115` sees that
DrainOutcome and calls `finalize_spawn(status="succeeded", origin="launcher")`.

**Implication.** Even if we kept the control-socket cancel, the bug is that
`SpawnManager.cancel` does not transition the session into a cancelled state
(the way `SpawnManager.stop_spawn(status="cancelled", ...)` does). The redesign
solves this by removing the control-socket cancel entirely; the SIGTERM-driven
path **does** call `stop_spawn(status="cancelled", ...)`, so the session is
correctly marked.

## P3 — Codex `turn/completed` with `interrupted` is treated as terminal

**Question.** Why does `meridian spawn inject --interrupt` finalize the spawn as
`failed`?

**Probe.** Static read of
`src/meridian/lib/launch/streaming_runner.py:254–272` (`_terminal_event_outcome`),
plus `_consume_subscriber_events:362–365`.

**Verdict.** VERIFIED. `_terminal_event_outcome` matches the codex
`turn/completed` event and inspects `turn.status`. The current rule is "any
non-completed status is terminal `failed`". `turn_status == "interrupted"` therefore
returns `_TerminalEventOutcome(status="failed", exit_code=1, error="turn_interrupted")`.
This sets `terminal_event_future`, which `_run_streaming_attempt` honors by
calling `manager.stop_spawn(status="failed")`. Result: the spawn is finalized
after one interrupt.

**Implication.** Direction #2 ("interrupt is non-fatal") requires
`_terminal_event_outcome` to **stop classifying `turn/completed`-with-`interrupted`
as terminal**. Per-turn outcomes are not per-spawn outcomes; the runner must
keep waiting for either another `turn/*` event, a real `session.error`, or a
SIGTERM/`stop_spawn` call.

## P4 — App-server-launched spawns never populate `runner_pid`

**Question.** Why does `meridian spawn show` report `missing_worker_pid` for
HTTP-launched spawns while the app still owns them?

**Probe.** Static read of `src/meridian/lib/app/server.py:155–178`
(`reserve_spawn_id`) and `src/meridian/lib/state/reaper.py:145–179`
(`decide_reconciliation`).

**Verdict.** VERIFIED. `reserve_spawn_id` calls `spawn_store.start_spawn` with
no `runner_pid`. `SpawnManager.start_spawn` does not patch `runner_pid` on the
record either (compare with `streaming_runner.py:434–438` which explicitly
calls `spawn_store.update_spawn(state_root, spawn_id, runner_pid=os.getpid())`).
The record stays `runner_pid=None` for the entire lifetime of the spawn.

The reaper's branch for `runner_pid is None or runner_pid <= 0` falls through to
`missing_worker_pid` once the 15-second startup grace window passes **and** no
tracked-activity artifact is fresh inside the 120-second heartbeat window. Idle
periods between user messages exceed both bounds.

**Implication.** Direction #3 must close this gap. Either the FastAPI worker's
PID is written into `runner_pid` at spawn-creation time, **or** the
`SpawnManager` is responsible for keeping a spawn-scoped heartbeat fresh while
the connection is live. Both options are evaluated in the architecture doc.

## P5 — Heartbeat is only touched by `runner.py` / `streaming_runner.py`

**Question.** Are heartbeats being touched on the app path at all?

**Probe.** Grep for `_touch_heartbeat_file` and `_run_heartbeat_task` across
`src/meridian/`.

**Verdict.** VERIFIED. Both helpers are private to `runner.py` and
`streaming_runner.py`. `SpawnManager` and `app/server.py` do not import them.
The heartbeat artifact is therefore **never** touched on the app path. The
reaper's "recent activity" check falls back to `output.jsonl` and `stderr.log`
mtime — which are stale during inter-turn idle.

**Implication.** Whichever option Direction #3 picks, heartbeat ownership must
move to whichever process owns the live connection (the `SpawnManager` or its
host). It cannot stay attached to the legacy runner-only path.

## P6 — `spawn cancel` (top-level CLI) already SIGTERMs

**Question.** Is there an existing CLI surface that already implements
"SIGTERM the runner" semantics?

**Probe.** Static read of `src/meridian/lib/ops/spawn/api.py:466–522`
(`spawn_cancel_sync`).

**Verdict.** VERIFIED. The top-level `meridian spawn cancel <id>` command
already resolves a target PID (preferring `worker_pid`, falling back to
background/harness PIDs), sends SIGTERM, and writes
`finalize_spawn(status="cancelled", origin="cancel")`. This path is independent
of the control socket and is used by both interactive cancellation and
timeout-driven cleanup.

**Implication.** Direction #1 is partially done — but the resolver currently
prefers `worker_pid` (the harness PID) over the runner. We must repoint the
resolver at `runner_pid` for streaming spawns so the runner's signal handler
performs the proper cancel (`origin=runner|cancel`, `status=cancelled`) instead
of killing the harness child directly and letting the runner reconcile.

## P7 — Authorization context: `MERIDIAN_SPAWN_ID` is inherited

**Question.** Is there a stable identifier in the spawn process environment
that names "the spawn this process is running inside", so that lifecycle
operations can be parent-scoped?

**Probe.** Grep for `MERIDIAN_SPAWN_ID` in `src/meridian/`.

**Verdict.** OPEN. `MERIDIAN_CHAT_ID` is documented as "inherited parent
session id" in `meridian-cli/SKILL.md`. `MERIDIAN_DEPTH` indicates spawn
nesting (>0 means inside a spawn). I have not yet confirmed whether a spawn-id
env var is similarly inherited. If absent, we must add one (cheap) before the
authorization model can make parent-ancestry decisions.

**Action.** The architecture doc proposes `MERIDIAN_SPAWN_ID=<id>` injection
into every child spawn process; an architect/probe spawn must verify whether
the env is already plumbed through `prepare_launch_context`. Filed as
spec-blocking until verified.

## P8 — Concurrent inject ack ordering

**Question.** Why does the smoke double-inject (#31) reverse user-message
ordering and drop one ack?

**Probe.** Static read of
`src/meridian/lib/streaming/control_socket.py` (one connection per
`open_unix_server`) and `SpawnManager.inject` (no per-spawn lock).

**Verdict.** VERIFIED. `start_unix_server` accepts each connection
concurrently. Two injects open two sockets. Each handler calls
`SpawnManager.inject`, which writes `inbound.jsonl` and calls
`connection.send_user_message` without serialization. The inbound write order
is preserved by the file lock, but `send_user_message` to the harness can
interleave: the second writer's payload may arrive at the harness stdin before
the first writer's drain completes, depending on scheduler ordering.

**Implication.** A per-spawn asyncio lock around the
`inbound.jsonl` write **and** the harness-bound send is sufficient to make
inject linearizable. The control-socket server should not need to change; only
`SpawnManager.inject` needs the mutex. Same lock applies to interrupt for
sequencing.

## P9 — Reaper reads `runner_pid_alive` only when status != "finalizing"

**Question.** If the runner sits in finalizing for a long time, does the
reaper still check liveness?

**Probe.** Static read of
`src/meridian/lib/state/reaper.py:121–137` and `145–179`.

**Verdict.** VERIFIED. `_collect_artifact_snapshot` skips the
`is_process_alive` call when `record.status == "finalizing"` and
`decide_reconciliation` only considers durable-report-completion / recent
activity in that branch. The "finalizing" hand-off is intentional — the runner
masks SIGTERM during the critical section, so liveness via PID is misleading.

**Implication.** The fix must not regress the finalizing branch. If app-managed
spawns ever enter `finalizing`, the same recent-activity rule applies; nothing
changes there.

## Open items

- **P7.** Verify `MERIDIAN_SPAWN_ID` plumbing, or specify the env-injection
  contract precisely. Architect spawn must close this before the authorization
  spec is final.
- **P10.** What does `connection.send_interrupt()` actually do per harness
  (codex/claude/opencode)? If the harness emits `turn/completed` with
  `interrupted`, the runner must treat that as **non-terminal** (Direction #2),
  but we should also verify the harness does not exit its own event stream as
  a side effect of receiving the interrupt. Architect spawn to enumerate
  per-harness behavior.
