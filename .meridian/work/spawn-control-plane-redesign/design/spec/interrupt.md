# Interrupt — Non-Fatal Intra-Turn Stop

Interrupt is an **intra-turn operation**: it stops the current turn's
generation or tool call but leaves the harness connection open. The spawn
remains active and accepts follow-up `inject` (text or interrupt) without
finalization. Interrupt is the only way to stop a runaway turn without
ending the spawn lifecycle.

## EARS Statements

### INT-001 — Interrupt stops the current turn without finalization

**When** the per-spawn control socket receives `{"type": "interrupt"}` on an
active streaming spawn,
**the runner shall** request the harness to interrupt its current turn,
record the action to `inbound.jsonl`, and **shall not** transition the spawn
to any terminal status.

**Observable.** After ack, `SpawnRecord.status == "running"`,
`control.sock` still exists, and `meridian spawn show` reports the spawn as
running. `inbound.jsonl` contains a single `action: "interrupt"` entry.

### INT-002 — `turn/completed` with `status="interrupted"` is non-terminal

**When** the streaming runner observes a harness terminal event whose payload
indicates the **turn** ended due to interruption (codex `turn/completed` with
`turn.status == "interrupted"`, claude `result` whose `terminal_reason`
indicates an interrupt, or the opencode equivalent),
**the runner shall** treat the event as non-terminal at the **spawn** level
and **shall not** populate `terminal_event_future`.

**Observable.** `_terminal_event_outcome` returns `None` for these payloads.
The drain loop continues consuming events. No `manager.stop_spawn(...)` call
fires from the terminal-event branch.

### INT-003 — Interrupt is followed by a usable connection

**When** an interrupt has been acknowledged (INT-001) and the harness has
acknowledged the interrupt at its level (e.g., codex `turn/completed
interrupted`),
**the runner shall** be ready to accept a subsequent
`{"type": "user_message"}` or `{"type": "interrupt"}` on the same control
socket, and **shall** route a follow-up `user_message` as a fresh `turn/start`
(or harness equivalent) without rejecting on
`spawn not running`.

**Observable.** Smoke scenario: after `meridian spawn inject <id> --interrupt`,
running `meridian spawn inject <id> 'follow-up'` succeeds and the spawn
produces a fresh assistant turn.

### INT-004 — Interrupt is allowed when no turn is in flight

**When** an interrupt is received and the harness reports no current turn id,
**the runner shall** acknowledge with `{"ok": true, "noop": true}` and
**shall not** error.

**Observable.** Idempotency test: repeated interrupts during idle return
`{"ok": true, "noop": true}` and produce no `inbound.jsonl` entries beyond
the first per cluster.

### INT-005 — HTTP interrupt parity

**When** the FastAPI app receives `POST /api/spawns/{id}/inject` with
`{"interrupt": true}` (and no `text`),
**the app shall** invoke the same interrupt path as INT-001 via the active
`SpawnManager` and respond with `{"ok": true}` once the manager has dispatched
the interrupt to the harness.

**Observable.** Smoke scenario 9b passes. The HTTP request is **not** rejected
with 422 for missing `text`. Schema for `InjectRequest` accepts either `text`
xor `interrupt: true`, never both.

### INT-006 — Interrupt is mutually exclusive with text in one request

**When** an inject request specifies both `text` (non-empty) and
`interrupt: true`,
**the receiving surface (CLI, control socket, HTTP) shall** reject the
request with a structured error and **shall not** apply either action.

**Observable.** CLI prints
`Error: message text is mutually exclusive with --interrupt`. HTTP returns
400 with `{"detail": "text and interrupt are mutually exclusive"}`. Control
socket replies `{"ok": false, "error": "text and interrupt are mutually
exclusive"}`.

### INT-007 — Per-spawn interrupt-and-inject ordering is linearizable

**When** an interrupt and a follow-up text message are sent concurrently on
the same spawn from two clients,
**the runner shall** apply them in the order they were accepted onto the
control socket queue (per-spawn FIFO), so that `inbound.jsonl` order matches
the harness-side delivery order.

**Observable.** Same per-spawn lock as INJ-002. See `inject.md` for the
shared serialization contract.
