# Agent Shell MVP — Requirements

> **Revised 2026-04-08** from conversation `c1135`. Supersedes the earlier
> iteration in this file's git history. The authoritative decision trail is
> `decisions.md` (through D44 at time of writing); this document is the
> current source of truth for the **next design round** produced by
> `@design-orchestrator` from scratch after `design/` is archived per D44.
>
> Read this first. Mine the parent session and `decisions.md` for nuance on
> specific decisions.

## What This Is

Build a **domain-flexible agent shell** — `meridian app` — that runs locally
on a user's machine, wraps Claude Code / Codex / OpenCode subprocesses as
session-lived orchestrators, and provides a polished web UI for end users to
interact with them. The shell is generic; **domain specialization happens
through agent profiles, skills, and interactive tools — never through
hardcoded shell behavior.**

This work item lives in `meridian-channel`. There is **no separate Go backend
during MVP**. Python FastAPI serves both the API (WebSocket to frontend) and
owns the spawn lifecycle via the Phase 1 bidirectional streaming layer,
in-process. The UI is React, adapted from `frontend-v2`, copied into this
repo.

Post-MVP cleanup will revisit language choice — the Go CLI rewrite is a
committed direction post-validation, tracked in the `post-mvp-cleanup` work
item — but the MVP itself is pure Python.

## MVP Scope: Three Sequenced Phases

Per **D41**. Each phase has a verifiable gate; nothing downstream starts
until the gate is green.

### Phase 1 — Bidirectional streaming foundation, all three harnesses

Every harness adapter in `src/meridian/lib/harness/` gains the ability to
write to the subprocess's input channel while it's reading from the output.
**Not a flag. Not a mode. Not a new invocation shape.** The underlying
mechanism is universal and always available; fire-and-forget spawns still
work exactly as they do today if the caller ignores the input side.

Affects all three tier-1 harnesses. Per-harness injection mechanism
(researched April 2026; sources: companion reversed protocol doc, Codex
app-server official docs, OpenCode issue tracker):

- **Claude Code** — use `--sdk-url ws://localhost:<port>` mode. Claude CLI
  connects to **our WebSocket server** as a client. Bidirectional NDJSON
  over WebSocket. We send `user` type messages; Claude sends `assistant`,
  `stream_event`, `tool_progress`, `tool_use_summary`, `result`. The `-p`
  arg is ignored — Claude waits for the first `user` message over WS.
  Auth via `CLAUDE_CODE_SESSION_ACCESS_TOKEN` env var. MCP channels (Tengu
  Harbor) available for MCP server integration, but user message injection
  is simply the `user` message type on the main channel. **Stability
  concern**: `--sdk-url` is reverse-engineered from companion, not
  officially documented by Anthropic. The design must flag this risk and
  note the hybrid fallback (WebSocket receive-only + HTTP POST for sending
  via `CLAUDE_CODE_POST_FOR_SESSION_INGRESS_V2`). Reference:
  https://github.com/The-Vibe-Company/companion/blob/main/WEBSOCKET_PROTOCOL_REVERSED.md
- **Codex** — use `--listen ws://IP:PORT` (experimental). Codex runs a
  **WebSocket server**; our process connects as a client. JSON-RPC 2.0,
  one message per WebSocket text frame. Mid-turn injection via
  **`turn/steer`** — appends user input to the active in-flight turn
  (requires `expectedTurnId`; does NOT restart the turn). Also:
  `turn/start` (new turn), `turn/interrupt` (cancel in-flight turn).
  Schema generation available: `codex app-server generate-json-schema`.
  Reference: https://developers.openai.com/codex/app-server
- **OpenCode** — currently HTTP + ACP over stdio (nd-JSON). WebSocket
  transport proposed in issue #13388 (`/acp` endpoint on existing server
  port). Design must check whether #13388 is merged in the current release;
  if yes, use WebSocket; if not, use HTTP/ACP for MVP and note WebSocket as
  a pending upgrade path. Reference: https://github.com/anomalyco/opencode/issues/13388

**Note: each harness has a different WebSocket topology.** Claude Code
makes our process the server; Codex and OpenCode (if WebSocket) make our
process the client. The adapter pattern must hide this topology difference
behind the uniform `HarnessSender` / `HarnessReceiver` interface. This is
the most load-bearing part of the SOLID abstraction.

**`meridian spawn inject <spawn_id> "message"` is hard-committed to Phase 1**
(not "ship if cheap, defer otherwise"). It is the **same mechanism** that
Phase 2's WebSocket endpoint routes through. Phase 1 builds the control
layer; Phase 2 wraps it in a UI-facing WebSocket. The inject CLI is the
smoke-test primitive for proving the control layer works, and it's
immediately useful for dev-workflow orchestrators steering children mid-turn.

**Gate**: all three harnesses pass manual smoke-test guides for mid-turn
injection — use `meridian spawn inject` to write a user message into a
running spawn, verify the harness received it and produced a visible
response change. Smoke test format per the `smoke-test` skill.

**Out of scope for Phase 1**: the FastAPI server, the UI-facing WebSocket,
the React UI, AG-UI event translation. Those are Phase 2 and 3.

### Phase 2 — Python FastAPI WebSocket server with AG-UI translation

A FastAPI application that:

1. Hosts a WebSocket endpoint — one endpoint, one lifecycle, one JSON frame
   format (per **D42**).
2. Launches or attaches to a meridian spawn using the Phase 1 bidirectional
   layer.
3. Reads harness wire output and maps it into `ag_ui.core` event shapes from
   the `ag-ui-protocol` Python SDK (per **D43**).
4. Sends those events over the WebSocket as JSON frames —
   `event.model_dump_json(by_alias=True, exclude_none=True)`.
5. Reads inbound WebSocket frames (`user_message`, `interrupt`, `cancel`) and
   routes them into the spawn's input channel.

**Event type AND emission semantics source**: the `ag-ui-protocol` PyPI
package and the AG-UI protocol documentation at
<https://docs.ag-ui.com/sdk/python/core/overview>. Pydantic models,
camelCase serialization, forward-compatible with upstream spec evolution.
The protocol docs define event lifecycle, emission order, and interaction
semantics canonically — use those, not the Go server implementation.
**Mapping source**: new per-harness code, written during Phase 2.

**Gate**: both test suites green.

- **Smoke tests** — end-to-end through the WebSocket, one per harness,
  verifying the full event lifecycle from `RUN_STARTED` to `RUN_FINISHED`
  including at least one mid-turn injection.
- **Unit tests** — the harness-wire-format → AG-UI mapping function for
  each harness, in isolation, with fixtures captured from real harness runs.
  Unit tests here are explicitly justified (and requested by the user) even
  though the project default leans smoke-over-unit, because the mapping
  function is a stable pure-ish transformation — exactly the kind of thing
  unit tests are cheap and valuable for.

### Phase 3 — React UI (`meridian app`)

A React application consuming the Phase 2 WebSocket. Adapted from
`frontend-v2`, copied into this repo. Provides:

- Activity stream rendering (AG-UI events → visual timeline).
- User input form that sends `user_message` / `interrupt` / `cancel` frames.
- Per-tool display config — reusing frontend-v2's existing
  `toolDisplayConfigs`-style registry, or replacing it if a better shape
  emerges during design.
- Capability-aware affordances — if adapters declare different mid-turn
  semantics (Claude queues to next turn, Codex interrupts, OpenCode
  POSTs), the UI renders the right send-button affordance per harness.

**Gate**: a single customer can run `meridian app`, interact with a Claude
Code spawn, see activity, inject mid-turn messages, and get meaningful
responses — end-to-end on their local machine.

**First release can ship Claude-Code-only in the UI** even though Phase 1
and Phase 2 proved all three harnesses. Codex and OpenCode in the UI are
incremental work after the first Claude Code demo validates.

## Non-Goals (post-mvp-cleanup)

Everything below is explicitly **not** MVP work. Tracked in the
`post-mvp-cleanup` backlog work item.

- **Go CLI rewrite.** Committed direction post-validation, not mid-MVP.
  Motivations: concurrency fit for orchestrating many connections,
  single-binary distribution story. See `post-mvp-cleanup/backlog.md`.
- **Consolidation of scattered code** across the four parallel repos
  (`meridian/`, `meridian-agents/`, `meridian-collab/`, `meridian-flow/`).
  MVP pulls in only what's needed for the demo.
- **Cloud deployment / auth / Supabase / Daytona / billing.** MVP is
  strictly localhost, single user, no persistence between processes.
- **Permission gating** (approve-before-tool-call UX). Useful but not
  MVP-blocking.
- **Session persistence and resume across process restarts.** MVP is
  single-session-per-process.
- **`meridian spawn inject` CLI as a standalone deliverable.** MOVED to
  Phase 1 hard-commit per user directive. No longer a non-goal. See
  Phase 1 section.
- **SSE transport path.** WebSocket-only per D42. `ag_ui.encoder.EventEncoder`
  remains available in the SDK but is not wired or tested.
- **Reconnect handling.** Manual refresh on disconnect is acceptable for
  the first customer release. Client-side `ReconnectingWebSocket` wrapper
  is post-MVP polish.

## Constraints That Are Not Up For Re-Debate

These are locked decisions. Design-orchestrator must optimize within them,
not re-litigate them.

### Python + FastAPI + WebSocket (D42)
New Python backend, FastAPI, WebSocket for 2-way streaming. No separate Go
backend during MVP. No meridian-flow subprocess adapter. The Python FastAPI
server owns the spawn lifecycle via Phase 1's bidirectional streaming layer,
in-process.

### `ag-ui-protocol` Python SDK for event types (D43)
Use the PyPI `ag-ui-protocol` package for AG-UI event types and serialization.
Do not port `events.go` from the Go server. The *mapping* from harness wire
format to AG-UI events is new work; the *event types themselves* are
imported.

### SOLID harness abstraction
The harness abstraction is load-bearing — get it wrong and adding a new
harness requires a backend rewrite. Required:

- **SRP** — `HarnessAdapter` knows how to lifecycle one specific harness.
  The event-mapping module knows the AG-UI shape. A router maps between them.
  Three concerns, three modules.
- **OCP** — adding a new harness = new adapter file + registration; zero
  modifications to router or mappers for existing harnesses.
- **ISP** — split the harness interface so consumers see only what they
  need: `HarnessLifecycle` (start/stop/health), `HarnessSender` (user
  message, interrupt, approve tool), `HarnessReceiver` (event stream out).
- **LSP** — adapters are interchangeable; swapping one for another is a
  config change, not a code change.
- **DIP** — FastAPI depends on the abstract `HarnessAdapter`, not on a
  concrete adapter.

Design the interface against the **least-common-denominator** of all three
harnesses. Do not warp it to fit Claude Code's `--sdk-url` shape
specifically. Each harness has a **different WebSocket topology** (Claude
Code makes our process the server; Codex and OpenCode make our process the
client). The adapter must hide this topology difference behind the uniform
interface. See Phase 1 section for per-harness mechanism details.

The existing single-shot harness adapters in `src/meridian/lib/harness/`
inform the new long-lived ones conceptually but do not bind them. **The
transition from fire-and-forget subprocess + stdout capture to bidirectional
WebSocket-based sessions is a significant architectural shift** that may
require substantial refactoring of the harness and launch layers. If the
existing code was designed with SOLID adapter boundaries, the refactoring
should be localized to adapter internals and launch mechanics. If not, the
refactoring surface is larger. The design-orchestrator must map the
actual refactoring scope before Phase 1 implementation starts.

### Python stays for the MVP
The Go CLI rewrite is post-mvp-cleanup, not mid-MVP. Design must not propose
or require rewriting meridian-channel out of Python for any part of the MVP
scope. See `post-mvp-cleanup/backlog.md` item 1 for the committed direction.

### Local Python venv is the execution runtime
- User installs Python + `uv` as a prerequisite (acceptable because Python
  is required for the validation domain anyway).
- The agent's `python` / `bash` tools execute against a local venv.
- Persistent kernel across tool calls where the validation domain needs it.
- **Not Daytona for MVP.** Single-user localhost.

### Files-as-authority
Meridian-channel's files-as-authority discipline extends cleanly into the
MVP: every user turn, every tool call, every agent response lands as files
under the work item directory. Design must preserve and amplify this — it's
load-bearing for validation domain reproducibility (the decision log
doubles as a methods section for the scientific audit trail).

## Validation Context

### Primary: Dogfooding — using `meridian app` to build meridian itself

The **primary validation** is self-referential: the user will use
`meridian app` to do the development work on meridian-channel. This
provides the tightest possible feedback loop — if the tool is useful for
building itself, it's useful. The first validation customer is the
developer (the user themselves).

**What this means for MVP design**: the UI does NOT need to be "so simple
a non-technical researcher can use it" for first validation. It needs to be
**better than the CLI** for orchestrating spawns and steering them mid-turn.
The test is: "does `meridian app` make meridian development faster than
`meridian spawn` + `meridian spawn show` + reading `output.jsonl`?"

Features that matter for dogfooding:
- See what a spawn is doing in real time (activity stream).
- Inject context / redirect mid-turn (Phase 1's core deliverable exposed
  through Phase 3's UI).
- See tool calls and their results as they happen.
- Multi-spawn visibility (eventually — may not be MVP-minimum).

### Secondary: Biomedical — μCT analysis for the Yao Lab

The second validation domain is **biomedical (μCT analysis for the Yao Lab
at University of Rochester, musculoskeletal research)**. The validation
customer is a real human being ("Dad") who uses Amira today and has a
year-long learning curve with it. The MVP is "good enough to do his actual
μCT pipeline on his actual data without fighting the tool."

**What this means for MVP design**: the Phase 3 UI must eventually be
usable by a non-technical researcher who does not touch a terminal and
does not write code. This is a **secondary** priority — Phase 3 ships
first to a developer dogfooding it, then gets polished for the biomedical
customer.

**Co-pilot, not autonomous.** The user ran a prototype attempt and found
the model can't do biomedical analysis blind. The actual product is
**co-pilot with feedback loops**: either agent self-feedback via off-screen
rendering + multimodal vision ("Path A") or human-in-the-loop interactive
correction via blocking interactive tools like PyVista point picking
("Path B"), or both. Phase 3 design must accommodate both paths.

**Interactive tool protocol** (preserved): domain-specific UX is delivered
through interactive Python tools the agent calls, not through custom UI
panels in the shell. Example: agent calls `pick_points_on_mesh()` → a
standalone PyVista window opens with rotate/zoom/pick widgets → user
clicks landmarks → window closes → tool returns coordinates as JSON →
agent continues. The shell renders chat + tool timeline + inline images,
generic; each domain ships agent profile + skills + interactive tools.

Biomedical V0 specifically ships: data-analyst agent profile + biomedical
skills + interactive PyVista tool(s) (point pick, box select, region pick).
Pivoting domain is "swap agent + skills + tools," not "rebuild the shell."

## Reference Reading For The Fresh Design Phase

The new `@design-orchestrator` spawn should mine these as grounding before
producing design artifacts. Delegate to `@explorer` spawns where the volume
warrants it.

### 1. This work item

- `decisions.md` — D1 through D44, authoritative decision trail. Read end
  to start (most recent first — D44, D43, D42, D41 — for fastest orientation
  on current framing, then walk backward for historical context).
- `findings-harness-protocols.md` — authoritative reference for harness
  mid-turn capabilities and tier-1 determination. Confirms all three
  harnesses support mid-turn injection.
- (The old `design/` subtree is **archived per D44** — do not read, do not
  reference; it was under the D34–D40 framing and is stale by default.)

### 2. meridian-channel source

- `src/meridian/lib/harness/` — existing single-shot adapters; informs the
  new long-lived adapters conceptually.
- `src/meridian/lib/harness/claude.py`, `codex.py`, `opencode.py` —
  baselines for how each harness is launched today and what changes Phase 1
  must make.
- `src/meridian/lib/launch/process.py`, `runner.py`, `stream_capture.py` —
  process launch / PTY / stream capture machinery. Phase 1 interacts here;
  the non-PTY launch shape for the new bidirectional path must not collide
  with existing parent-stdin → child-PTY copying.
- `src/meridian/lib/state/paths.py`, `spawn_store.py` — `.meridian/` state
  model. Phase 1 may need spawn_store extensions for per-spawn control
  metadata.
- `.agents/` loading and skill resolution — informs how MVP surfaces agent
  profiles to Claude Code at session start.

### 3. AG-UI protocol — primary source for emission semantics

- **AG-UI protocol docs** — <https://docs.ag-ui.com/sdk/python/core/overview>.
  Canonical source for event lifecycle, emission order, and semantic rules.
  Use this as the primary reference for how and when to emit AG-UI events.
- **`ag-ui-protocol` Python SDK** — the types themselves (Pydantic models),
  serialization, validation. See section 4 below.
- **`agent-framework-ag-ui`** on PyPI — reference implementation showing the
  orchestrator + event bridge + FastAPI pattern in idiomatic Python.

### 4. Go server (`meridian-flow/backend`, supplementary reference)

Supplementary to the AG-UI protocol docs — useful for seeing one concrete
implementation of the emission patterns, especially for edge cases the
protocol docs may not fully cover (catchup/reconnect, cancellation
sequencing, tool call ordering under concurrency). NOT the primary semantic
authority — the protocol docs and Python SDK are.

- `internal/service/llm/streaming/agui/` — events, emitter, id_factory
- `internal/service/llm/streaming/` — stream_executor, block_processor,
  tool_executor, cancel_handler, catchup
- `tests/smoke/websocket/thread-ws/streaming-lifecycle.md` — template for
  Phase 2 smoke tests

(Canonical source assumption: `meridian-flow/backend/` is the most
recently-touched of the four parallel repos with this code. Confirm during
design; `meridian-collab/backend/` has near-identical structure as a
fallback.)

### 5. `ag-ui-protocol` Python SDK

- PyPI: `ag-ui-protocol`
- Docs: <https://docs.ag-ui.com/sdk/python/core/overview>
- Event taxonomy reference — design should enumerate which subset of the
  full AG-UI taxonomy meridian-channel's harnesses actually emit for MVP
  workflows (likely `RUN_*`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `STEP_*`,
  `STATE_*`; possibly `REASONING_*` for Claude).
- Reference implementation pattern: `agent-framework-ag-ui` on PyPI
  (orchestrator → event bridge → FastAPI endpoint). Read as template; do
  not adopt as a dependency.

### 6. `frontend-v2` in `meridian-collab/frontend-v2/`

Canonical copy (most recently touched among the parallel repos; confirm
during design). Full directory is in scope — component tree, activity
stream reducer, WebSocket client, thread components, UI atoms. Phase 3
adapts this; design must enumerate what stays / cuts / extends.

Specifically worth inspecting:

- **Activity stream reducer** — already written against AG-UI event shapes;
  Phase 3 design should decide whether to preserve as-is or evolve.
- **WebSocket client** — currently speaks the Go backend's WebSocket
  contract; Phase 3 may need to point it at the new Python endpoint.
- **Thread components** — essential, keep.
- **UI atoms** — essential, keep.
- **Writing-app legacy** (editor with CM6+Yjs, document tree) — may or may
  not be useful for the validation domain. If the agent drafts paper
  sections (step 10 of the validation pipeline), the editor stays.
  Otherwise cut.

## What The New Design Must Not Do

- Do not propose rewriting meridian-channel out of Python for any part of
  MVP scope. Post-mvp-cleanup owns that decision.
- Do not bake domain-specific behavior (biomedical, μCT, PyVista, etc.)
  into the shell, the backend, or the wire protocol. Domain lives in
  agent profiles, skills, and interactive tools.
- Do not require a separate Go backend during MVP.
- Do not require Daytona, Supabase, auth, or billing.
- Do not design around `companion` (the TypeScript reference) as a
  dependency. Read it for stream-json protocol understanding only.
- Do not over-engineer. Design quality is load-bearing for the harness
  abstraction, the event mapping, and the SOLID boundaries. Everything else
  can be rough-and-ready and refactored post-MVP.
- Do not preserve any content from the archived `design/` subtree without
  explicit per-file re-validation against this requirements doc. It was
  under the D34–D40 framing and is stale by default.
- Do not propose a FIFO control protocol, cross-process control frames, or
  streaming-as-a-separate-invocation-shape. Those were D37 deliverables;
  they are stale under D41 (control is in-process asyncio in the
  single-Python-process MVP).

## What The New Design Should Produce

The fresh `@design-orchestrator` run produces a design tree organized
around the three phases. The exact file split is the orchestrator's to
choose based on the `planning` and `architecture` skills, but coverage
must include at minimum:

- **System topology** — how the three phases fit together at runtime, what
  processes exist, what the data flow looks like end-to-end.
- **Phase 1 — bidirectional streaming foundation** — per-harness input
  channel mechanics, `HarnessSender` interface, integration with existing
  `HarnessAdapter` and `launch/process.py`, Phase 1 smoke test shape.
- **Phase 2 — FastAPI + WebSocket + AG-UI mapping** — WebSocket endpoint
  shape, inbound/outbound frame taxonomies, per-harness wire-format →
  AG-UI event mapping, integration points for `ag_ui.core` types, unit
  test shape per mapper, end-to-end smoke test shape.
- **Phase 3 — React UI** — component tree derived from `frontend-v2`,
  activity stream rendering, input form behavior, per-tool display config,
  capability-aware affordances, interactive-tool protocol integration for
  blocking tools like PyVista.
- **Agent profile loading** — how `.agents/` flows into a Claude Code
  session at spawn time and how this stays clean for Codex and OpenCode.
- **Repository layout** — where new code lives in meridian-channel, how
  `meridian app` is launched, what `uv sync` installs, what ships in
  `mars sync`.

Edge cases and failure modes must be enumerated explicitly in design
artifacts, per the `dev-principles` skill. At minimum:

- Harness subprocess dies mid-turn — how does the adapter report it, how
  does the WebSocket surface it, how does the UI recover?
- Client disconnects mid-stream — does the spawn continue or cancel?
- Inbound `user_message` arrives while the harness is mid-tool-execution —
  is it queued, rejected, or buffered?
- Adapter starts but harness refuses to produce `RUN_STARTED` — timeout
  semantics?
- Two processes attempt to control the same spawn simultaneously — who
  wins? (MVP answer is probably "undefined, single-process only," but the
  design must acknowledge.)

Run the final fan-out review across diverse models per the
`agent-staffing` skill. **Include `@refactor-reviewer`** — the harness
abstraction is a structural hot spot and refactor hygiene matters here.

## Customer Reminder

**Primary customer**: the developer building meridian itself. The MVP bar
is "better than the CLI for steering Claude Code spawns mid-turn." Every
design decision should be checkable against "would this make meridian
development faster."

**Secondary customer**: a real human being at Yao Lab who uses Amira today
and has a year-long learning curve. The long-term bar is "good enough to
do his actual work on his actual data without fighting the tool."

Design quality for its own sake does not matter — design quality where it
unblocks the customer does.
