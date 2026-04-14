# Inject — Cooperative Text Delivery (Intra-Turn)

Inject is a **cooperative intra-turn operation** — it appends a user message
to the active streaming spawn so the harness can respond. Inject is open to
any caller that can reach the control socket or the HTTP endpoint; it carries
no lifecycle authority and never finalizes the spawn.

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

**When** two or more clients open simultaneous control-socket connections to
the same spawn and each sends an inject (text or interrupt),
**the runner shall** serialize the writes through a per-spawn asyncio mutex
that wraps the (`record_inbound` + `send_to_harness`) pair, so that
`inbound.jsonl` order is the order acked back to clients **and** the order
delivered to the harness.

**Observable.** Smoke scenario 8 passes — two parallel injects produce
matched ordering across `inbound.jsonl`, `output.jsonl`, and the assistant
acknowledgements. No injected messages are silently dropped.

### INJ-003 — Inject acks a per-message handle

**When** the runner has written `inbound.jsonl` and dispatched the message to
the harness,
**the runner shall** respond on the control socket with
`{"ok": true, "inbound_seq": <int>}` where `inbound_seq` is the
zero-based line index of the message it appended.

**Observable.** Concurrent clients see distinct `inbound_seq` values; CLI
text-mode output is unchanged for human use, JSON output exposes the seq.

### INJ-004 — Inject rejects when the spawn is terminal

**When** the inject surface is invoked against a spawn that is terminal at
request time,
**the surface shall** reject with `{"ok": false, "error": "spawn not
running: <status>"}` and **shall not** open a connection or attempt to
contact the runner.

**Observable.** CLI exits 1 with the same error string. HTTP returns 410
with `{"detail": "spawn not running: <status>"}`.

### INJ-005 — HTTP inject schema mirrors CLI

**When** the FastAPI app receives `POST /api/spawns/{id}/inject`,
**the app shall** accept exactly one of:
1. `{"text": "<non-empty>"}` — equivalent to INJ-001
2. `{"interrupt": true}` — equivalent to INT-005

and **shall** reject any other shape with HTTP 422 and an error message that
names the supported request shapes.

**Observable.** Smoke scenarios 9a/9b pass. OpenAPI schema lists both
variants.

### INJ-006 — Inject does not require lifecycle authorization

**When** any caller reaches the inject surface with a valid request,
**the surface shall** dispatch the inject without invoking the cancel/
interrupt authorization gate from `spec/authorization.md`.

**Observable.** Inject is the only cooperative surface; the
`AuthorizationGuard` defined in the architecture doc is bypassed by
construction for inject. Inject's safety story rests on the CLI/HTTP being
local-only and on per-spawn isolation, not on caller identity.
