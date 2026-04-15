# Reviewer: external contract fidelity on agent-shell-mvp rewritten design tree

## Context

The `agent-shell-mvp` work item in meridian-channel was **reframed** per D34–D40. The reframed scope is: meridian-channel's harness adapters will emit AG-UI events, gain a streaming spawn mode with a stdin control protocol, and expose a `meridian spawn inject` CLI primitive. The AG-UI event taxonomy, 3-WS topology, and per-tool behavior config live in **meridian-flow**, not here — meridian-channel's job is to *emit events that fit* the contract meridian-flow already defines.

Your job is to check whether the rewritten design tree **correctly references the external contract** and **doesn't drift from it**. This is a cross-repository fidelity review.

## What to read

### The external contract (read-only, canonical)

Read these before evaluating the meridian-channel design tree. They are the source of truth — the meridian-channel tree must match them.

1. `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md` — **primary reference**. End-to-end AG-UI event sequence during a turn, with traces.
2. `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md` — 3-WS topology, hooks, streaming reducer contract.
3. `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/foundations.md`
4. `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/state-management.md`
5. `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/thread-model.md`
6. `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/backend/python-tool.md` — per-tool config example (python: stdout visible inline)
7. `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/backend/bash-tool.md` — per-tool config example (bash: everything collapsed)
8. `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/backend/display-results.md` if present — DISPLAY_RESULT + TOOL_OUTPUT payload contracts

### The meridian-channel side

1. `$MERIDIAN_WORK_DIR/reframe.md` — corrected framing
2. `$MERIDIAN_WORK_DIR/decisions.md` D34–D40 — basis decisions (D36 especially)
3. `$MERIDIAN_WORK_DIR/findings-harness-protocols.md` — harness protocol authority
4. The rewritten design tree:
   - `$MERIDIAN_WORK_DIR/design/overview.md`
   - `$MERIDIAN_WORK_DIR/design/harness/overview.md`
   - `$MERIDIAN_WORK_DIR/design/harness/abstraction.md`
   - `$MERIDIAN_WORK_DIR/design/harness/adapters.md`
   - `$MERIDIAN_WORK_DIR/design/harness/mid-turn-steering.md`
   - `$MERIDIAN_WORK_DIR/design/events/overview.md`
   - `$MERIDIAN_WORK_DIR/design/events/flow.md`
   - `$MERIDIAN_WORK_DIR/design/events/harness-translation.md`

## Focus: external contract fidelity

### 1. Reference, don't duplicate (D36)

meridian-channel must **reference** meridian-flow's AG-UI schema, not redefine it. Flag any place where:
- The rewritten tree restates the AG-UI event taxonomy as if it were owned here
- The rewritten tree invents event types that don't exist in meridian-flow's `streaming-walkthrough.md`
- The rewritten tree defines per-tool behavior config values that contradict `python-tool.md` / `bash-tool.md`
- The rewritten tree introduces a parallel "meridian-channel normalized schema" — D36 explicitly rejected this

### 2. Event taxonomy correctness

Cross-check every AG-UI event name and field referenced in `events/flow.md` and `events/harness-translation.md` against meridian-flow's `streaming-walkthrough.md`. Flag:
- Events named differently from the canonical source
- Event sequencing that doesn't match the canonical walkthrough
- Missing events that the walkthrough emits
- Extra events the walkthrough doesn't define

### 3. 3-WS topology

The data flow between the streaming spawn and meridian-flow's backend/frontend goes through Agent WS. The meridian-channel design should NOT try to redefine which WS carries what — it should only say "our streaming output is what the Agent WS carries" and link to `data-flow.md`. Flag any place where the design tries to own 3-WS topology decisions.

### 4. Per-tool behavior config shape

`python-tool.md` and `bash-tool.md` define the exact shape of per-tool render config (`input: visible|collapsed`, `stdout: visible|collapsed|inline`, `stderr: ...`). The harness adapters docs and `events/harness-translation.md` describe how each adapter attaches this config to `TOOL_CALL_START`. Flag:
- Config key names that diverge from meridian-flow's canonical shape
- Config values that contradict the canonical examples (e.g., bash not collapsed, python stdout not inline)
- Made-up config fields that meridian-flow doesn't define
- Invented tool names or misattributed tool names per harness

### 5. CAPABILITY event

The design has the adapter emit a `CAPABILITY` event after `RUN_STARTED` declaring its `mid_turn_injection` semantic. Check whether this is a meridian-flow-defined event or a meridian-channel invention. If it's an invention, it needs to be flagged as a coordination point with meridian-flow (it's fine to propose, but the design should be honest that it's a proposed extension, not an existing event).

### 6. harness-protocols grounding

`findings-harness-protocols.md` is authoritative on:
- Claude stream-json NDJSON format
- Codex JSON-RPC 2.0 over stdio with `item/*` notifications
- OpenCode HTTP session events (SSE)
- Mid-turn steering semantics: Claude queues, Codex interrupt-restarts, OpenCode HTTP POSTs
- All three harnesses are tier-1
- Companion's `codex-adapter.ts` is a reference, not a dependency

Flag any place where the rewritten docs contradict this — especially any language calling Codex experimental/deferred, or any treatment of mid-turn steering as optional/V2.

### 7. In-process harness scope

`direct.py` (in-process Anthropic Messages API) should be **out of scope** — it stays non-streaming. Flag if the design tries to sweep it in.

### 8. Control protocol fidelity

The stdin control frame model (`user_message`, `interrupt`, `cancel`) is a meridian-channel invention (it's what we're designing). It needs to:
- Match D37's direction
- Include a version field from day one (D37 open question #2)
- Translate cleanly into each harness's native injection mechanic per findings-harness-protocols.md

Flag any mismatch between the control-frame model in `mid-turn-steering.md` and the per-harness mechanics in `adapters.md` or `harness-translation.md`.

## Anti-patterns to avoid in your review

- Don't fault the meridian-channel design for something that's actually a gap in the meridian-flow contract (if meridian-flow doesn't define a DISPLAY_RESULT subtype, it's a coordination issue, not a meridian-channel error)
- Don't demand exhaustive event-by-event traces in the meridian-channel design; it's meant to be a translation layer, not a re-explanation of the canonical walkthrough
- Don't propose that the meridian-channel design should own things that belong to meridian-flow

## Report format

Structured report with findings ranked by severity:

- **Blocker** — meridian-channel design contradicts the meridian-flow external contract, restates schema it should reference, or contradicts findings-harness-protocols.md
- **Concern** — a reference that's incorrect, incomplete, or would confuse an implementer
- **Coordination** — a point where the meridian-channel design proposes a new thing (like the CAPABILITY event shape) that meridian-flow needs to agree to; this is not a meridian-channel bug but needs to be called out so the handoff is clean
- **Nit** — wording or link-target improvements

For each finding: cite the file + section in meridian-channel, quote the specific language, and cite the matching meridian-flow file + section the claim conflicts with (or should reference).
