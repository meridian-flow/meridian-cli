# Cancel — Signal-Based Lifecycle Termination

Cancel is a **lifecycle operation**: the spawn must end as `cancelled`,
regardless of which surface initiated the cancel and regardless of whether
the harness happens to exit cleanly when asked to stop. Cancel never lives
on the per-spawn control socket; it lives at the OS process layer so the
same mechanism serves CLI, HTTP, and external timeout-based killers.

All cancel callers go through `SignalCanceller.cancel(spawn_id)`.
The canceller dispatches by `launch_mode`:
- CLI-launched spawns (`foreground`/`background`): SIGTERM to `runner_pid`.
- App-managed spawns (`app`): in-process `manager.stop_spawn()` or HTTP
  `POST /cancel` when cross-process (v2r2 D-03, two-lane).

## Triggers covered

| Trigger | Surface |
|---|---|
| User runs `meridian spawn cancel <id>` | CLI |
| HTTP client calls `POST /api/spawns/{id}/cancel` | App server (AF_UNIX) |
| External supervisor sends SIGTERM to the runner process | OS |
| Authorized child agent invokes a gated cancel tool | Agent runtime |

## EARS Statements

### CAN-001 — SIGTERM to the runner finalizes as cancelled

**When** the process identified by `runner_pid` on a non-terminal
`SpawnRecord` receives `SIGTERM`,
**the runner process shall** finalize the spawn with
`status="cancelled"`, `exit_code=143`, `origin="runner"`,
`error="cancelled"`, **before** its own process exits.

**Observable.** A single `SpawnFinalizeEvent` row in `spawns.jsonl` with
`status="cancelled"`, `origin="runner"`, `exit_code=143`, written before
the runner process is reaped.

**Applies to:** CLI runner (streaming_runner.py). App-managed spawns
use the in-process cancel path (CAN-002 dispatcher), which also calls
`manager.stop_spawn(status="cancelled")` but without SIGTERM.

### CAN-002 — `meridian spawn cancel` resolves the runner PID and SIGTERMs it

**When** `meridian spawn cancel <id>` is invoked against a non-terminal
streaming spawn,
**the CLI shall** invoke `SignalCanceller.cancel(spawn_id)` which
dispatches by `launch_mode`:
- **`foreground`/`background`**: resolve `runner_pid` with PID-reuse
  guard (D-15), send SIGTERM, wait `cancel_grace_seconds`.
- **`app`**: call `manager.stop_spawn(status="cancelled")` in-process
  if the caller is in the same FastAPI worker, otherwise route through
  HTTP `POST /api/spawns/{id}/cancel`.

**Observable.** For CLI spawns: `os.kill(runner_pid, SIGTERM)` once;
`terminal_origin == "runner"`. For app spawns: `stop_spawn` called
directly; `terminal_origin == "runner"` (app IS the runner).

### CAN-003 — Cancel grace period is bounded; no SIGKILL escalation

**When** the runner has not finalized the spawn within
`cancel_grace_seconds` after CAN-002 sends SIGTERM,
**the canceller shall** return 503 (HTTP) or print "spawn did not
terminate within grace; reaper will reconcile" (CLI). No SIGKILL is
ever sent by the cancel pipeline.

**Observable.** `cancel_grace_seconds` defaults to 5s, configurable.
If the runner is truly hung, the reaper detects stale heartbeat + dead
process within `heartbeat_window` (120s) and reconciles with
`origin="reconciler"` (v2r2 D-13: SIGKILL removed from pipeline).

### CAN-004 — `POST /api/spawns/{id}/cancel` is a separate endpoint

**When** the AF_UNIX app server receives
`POST /api/spawns/{id}/cancel` on an active spawn,
**the app shall** invoke `SignalCanceller.cancel(spawn_id)` and respond:
- `200` with `{"ok": true, "status": "cancelled"}` once the spawn is
  terminal.
- `409` with `{"detail": "spawn already terminal: <status>"}` if already
  terminal at request time.
- `503` with `{"detail": "spawn is finalizing"}` if finalizing at grace
  expiry.
- `404` if the spawn does not exist.

All error responses use FastAPI's `detail` convention (v2r2 alignment
with HTTP-004).

**Observable.** HTTP status codes match the error-mapping table in
`spec/http_surface.md`.

### CAN-005 — `DELETE /api/spawns/{id}` is removed in favor of CAN-004

**When** any caller invokes `DELETE /api/spawns/{id}`,
**the app server shall** respond `405 Method Not Allowed` with
`{"detail": "use POST /api/spawns/{id}/cancel for lifecycle cancel"}`.

**Observable.** OpenAPI no longer advertises `DELETE /api/spawns/{id}`.

### CAN-006 — Control-socket `cancel` is removed

**When** the per-spawn control socket receives a JSON request with
`{"type": "cancel"}`,
**the control socket server shall** respond
`{"ok": false, "error": "cancel is not supported on the control socket;
use meridian spawn cancel <id>"}` and **shall not** route the request to
`SpawnManager`.

**Observable.** `inbound.jsonl` does not contain any `action: "cancel"`
entry. `SpawnManager.cancel()` is removed. CLI `spawn inject` removes the
`--cancel` flag.

### CAN-007 — Cancel is idempotent on terminal spawns

**When** any cancel surface (CAN-002, CAN-004) is invoked against a spawn
already in a terminal status,
**the canceller shall** return the existing terminal status without
side effects and **shall not** issue SIGTERM, append a finalize event,
or re-activate.

**Observable.** No new `SpawnFinalizeEvent` row. CLI exits 0 with
`Spawn '<id>' is already <status>`. HTTP returns `409` with
`{"detail": "spawn already terminal: <status>"}`.

### CAN-008 — Cancel under finalizing waits, never escalates

**When** cancel is invoked against a spawn whose status is `finalizing`,
**the canceller shall**:
1. Skip SIGTERM (runner already masked it during its critical section).
2. Poll for terminal-row emission for `cancel_grace_seconds`.
3. If terminal row appears, apply CAN-007 idempotency.
4. If grace expires while still finalizing, return 503 (HTTP) / print
   warning (CLI). Reaper reconciles eventually.

**Observable.** No SIGTERM or SIGKILL sent while `status == "finalizing"`.
Logs record `reason=finalizing_wait`. This is the same grace-expiry
behavior as CAN-003 (no SIGKILL in any path per D-13).

## Verification plan

### Unit tests
- `SignalCanceller` with mocked `os.kill` and spawn store:
  - Happy path (CLI spawn): SIGTERM → runner finalizes within grace → `origin="runner"`
  - Happy path (app spawn): in-process `manager.stop_spawn()` → `origin="runner"`
  - Grace expiry: SIGTERM → no finalize → returns 503 (no SIGKILL, D-13)
  - Already terminal: no signal, returns existing status
  - Finalizing gate: no SIGTERM, waits, returns 503 or terminal
  - PID-reuse: stale `runner_pid` with `create_time` mismatch → no signal
  - Two-lane dispatch: `launch_mode="foreground"` → SIGTERM; `launch_mode="app"` → in-process

### Smoke tests
- Scenario 1: `meridian spawn cancel <id>` on running spawn → cancelled
- Scenario 14: `POST /cancel` end-to-end → cancelled
- Scenario 15: `DELETE /api/spawns/{id}` → 405

### Fault-injection tests
- **Cancel-during-finalize**: spawn enters finalizing; canceller invoked;
  verify no signal sent, 503 returned, reaper eventually reconciles.
- **PID-reuse**: spawn exits, PID recycled; cancel invoked; verify no
  SIGTERM to the reused PID.
- **Concurrent cancel**: two cancel requests for the same spawn; verify
  exactly one finalize event, second gets idempotent response.
- **Grace-expiry on stuck runner**: runner hangs without finalizing;
  cancel waits grace, returns 503; reaper detects stale heartbeat within
  120s and reconciles.
- **App-managed cancel cross-process**: CLI invokes cancel on app-managed
  spawn; verify HTTP dispatch to app server, in-process stop_spawn call.
