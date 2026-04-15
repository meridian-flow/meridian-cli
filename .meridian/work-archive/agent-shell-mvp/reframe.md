# Architectural Reframe — 2026-04-08

**Status**: Active. Read this first. This doc supersedes the earlier framing in
`overview.md`, `design/strategy/`, `design/extensions/`, `design/frontend/`, and
`design/packaging/` — most of which is about to be deleted.

**Origin**: Dev-orchestrator conversation c1046 continuation, 2026-04-08,
following user direction to "use the building blocks of frontend contract
designed and developed in that other repo" and the clarification that "the
point of adding a UI onto meridian was to be able to spawn other providers."

**Supersedes**: D21 (agent-shell-mvp replaces meridian-flow) and most of the
`agent-shell-mvp/design/` tree that treated the shell as a new product.

**Related decisions**: D34–D40 (new this session, see `decisions.md`).

## TL;DR

The "agent-shell-mvp" is **NOT a new product**. It is a **local deployment
shape** of meridian-flow's frontend, backed by **meridian-channel as the agent
runtime**.

```
Local (agent-shell-mvp path):                 Cloud (biomedical-mvp path):
┌────────────────────────────┐                ┌────────────────────────────┐
│ frontend-v2 (React)        │                │ frontend-v2 (React)        │
└──────────┬─────────────────┘                └──────────┬─────────────────┘
           │ 3-WS / AG-UI                                │ 3-WS / AG-UI
┌──────────┴─────────────────┐                ┌──────────┴─────────────────┐
│ meridian-flow backend (Go) │                │ meridian-flow backend (Go) │
└──────────┬─────────────────┘                └──────────┬─────────────────┘
           │ subprocess (stdout/stdin)                   │ direct function call
┌──────────┴─────────────────┐                ┌──────────┴─────────────────┐
│ meridian-channel (Python)  │                │ meridian-llm-go providers  │
│ — agent runtime            │                │ (anthropic, openrouter)    │
└──────────┬─────────────────┘                └──────────┬─────────────────┘
           │ subprocess                                  │ HTTPS
┌──────────┴─────────────────┐                ┌──────────┴─────────────────┐
│ Claude Code / Codex /      │                │ Anthropic / OpenRouter     │
│ OpenCode harness           │                │                            │
└──────────┬─────────────────┘                └──────────┬─────────────────┘
           │ user's API subscription                     │ + Daytona sandbox
           ▼                                             ▼
       LLM provider                                  LLM provider
```

**Two backends, one frontend, one wire contract.** The contract is the
AG-UI event taxonomy + 3-WS topology + per-tool behavior config that already
exist in meridian-flow's biomedical-mvp design.

## meridian-channel's Role

meridian-channel **IS** the agent runtime. In the local deployment path, the
Go backend doesn't invent an agent runtime — it delegates to meridian-channel
as a subprocess.

What meridian-channel already owns and keeps owning:

- Agent profiles (YAML frontmatter + markdown system prompts)
- Skills loading (fresh on launch/resume — survives compaction)
- Model and harness resolution (profile → model → harness)
- Work item context, shared filesystem (`$MERIDIAN_WORK_DIR`, `$MERIDIAN_FS_DIR`),
  parent chat inheritance (`$MERIDIAN_CHAT_ID`)
- Mars package integration (ensures `.agents/` materialized before spawn)
- Spawn/session state (crash-only JSONL event stores)
- Config precedence (CLI > env > profile > project > user)
- Approval modes and permission tiers
- Harness subprocess launching for Claude Code, Codex, OpenCode
- The CLI surface developers already use in production for dev-workflow
  orchestration

None of this gets rewritten. meridian-channel stays Python (D35).

## What This Work Item Delivers

Three additive changes to meridian-channel, grounded in D33 and refined by
D36/D37:

### 1. Harness adapters emit canonical AG-UI events (D36)

Current harness adapters write raw harness output to `spawn.jsonl` and extract
a final report. The refactor adds a **normalization layer**: every adapter
translates its wire format (Claude stream-json, Codex JSON-RPC `item/*`
notifications, OpenCode HTTP session events) into the **canonical AG-UI event
taxonomy** from meridian-flow's biomedical-mvp design:

```
RUN_STARTED / RUN_FINISHED
STEP_STARTED
THINKING_START / THINKING_TEXT_MESSAGE_CONTENT
TEXT_MESSAGE_START / TEXT_MESSAGE_CONTENT / TEXT_MESSAGE_END
TOOL_CALL_START / TOOL_CALL_ARGS / TOOL_CALL_END / TOOL_CALL_RESULT
TOOL_OUTPUT {stream: stdout|stderr}
DISPLAY_RESULT {resultType}
```

Plus per-tool behavior config: each adapter knows its harness's tool set and
emits events with the right render defaults (bash collapsed, Read/Grep/Glob
collapsed, Python stdout inline, etc.). The config matches what
meridian-flow's frontend reducer already expects.

### 2. Streaming spawn mode + stdin control protocol (D37)

New invocation shape for backend consumption (exact flag/subcommand name
decided during design):

```
meridian spawn --stream -a coder -p "implement phase 2"
```

**Stdout**: JSONL stream of AG-UI events.
**Stdin**: JSONL control channel. Mid-turn user messages, interrupts,
cancellation:

```json
{"type": "user_message", "text": "wait, reconsider X"}
{"type": "interrupt"}
{"type": "cancel"}
```

Mid-turn injection semantics vary by harness, adapter hides the difference:
- **Claude Code**: write stream-json user message to harness stdin → Claude
  queues to next turn boundary
- **Codex**: `turn/interrupt` + `turn/start` with the new message
- **OpenCode**: POST to session message endpoint

Capability is reported via an AG-UI event on spawn start so the frontend knows
which affordance to render.

### 3. `meridian spawn inject <spawn_id> "message"` CLI primitive (D37)

Public-facing command that injects mid-turn messages into a running spawn from
another process. Two consumers:
- **Existing dev-workflow orchestrators**: dev-orchestrator, design-orchestrator,
  impl-orchestrator can steer their children mid-execution.
- **meridian-flow's Go backend**: forwards frontend user messages into the
  running agent turn.

Underneath, it writes a `user_message` control frame to the spawn's stdin (or
a control FIFO — TBD during design).

## The External Contract

The frontend contract is **external** to this work item. Canonical sources live
in meridian-flow:

| File | Role |
|---|---|
| `meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md` | 3-WS topology, hook contracts, reconnect recovery, initialization order |
| `meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md` | End-to-end AG-UI event sequence with traces |
| `meridian-flow/.meridian/work/biomedical-mvp/design/frontend/foundations.md` | Cross-cutting frontend model |
| `meridian-flow/.meridian/work/biomedical-mvp/design/frontend/state-management.md` | Store specifications |
| `meridian-flow/.meridian/work/biomedical-mvp/design/frontend/thread-model.md` | Thread/turn/work-item lifecycle |
| `meridian-flow/.meridian/work/biomedical-mvp/design/backend/python-tool.md` | Per-tool behavior config (example: python) |
| `meridian-flow/.meridian/work/biomedical-mvp/design/backend/bash-tool.md` | Per-tool behavior config (example: bash) |
| `meridian-flow/.meridian/work/biomedical-mvp/design/backend/display-results.md` | Structured tool result rendering |

Implementation lives in meridian-flow source trees:

| Path | Role |
|---|---|
| `meridian-flow/meridian-stream-go/` | Stream dispatch, `InterjectionBuffer`, SSE handler, registry — **reference** for meridian-channel's Python implementation, not imported |
| `meridian-flow/meridian-llm-go/` | Block types, provider interface — used only by the cloud path, **not** the shell path (D40) |
| `meridian-flow/backend/` | Current Go backend, about to be refactored to 3-WS per issue #8 |
| `meridian-flow/frontend-v2/` | Current frontend, about to be repointed for local deployment |

**agent-shell-mvp refactors meridian-channel to MATCH this contract.** It does
not redefine or duplicate it.

## What This Work Item Is NOT Responsible For

These belong to meridian-flow's dev-orchestrator in separate workstreams (D39):

- Backend 3-WS refactor (issue #8): rename existing handlers, add Project WS
- New "meridian-channel subprocess adapter" in meridian-flow's backend that
  launches meridian-channel, tails AG-UI events from stdout, forwards mid-turn
  injections to stdin
- Local deployment path for meridian-flow: localhost binding, Supabase/Daytona
  optional, static frontend-v2 serving, Converse mode as primary
- Frontend-v2 repointing and trimming for local single-user deployment

The coupling between this work item and meridian-flow's work is **only the two
published contracts**:

1. **AG-UI event schema** — meridian-flow defines, meridian-channel emits,
   meridian-flow backend+frontend consumes
2. **Streaming spawn control protocol** (stdin/stdout JSONL, D37) — defined
   here, consumed by meridian-flow's backend

Both sides can progress in parallel as long as both contracts are respected.

## What Still Lives in This Work Item's `design/`

After the rescope (per D38):

- `design/overview.md` — rewritten: short summary of the refactor, pointers to
  external contract, pointer to this doc
- `design/harness/` — kept, rewritten for the refactor scope
  - `overview.md`, `abstraction.md`, `adapters.md`, `mid-turn-steering.md`
- `design/events/` — kept, rewritten to describe AG-UI translation rather than
  invent a schema
  - `overview.md`, `flow.md`, harness→AG-UI mapping tables (replaces
    `normalized-schema.md`)

Deleted wholesale:

- `design/strategy/` — strategy is at product-strategy level, not design
- `design/extensions/` — composite frontend+MCP extensions are out of scope
- `design/packaging/` — mars capability packaging is separate work
- `design/frontend/` — frontend contract lives in meridian-flow
- `design/execution/` — collapses to "run as subprocess"

Preserved as historical record (not deleted):

- `requirements.md` — pre-D34 requirements; superseded but preserved for context
- `synthesis.md` — pre-correction convergence output from p1101
- `decisions.md` — full log D1–D40 (new D34–D40 at the bottom)
- `findings-harness-protocols.md` — authoritative harness protocol reference
- `correction-pass-brief.md`, `correction-review-brief.md` — earlier correction
  artifacts, still useful as examples

## Refactor Touchpoints in Current Code

These are the files the design needs to reason about when drafting the refactor
plan (not a comprehensive list — @explorer should map this fully during design):

| Path | Current role | Refactor impact |
|---|---|---|
| `src/meridian/lib/harness/claude.py` | Claude Code adapter | Add AG-UI event emission, stdin control routing |
| `src/meridian/lib/harness/codex.py` | Codex adapter | Same + JSON-RPC `turn/interrupt` wiring |
| `src/meridian/lib/harness/opencode.py` | OpenCode adapter | Same + HTTP session POST wiring |
| `src/meridian/lib/harness/adapter.py` | Base adapter interface | Grow event-emission + stdin-control methods |
| `src/meridian/lib/harness/common.py` | Shared harness helpers | Likely home for AG-UI emission utilities |
| `src/meridian/lib/harness/transcript.py` | Harness output recording | Extends to AG-UI-normalized transcript |
| `src/meridian/lib/harness/launch_types.py` | Launch config types | New streaming-mode launch type |
| `src/meridian/lib/state/` | Spawn/session stores | Integration with streaming event output |
| `src/meridian/cli/` | CLI commands | New `spawn --stream` flag or subcommand + `spawn inject` |
| Tests covering harness output formats and spawn lifecycle | Smoke + unit | Must not regress dev-workflow orchestrators |

## Principles for the Design Pass

1. **Reference, don't duplicate.** When the frontend contract or event schema
   is defined in meridian-flow, point to it. Do not copy it.
2. **Match existing conventions.** meridian-channel already has established
   patterns for adapters, state, config, and CLI commands. Follow them.
3. **Preserve dogfood workflows.** Every existing dev-workflow orchestrator use
   case must continue to function through the refactor. Smoke tests must pass
   before declaring the refactor done.
4. **Normalization at the adapter boundary.** AG-UI event translation happens
   inside each harness adapter, not in a post-hoc layer. The adapter contract
   grows to include "emit AG-UI events on an output channel."
5. **Capability honesty.** The three harnesses differ in mid-turn injection
   semantics. The abstraction unifies the *capability* (send_user_message) but
   surfaces the *semantic* (queue vs interrupt_restart vs http_post) so callers
   can render the right affordance.
