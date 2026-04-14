# Design Decisions — Spawn Control Plane

Append-only log of the non-obvious judgment calls made during this design
cycle. Each entry states what was chosen, what alternatives were considered,
and why this choice won.

## D-01 — Cancel goes through OS signals, not control-socket transitions

**Choice.** All cancel callers (CLI, HTTP, timeout killers) funnel through
`SignalCanceller.cancel(spawn_id)` → SIGTERM to the runner pid. The runner's
existing SIGTERM handler drives `manager.stop_spawn(status="cancelled",
origin="runner")`.

**Alternatives considered.**

1. *Fix `SpawnManager.cancel` to transition the session cleanly before
   closing the harness.* Would require the manager to synthesize an internal
   "cancel" drain outcome and bypass the harness's natural terminal event.
   Adds a new failure mode in the drain state machine and leaves two cancel
   code paths (signal-based for external kills, cooperative for
   CLI-invoked). Duplication compounds #29-class bugs.
2. *Leave `SpawnManager.cancel` and just fix its status mapping.* The
   underlying issue — `connection.send_cancel()` for codex closes the
   WebSocket cleanly, producing `DrainOutcome(status="succeeded")` — would
   still require intercepting the drain outcome. Same surface-area cost
   as (1) with no upside.

**Why signals win.** The runner already has a SIGTERM handler, an
exit-code mapping (143), and the `signal_coordinator().mask_sigterm()`
critical section for finalize. Routing cancel through it reuses a proven,
race-tested path. External killers (`timeout 60 meridian spawn ...`) already
use SIGTERM today; this collapses three slightly-different "cancel"
semantics into one.

**Tradeoff.** Cancel becomes less "cooperative-looking" — the harness isn't
asked nicely to stop; it's terminated by its parent. For meridian's model
(every spawn is a child process we own), that's correct: the spawn is a
resource, and cancel is resource termination. Interrupt retains the
cooperative semantics for the "please stop this turn" case.

## D-02 — Heartbeat ownership moves to SpawnManager (LIV-003)

**Choice.** Extract a module-level `heartbeat_loop` helper; SpawnManager
starts and stops it per spawn. Runners that don't use SpawnManager still
call the helper but via SpawnManager instantiation.

**Alternative considered.** Leave heartbeat in `runner.py` /
`streaming_runner.py` and add a parallel heartbeat loop to the FastAPI
`_run_managed_spawn` path. Rejected: three heartbeat writers is worse than
one, and the FastAPI path would still drift from runner behavior on
interval, cleanup, and error handling.

**Why this wins.** The spawn is alive iff its SpawnManager is running. The
manager is the natural owner of that signal. The runner scripts become
thinner (one import + one `manager._start_heartbeat()` call).

## D-03 — FastAPI worker does NOT accept SIGTERM for per-spawn cancel

**Choice.** CLI `meridian spawn cancel <id>` dispatches by launch mode:
foreground spawns SIGTERM the runner pid; app-launched spawns go through
`POST /api/spawns/{id}/cancel`. The HTTP handler runs inside the FastAPI
worker and calls `manager.stop_spawn(...)` in-process.

**Alternative considered.** Have the FastAPI worker install a custom
SIGTERM handler that reads a "current target spawn" from a file or socket
and cancels just that spawn. Rejected: signal handlers inherently
single-valued, the indirection is brittle, and it conflates "server
shutdown" with "one of the server's spawns was cancelled".

**Why this wins.** Signals are process-level; per-spawn semantics need a
per-spawn channel. HTTP already exists, runs inside the worker, and the
in-process `SpawnManager` is directly addressable there. The CLI
dispatcher is one extra `if record.launch_mode == "app":` branch.

**Constraint discovered.** This design relies on app-server being a single
worker. Multi-worker FastAPI deployments would need an affinity scheme
("which worker owns spawn X?"); out of scope and not on the roadmap.

## D-04 — `turn/completed` is never spawn-terminal (INT-002)

**Choice.** Narrow `_terminal_event_outcome` so per-turn payloads don't
finalize the spawn. Only `session.error` / `session.terminated`, natural
stream end, SIGTERM, and the report watchdog finalize.

**Alternative considered.** Introduce a per-harness map
`{harness: {turn_status: spawn_outcome}}`. Rejected: codifies the bug.
`turn_status` is about a turn, not a session; any mapping reintroduces
the #28 confusion when a harness adds new turn statuses.

**Why this wins.** The classification concept is "what the harness meant
by this event". `turn/completed` means "one turn ended"; that is never a
spawn-terminal statement.

**Feasibility note.** P10 probe confirmed codex is the only harness
emitting per-turn terminal-looking payloads. Claude `result` and opencode
`session.idle`/`session.error` already correspond to spawn-end, so their
classification is unchanged.

## D-05 — Per-spawn asyncio.Lock, not a command queue (INJ-002)

**Choice.** `inject_lock` module with a `dict[SpawnId, asyncio.Lock]`.
`SpawnManager.inject` and `.interrupt` acquire the lock for the duration
of `(record_inbound + send_*)`.

**Alternatives considered.**

1. Per-spawn `asyncio.Queue[Command]` with a dedicated worker task.
   Rejected: doubles task accounting during shutdown and splits error
   paths across caller and worker.
2. Lock inside `HarnessConnection`. Rejected: ties serialization to the
   connection rather than the spawn; a future connection pool would
   violate the invariant.

**Why this wins.** Smallest code change that guarantees FIFO; method
signatures unchanged; error paths unchanged.

## D-06 — Authorization by env-derived caller id, not by cryptographic token

**Choice.** `MERIDIAN_SPAWN_ID` in the caller's environment identifies the
caller. `authorize()` is a pure function over `(state_root, target, caller)`.

**Alternatives considered.**

1. Per-spawn API token stamped into env and verified by the guard.
   Rejected: adds token rotation, token storage, and token revocation to a
   problem that today has a simple ancestry answer.
2. Requiring an MCP-style auth header. Rejected: forgeable (local process
   can set any header), and the threat model explicitly does not include
   adversaries inside the process tree.

**Why this wins.** The threat model (subagent accidentally cancels sibling)
is an honest-actors problem, not a hostile-actors one. Env-derived
identity matches the pattern meridian already uses for parent-tracking and
costs nothing.

**Escape valve.** If a future deployment wants hostile-actor resistance,
replace `caller_from_env` / `_caller_from_http` / `_caller_from_socket_peer`
without touching `authorize()`. The boundary is deliberate.

## D-07 — Inject stays un-gated

**Choice.** `meridian spawn inject <id> '<text>'` and `POST /inject` (text)
are explicitly outside the authorization guard.

**Alternative considered.** Gate inject the same as interrupt/cancel.
Rejected: inject is a data-plane "send text" operation; collaboration
between sibling agents is an intentional feature. Gating it would break
multi-agent choreography patterns that are legitimate use cases.

**Why this wins.** The interrupt/cancel threats (force-terminate a sibling,
crash an unrelated user's spawn) don't apply to "send a text message".
Worst case: a sibling agent confuses another by injecting noise; the
receiver can ignore.

## D-08 — Delete `SpawnManager.cancel` outright; no shim (R-06)

**Choice.** Remove `SpawnManager.cancel`, its control-socket handler, and
the CLI `--cancel` flag in the same change set. Audit callers and update.

**Alternative considered.** Keep a deprecation shim that forwards to
`SignalCanceller` so external callers don't break. Rejected: the project
explicitly has no backcompat guarantee (per CLAUDE.md "no real users, no
real user data"). A shim costs maintenance and ambiguous semantics (if
cancel now means SIGTERM, the shim's behavior is "SIGTERM inside a
SpawnManager context" — which has never been a real contract).

**Why this wins.** Simpler surface, one cancel path, no legacy branches
in code review forever.

## D-09 — Rejected: cancel via "terminal message" over control socket

**Alternative rejected before it could be written up.** An earlier option
considered a new control-socket `type="cancel_graceful"` that would
cause `SpawnManager` to drive a drain-then-finalize cycle without any
signal. Rejected because:

- The harness side (notably codex) has no "drain and stay dead" primitive
  today — `send_cancel` closes the WS.
- Adding one would require coordinating a new message type across every
  harness adapter (claude, codex, opencode), a much larger surface than
  signal-based cancel.
- The coordination between "cooperative cancel finished" and the reaper's
  authority window is identical to the SIGTERM path, so we'd pay all the
  integration cost with no clarity win.

## D-10 — App-launched spawns populate `runner_pid` with FastAPI worker pid

**Choice.** The FastAPI worker's pid goes into `runner_pid` at spawn
creation time. This matches the contract "`runner_pid` is the process
that owns finalize and heartbeat".

**Alternative considered.** Leave `runner_pid` unset for app-launched
spawns and add a reaper carve-out to skip the check. Rejected: carve-outs
erode the clarity of the reaper's rule. The problem statement (#30) is
literally "the contract wasn't met"; meeting the contract is the fix.

**Tradeoff.** The FastAPI worker's pid is now visible in the spawn record;
if the worker restarts, previously-running spawns have a stale
`runner_pid`. That case is already handled by the reaper (pid-not-alive →
reconciliation) and is actually the signal we want: a worker restart
should let the reaper take over.
