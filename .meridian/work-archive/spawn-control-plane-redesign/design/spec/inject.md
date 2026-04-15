# Inject — Cooperative Text Delivery (Intra-Turn)

Inject is a **cooperative intra-turn operation** — it appends a user
message to the active streaming spawn so the harness can respond. Inject
is open to any caller that can reach the control socket or the AF_UNIX
HTTP endpoint; it carries no lifecycle authority and never finalizes.

## EARS Statements

### INJ-001 — Inject text is delivered to the harness without finalization

**When** the per-spawn control socket receives
`{"type": "user_message", "text": "<non-empty>"}` on an active spawn,
**the runner shall** append the message to `inbound.jsonl` and then call
`connection.send_user_message(text)` exactly once.

**Observable.** `inbound.jsonl` contains `action: "user_message"`,
`data.text == "<non-empty>"`, `source` matches the originating surface.
The harness emits a corresponding user-message item in `output.jsonl`.

### INJ-002 — Concurrent injects are linearizable per spawn

**When** two or more clients send simultaneous injects to the same spawn,
**the runner shall** serialize through a per-spawn asyncio mutex that
wraps (`record_inbound` + `send_to_harness`) so that:
1. `inbound.jsonl` order matches harness delivery order.
2. Each ack includes `inbound_seq` so clients can reconstruct ordering.
3. No injected messages are silently dropped.

**Ack ordering guarantee (v2r2 D-18):**
- **Control socket clients:** ack arrival order matches `inbound.jsonl`
  order (lock scope covers ack emission via `on_result` callback).
- **HTTP clients:** ack arrival order is NOT guaranteed to match
  `inbound.jsonl` order (independent connections). Clients use
  `inbound_seq` to reconstruct ordering.

**Observable.** Smoke scenario 8 passes — two parallel injects produce
matched `inbound.jsonl` + harness delivery ordering and distinct
`inbound_seq` values.

### INJ-003 — Inject acks a per-message handle

**When** the runner has written `inbound.jsonl` and dispatched to harness,
**the runner shall** respond with
`{"ok": true, "inbound_seq": <int>}` where `inbound_seq` is the
zero-based line index of the appended message.

**Observable.** Concurrent clients see distinct `inbound_seq` values.

### INJ-004 — Inject rejects when the spawn is terminal

**When** the inject surface is invoked against a terminal spawn,
**the surface shall** reject with `{"ok": false, "error": "spawn not
running: <status>"}` and **shall not** contact the runner.

**Observable.** CLI exits 1. HTTP returns 410.

### INJ-005 — HTTP inject schema mirrors CLI

**When** the AF_UNIX app server receives `POST /api/spawns/{id}/inject`,
**the app shall** accept exactly one of:
1. `{"text": "<non-empty>"}` — equivalent to INJ-001
2. `{"interrupt": true}` — equivalent to INT-005

and **shall** reject:
- Schema violations (missing fields, wrong types) with HTTP 422.
- Semantic violations (text + interrupt both set, neither set) with
  HTTP 400 (D-17 split).

**Observable.** OpenAPI lists both variants.

### INJ-006 — Inject does not require lifecycle authorization

**When** any caller reaches the inject surface with a valid request,
**the surface shall** dispatch without invoking the authorization guard.

**Observable.** Inject bypasses `AuthorizationGuard` by construction.
Safety rests on AF_UNIX filesystem permissions and per-spawn isolation.

## Verification plan

### Unit tests
- `InjectRequest` validates text / interrupt / both / neither.
- Per-spawn lock serializes two inject coroutines with correct seq ordering.

### Smoke tests
- Scenario 8: two parallel injects → distinct `inbound_seq`; control-socket
  ack order matches `inbound.jsonl` order.
- Scenario 9a: `POST /inject` with `{"text": "hi"}`.
- Scenario 9c: `POST /inject` with both text and interrupt → 400.

### Fault-injection tests
- **Concurrent inject ordering**: three clients inject simultaneously;
  verify `inbound.jsonl` order matches harness delivery, control-socket
  ack order matches that sequence, and HTTP clients receive distinct
  `inbound_seq` values with no drops.
