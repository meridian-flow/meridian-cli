# Fresh Design Round: Agent Shell MVP (3-Phase)

## Context

This is a **fresh design round from scratch** for the `agent-shell-mvp` work item. The previous `design/` subtree was built under a stale framing (meridian-flow as Go backend consumer) and has been archived per D44. Do NOT reference anything in `design.archived/`. Start fresh against the updated `requirements.md`.

The authoritative inputs are:

- **`requirements.md`** — current source of truth. Read this first and internalize the 3-phase scope, validation context, and constraints.
- **`decisions.md`** — D41 through D44 are the most recent decisions (end of file). D41 is the scope reframe. D42 is WebSocket transport. D43 is AG-UI Python SDK adoption. D44 is the archive decision. Earlier decisions (D1-D40) provide historical context but many are superseded by D41.
- **`findings-harness-protocols.md`** — authoritative reference for what each harness can actually do (tier-1 determination, mid-turn capability).

## What To Design

A complete design tree for the 3-phase `meridian app` MVP:

### Phase 1 — Bidirectional streaming foundation

The highest-risk, most architecturally load-bearing phase. Each harness has a **different WebSocket topology**:

- **Claude Code**: `--sdk-url ws://localhost:<port>` — Claude CLI connects to OUR WebSocket server as a client. Bidirectional NDJSON. We send `user` messages; Claude sends `assistant`, `stream_event`, `tool_progress`, `result`. Stability concern: `--sdk-url` is reverse-engineered, not officially documented. Hybrid fallback exists (WS receive + HTTP POST send). Reference: the companion reversed protocol doc linked in requirements.md.
- **Codex**: `--listen ws://IP:PORT` — Codex runs a WebSocket server, we connect as a client. JSON-RPC 2.0, one message per WS text frame. Mid-turn injection via `turn/steer` (appends to in-flight turn). Also `turn/start`, `turn/interrupt`. Schema generation available.
- **OpenCode**: HTTP + ACP over stdio currently. WebSocket proposed (issue #13388). Design must check if merged; if not, use HTTP for MVP.

The adapter abstraction must hide these topology differences (server vs client vs HTTP) behind a uniform `HarnessSender` / `HarnessReceiver` interface. This is the SOLID requirement's most load-bearing surface.

**`meridian spawn inject <spawn_id> "message"` is hard-committed to Phase 1.** It's the same mechanism the Phase 2 UI routes through. Phase 1 = control layer; Phase 2 = presentation layer over the control layer.

**Critical design task**: map the actual refactoring scope against the existing `src/meridian/lib/harness/` and `src/meridian/lib/launch/` layers. How much of the existing code can stay, and how much needs replacement? The shift from "fire-and-forget subprocess + stdout capture" to "bidirectional WebSocket sessions" may be substantial.

### Phase 2 — Python FastAPI WebSocket server with AG-UI translation

FastAPI app, one WebSocket endpoint, reads from Phase 1's control layer, translates harness wire format into `ag_ui.core` event shapes (from `ag-ui-protocol` PyPI package per D43), streams to clients. Routes inbound WS frames into the control layer.

The Go server at `meridian-flow/backend/internal/service/llm/streaming/` is the **semantic reference** for when to emit which event, how state snapshots work, how tool calls order relative to text. Read it for emission semantics; do NOT port its types (they come from the Python SDK). The key files to mine: `emitter.go`, `stream_executor.go`, `block_processor.go`, `tool_executor.go`, `cancel_handler.go`, `catchup.go`.

Also read `agent-framework-ag-ui` on PyPI as a template for how the FastAPI+AG-UI pattern looks in idiomatic Python. Do not depend on it.

### Phase 3 — React UI (`meridian app`)

Adapted from `frontend-v2` in `meridian-collab/frontend-v2/`. Design must enumerate what stays / cuts / extends. Primary validation is dogfooding (developer using it to build meridian itself, not a non-technical researcher). Secondary validation is biomedical.

## Key Constraints (from requirements.md, do not re-litigate)

- Python-native MVP, no Go backend, no meridian-flow
- WebSocket transport (D42), not SSE+POST
- `ag-ui-protocol` Python SDK for event types (D43), not hand-ported
- SOLID harness abstraction with ISP, DIP, OCP, LSP, SRP
- Localhost, single user, no auth, no cloud
- `meridian spawn inject` hard-committed to Phase 1
- Extensible adapter/DI pattern — swap one harness for another on any spawn

## Reference Reading

All listed in requirements.md "Reference Reading" section. Delegate to @explorer spawns for volume. The most important ones:

1. `src/meridian/lib/harness/` — existing adapter code, launch mechanics, what changes
2. Go server in `meridian-flow/backend/internal/service/llm/streaming/` — AG-UI emission semantics
3. `meridian-collab/frontend-v2/` — React component tree for Phase 3
4. `ag-ui-protocol` Python SDK docs at https://docs.ag-ui.com/sdk/python/core/overview

## Review Requirements

Include `@refactor-reviewer` in the design review fan-out. The harness abstraction is a structural hot spot — refactor hygiene matters here more than anywhere else in the design. Fan out across diverse models per `agent-staffing` skill.

## What Not To Do

- Do not reference `design.archived/` — it's stale.
- Do not propose rewriting meridian-channel out of Python.
- Do not propose a FIFO control protocol — those were D37 deliverables, stale under D41.
- Do not propose streaming as a separate invocation mode/flag — it's universal.
- Do not design for cloud deployment, auth, multi-user, or session persistence.
- Do not bake domain-specific behavior (biomedical, PyVista) into the shell or protocol. Domain lives in agent profiles + skills + interactive tools.
