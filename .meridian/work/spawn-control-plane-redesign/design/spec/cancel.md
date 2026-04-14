# Cancel — Signal-Based Lifecycle Termination

Cancel is a **lifecycle operation**: the spawn must end as `cancelled`,
regardless of which surface initiated the cancel and regardless of whether
the harness happens to exit cleanly when asked to stop. Cancel never lives on
the per-spawn control socket; it lives at the OS process layer so the same
mechanism serves CLI, HTTP, and external timeout-based killers.

## Triggers covered

| Trigger | Surface |
|---|---|
| User runs `meridian spawn cancel <id>` | CLI |
| HTTP client calls `POST /api/spawns/{id}/cancel` | App server |
| External supervisor sends SIGTERM to the runner process | OS |
| Authorized child agent invokes a gated cancel tool | Agent runtime |

## EARS Statements

### CAN-001 — SIGTERM to the runner finalizes as cancelled

**When** the process identified by `runner_pid` on a non-terminal `SpawnRecord`
receives `SIGTERM`,
**the runner process shall** finalize the spawn with
`status="cancelled"`, `exit_code=143`, `origin="runner"`, `error="cancelled"`,
**before** its own process exits.

**Observable.** A single `SpawnFinalizeEvent` row in `spawns.jsonl` with
`status="cancelled"`, `origin="runner"`, `exit_code=143`, written before the
runner process is reaped.

### CAN-002 — `meridian spawn cancel` resolves the runner PID and SIGTERMs it

**When** `meridian spawn cancel <id>` is invoked against a non-terminal
streaming spawn,
**the CLI shall** resolve the target process to `runner_pid` (preferring the
runner over `worker_pid` for streaming spawns), send a single `SIGTERM`, wait
up to `cancel_grace_seconds` for the runner to finalize, and then send
`SIGKILL` to the runner if it is still alive.

**Observable.** `os.kill(runner_pid, SIGTERM)` is issued exactly once on the
happy path; `SpawnRecord.terminal_origin == "runner"` after the runner exits
within grace. If grace expires, `terminal_origin == "cancel"` is permitted as
the fallback.

### CAN-003 — Cancel grace period is bounded

**When** the runner has not finalized the spawn within
`cancel_grace_seconds` after CAN-002 sends SIGTERM,
**the canceller shall** send `SIGKILL` to `runner_pid` and write
`finalize_spawn(status="cancelled", origin="cancel", exit_code=137,
error="cancel_force_killed")` to durably record the forced termination.

**Observable.** `cancel_grace_seconds` defaults to 5s, configurable via
`MeridianConfig`. Logs include `reason=cancel_force_killed` when the fallback
fires.

### CAN-004 — `POST /api/spawns/{id}/cancel` is a separate endpoint

**When** the FastAPI app receives `POST /api/spawns/{id}/cancel` on an active
spawn,
**the app shall** invoke the same cancel pipeline used by CAN-002 (resolve
`runner_pid` → SIGTERM → bounded grace → SIGKILL fallback) and respond with
`{"ok": true, "status": "cancelled"}` once the spawn record reaches a
terminal `cancelled` state.

**Observable.** The HTTP request returns 200 only after the record's terminal
status is `cancelled`. The request returns 409 if the spawn is already
terminal at request time, with `{"ok": false, "status": <terminal_status>}`.
The request returns 404 if the spawn does not exist.

### CAN-005 — `DELETE /api/spawns/{id}` is removed in favor of CAN-004

**When** any caller invokes `DELETE /api/spawns/{id}`,
**the app server shall** respond `405 Method Not Allowed` with
`{"detail": "use POST /api/spawns/{id}/cancel for lifecycle cancel"}`.

**Observable.** OpenAPI no longer advertises `DELETE /api/spawns/{id}`.

### CAN-006 — Control-socket `cancel` is removed

**When** the per-spawn control socket receives a JSON request with
`{"type": "cancel"}`,
**the control socket server shall** respond
`{"ok": false, "error": "cancel is not supported on the control socket; use
meridian spawn cancel <id>"}` and **shall not** route the request to
`SpawnManager`.

**Observable.** `inbound.jsonl` does not contain any `action: "cancel"`
entry. `SpawnManager.cancel()` is removed from the public manager surface.
The CLI `spawn inject` command removes the `--cancel` flag.

### CAN-007 — Cancel is idempotent on terminal spawns

**When** any cancel surface (CAN-002, CAN-004) is invoked against a spawn
already in a terminal status,
**the canceller shall** return success with the existing terminal status and
**shall not** issue a second SIGTERM, append a second finalize event, or mark
the spawn re-active.

**Observable.** No new `SpawnFinalizeEvent` row appears. CLI exits 0 with
`Spawn '<id>' is already <status>`. HTTP returns 409 with the existing
terminal status payload.

### CAN-008 — Cancel under finalizing is honored once finalize completes

**When** cancel is invoked against a spawn whose status is `finalizing`,
**the canceller shall** wait up to `cancel_grace_seconds` for the runner to
finish its critical section (signed by SIGTERM mask) and then re-evaluate.

**Observable.** No SIGKILL is sent while `status == "finalizing"`. If the
runner emits a terminal event during the wait, CAN-007 idempotency applies.
If grace expires while still `finalizing`, the canceller returns 503 with
`{"detail": "spawn is still finalizing"}`; existing reaper rules eventually
reconcile it.
