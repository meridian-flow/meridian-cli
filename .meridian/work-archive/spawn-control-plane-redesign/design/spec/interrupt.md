# Interrupt — Non-Fatal Intra-Turn Stop

Interrupt is an **intra-turn operation**: it stops the current turn's
generation or tool call but leaves the harness connection open. The spawn
remains active and accepts follow-up `inject` (text or interrupt) without
finalization. Interrupt is the only way to stop a runaway turn without
ending the spawn lifecycle.

Per-harness behavior verified in P10: codex, claude, and opencode all
keep the connection alive after interrupt. The only thing making interrupt
fatal was the runner's classifier bug (#28).

## EARS Statements

### INT-001 — Interrupt stops the current turn without finalization

**When** the per-spawn control socket receives `{"type": "interrupt"}` on
an active streaming spawn,
**the runner shall** request the harness to interrupt its current turn,
record the action to `inbound.jsonl`, and **shall not** transition the
spawn to any terminal status.

**Observable.** After ack, `SpawnRecord.status == "running"`,
`control.sock` still exists, and `meridian spawn show` reports running.
`inbound.jsonl` contains a single `action: "interrupt"` entry.

### INT-002 — `turn/completed` with `status="interrupted"` is non-terminal

**When** the streaming runner observes a harness event whose payload
indicates the **turn** ended due to interruption (codex
`turn/completed` with `turn.status == "interrupted"`, claude `result`
whose interrupt flag is set, or the opencode equivalent),
**the runner shall** treat the event as non-terminal at the **spawn**
level and **shall not** populate `terminal_event_future`.

**Observable.** `_terminal_event_outcome` returns `None` for these
payloads. The drain loop continues. No `manager.stop_spawn(...)` call
fires from the terminal-event branch.

### INT-003 — Interrupt is followed by a usable connection

**When** an interrupt has been acknowledged (INT-001) and the harness has
acknowledged the interrupt,
**the runner shall** be ready to accept a subsequent
`{"type": "user_message"}` or `{"type": "interrupt"}` on the same
control socket, and **shall** route a follow-up `user_message` as a fresh
turn without rejecting on `spawn not running`.

**Observable.** Smoke: after `spawn inject <id> --interrupt`, running
`spawn inject <id> 'follow-up'` succeeds and produces a fresh turn.

### INT-004 — Interrupt is allowed when no turn is in flight

**When** an interrupt is received and the harness reports no current turn,
**the runner shall** acknowledge with `{"ok": true, "noop": true}` and
**shall not** error.

**Observable.** Repeated interrupts during idle return
`{"ok": true, "noop": true}`. No `inbound.jsonl` entries beyond the
first per cluster.

### INT-005 — HTTP interrupt parity

**When** the AF_UNIX app server receives
`POST /api/spawns/{id}/inject` with `{"interrupt": true}` (and no `text`),
**the app shall** invoke the same interrupt path as INT-001 via the
active `SpawnManager` and respond with `{"ok": true}`.

**Observable.** Schema accepts either `text` xor `interrupt: true`, never
both. HTTP returns 200 on success, not 422 for missing `text`.

### INT-006 — Interrupt is mutually exclusive with text in one request

**When** an inject request specifies both `text` (non-empty) and
`interrupt: true`,
**the receiving surface (CLI, control socket, HTTP) shall** reject with a
structured error and **shall not** apply either action.

**Observable.** CLI prints
`Error: message text is mutually exclusive with --interrupt`. HTTP returns
400. Control socket replies `{"ok": false, ...}`.

### INT-007 — Per-spawn interrupt-and-inject ordering is linearizable

**When** an interrupt and a follow-up text message are sent concurrently,
**the runner shall** apply them in FIFO order (per-spawn lock). Both
`inbound.jsonl` order and harness-side delivery order remain aligned.

**Observable.** Same per-spawn lock as INJ-002. Control-socket ack order
matches `inbound.jsonl` order; HTTP callers rely on `inbound_seq`. See
inject.md for the shared serialization contract.

## Verification plan

### Unit tests
- `_terminal_event_outcome` for codex `turn/completed interrupted` →
  returns `None`.
- `_terminal_event_outcome` for codex `turn/completed completed` → still
  returns `None` (turn events are never spawn-terminal).
- `_terminal_event_outcome` for `session.error` → returns `failed`.
- Per-spawn lock serializes two simultaneous coroutines.

### Smoke tests
- Scenario 2: `spawn inject <id> --interrupt` → spawn stays running,
  follow-up text inject acked, fresh assistant turn.
- Scenario 8: double inject → both messages acked with distinct
  `inbound_seq`; control-socket ack order matches `inbound.jsonl`.
- Scenario 9b: HTTP interrupt parity.

### Fault-injection tests
- **Interrupt during no-turn**: verify noop ack, no state change.
- **Rapid interrupt+inject**: inject immediately after interrupt, verify
  ordering matches and spawn stays alive.
