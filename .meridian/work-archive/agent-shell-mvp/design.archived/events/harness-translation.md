# Harness Translation

Per-harness mapping tables: native wire format → AG-UI events. **This file
replaces the pre-reframe `normalized-schema.md`** — see [D36](../../decisions.md)
for why a parallel "meridian-channel normalized schema" was rejected in favor
of emitting AG-UI directly.

The authoritative wire-format reference for each harness is
[`../../findings-harness-protocols.md`](../../findings-harness-protocols.md).
The authoritative AG-UI event reference is meridian-flow's
[`streaming-walkthrough.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md).
This doc just shows how meridian-channel adapts one to the other.

For the canonical AG-UI sequence and example traces, see [flow.md](flow.md).
For the adapter contract, see [`../harness/abstraction.md`](../harness/abstraction.md).
For the mid-turn steering protocol details, see
[`../harness/mid-turn-steering.md`](../harness/mid-turn-steering.md).

## How To Read

Each harness section has the same shape:

1. **Wire format overview** — one paragraph naming the transport and event
   discriminator.
2. **Mapping table** — harness-native event → AG-UI event(s).
3. **Tool naming coordination** — the canonical tool names the adapter
   emits on `TOOL_CALL_START`. Per-tool *render config* lives in
   meridian-flow's frontend `toolDisplayConfigs` registry, not on the
   wire and not in meridian-channel.
4. **Gaps and open questions** — what the harness does not emit cleanly, per
   `findings-harness-protocols.md`.

After the three harness sections, **Cross-Harness Notes** documents the
shared capability enum (reported via `params.json`, not on the wire),
ordering invariants, and the placement of the translation layer in
`harness/ag_ui_events.py`.

---

## Claude Code

### Wire Format Overview

Claude Code is invoked with `claude --input-format stream-json
--output-format stream-json`. Both directions are NDJSON over stdin/stdout.
Each line is a JSON object with a top-level `type` discriminator (`system`,
`user`, `assistant`, `result`). The `assistant` events carry a `content`
array of typed blocks (`text`, `thinking`, `tool_use`); `user` events carry
`tool_result` content blocks. Status: stable, documented, low-risk per
[`findings-harness-protocols.md` §Claude Code](../../findings-harness-protocols.md).

### Mapping Table

| Claude stream-json event | AG-UI event(s) |
|---|---|
| `{type:"system", subtype:"init", session_id, model, tools, ...}` | `RUN_STARTED` (extract `session_id`, `model`). The capability bundle (`mid_turn_injection: "queue"`, `structured_reasoning_stream: true`, `cost_tracking: true`, `runtime_model_switch: false`, `runtime_permission_switch: false`) is written to `params.json` at launch time, not as a wire event. |
| First `{type:"assistant", message:{...}}` after a user turn | `STEP_STARTED` |
| `assistant.content[].type == "thinking"` (block opens) | `THINKING_START` |
| `assistant.content[].type == "thinking"` (delta) | `THINKING_TEXT_MESSAGE_CONTENT` |
| `assistant.content[].type == "text"` (block opens) | `TEXT_MESSAGE_START` |
| `assistant.content[].type == "text"` (delta) | `TEXT_MESSAGE_CONTENT` |
| `assistant.content[].type == "text"` (block closes) | `TEXT_MESSAGE_END` |
| `assistant.content[].type == "tool_use"` (block opens) — emit `id`, `name` | `TOOL_CALL_START` `{toolName, toolCallId}` (no per-tool config on the wire — see "Tool Naming Coordination" below) |
| `tool_use.input` partial JSON deltas | `TOOL_CALL_ARGS` (each delta) |
| `tool_use` block closes | `TOOL_CALL_END` |
| `{type:"user", message.content[].type == "tool_result"}` partials (when streaming) | `TOOL_OUTPUT {stream: "stdout"}` (or `"stderr"` when distinguishable; for tools that don't surface a separate stream the adapter labels everything `"stdout"` and the per-tool config decides rendering) |
| `tool_result` final block (`tool_use_id`, `is_error`, `content`) | `TOOL_CALL_RESULT {toolCallId, exit_code (synthesized: 0 or 1 from `is_error`), result}` |
| `tool_result.content` items of `type == "image"` or other rich kinds | `DISPLAY_RESULT {resultType: "image"}` (or similar — see "Display result mapping" below) |
| `{type:"result", subtype:"success", usage, total_cost_usd, session_id, ...}` | `RUN_FINISHED {inputTokens, outputTokens, total_cost_usd}` |
| `{type:"result", subtype:"error_*", ...}` | `RUN_FINISHED` with error metadata; the error itself is logged and surfaced via `report.md` per the existing artifact contract |

**Display result mapping for Claude**: Claude's tool results carry rich
`content` blocks (`text`, `image`, etc.) but do not have a meridian-flow-style
`result.json` file convention. The Claude adapter synthesizes `DISPLAY_RESULT`
events from `tool_result.content` items of non-text kinds. For built-in
Claude tools that the adapter knows about (e.g., a future `WebFetch` returning
markdown, or an `Image` content block from a Read on a binary file), the
adapter maps to the appropriate `resultType`. The adapter does NOT invent new
`resultType` values — it uses the meridian-flow set documented in
[`backend/display-results.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/backend/display-results.md)
(`plotly`, `image`, `dataframe`, `mesh_ref`, `text`, `markdown`). Anything
that doesn't fit those kinds becomes a `text` or `markdown` `DISPLAY_RESULT`.

### Tool Naming Coordination

Per meridian-flow's
[`frontend/component-architecture.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md),
`ToolDisplayConfig` (`inputCollapsed`, `stdoutCollapsed`, `stderrMode`,
`producesResults`, optional `label`, optional `icon`) is
**frontend-resident** in `toolDisplayConfigs: Record<string, ToolDisplayConfig>`,
keyed by `toolName`. The wire payload on `TOOL_CALL_START` is just
`{toolName, toolCallId}` and the reducer looks up the config when it
sees the event.

The Claude adapter's job is to emit the canonical Claude tool name on the
`toolName` field. The coordination requirement is that those names match
the keys in meridian-flow's registry; when a name disagrees, the local
path falls back to the registry's default config.

**Coordination checklist** (Claude built-ins to verify against
`toolDisplayConfigs` before V0 ships):

- `Bash` — shell commands (the registry's `bash` example shows
  `inputCollapsed: true, stdoutCollapsed: true`)
- `Read` — file read
- `Write`, `Edit`, `MultiEdit` — file mutation
- `Glob`, `Grep` — search
- `WebFetch`, `WebSearch` — web tools (the registry sets
  `producesResults: true` for these, with a markdown `DISPLAY_RESULT`)
- `Task` — sub-agent spawn
- `TodoWrite` — internal task tracking
- `NotebookEdit` — Jupyter cell edit
- `BashOutput`, `KillBash` — background-shell follow-up
- MCP-provided tools (`mcp__*`) — emit the MCP tool name verbatim;
  unknown tools fall back to the registry's default config

If a Claude tool name and the registry's key disagree, **change the
adapter's emitted name** to match the registry. The frontend registry
is the source of truth (D36); meridian-channel does not push new keys
into it.

There is no Claude equivalent of meridian-flow's `python` tool yet —
Claude Code doesn't have a built-in persistent Python kernel — but if a
Claude MCP added one, the adapter would emit `toolName: "python"` and
the registry's existing config would apply.

### Gaps and Open Questions

- **Streaming `tool_result` chunks**: Claude's stream-json emits `tool_result`
  as a single block in most cases. Long-running tools that stream output
  (e.g., a hypothetical `Bash` that pipes output mid-execution) may not
  surface intermediate chunks cleanly. The adapter falls back to emitting
  one `TOOL_OUTPUT` frame from the final `tool_result.content` and a
  `TOOL_CALL_RESULT` immediately after. **Open question**: does Claude's
  current stream-json surface stream-of-output for the built-in `Bash` tool,
  or only after completion? Validate during Phase 1 implementation.
- **MCP approvals**: per
  [`findings-harness-protocols.md`](../../findings-harness-protocols.md),
  the Claude adapter today auto-accepts MCP tool approvals. The approval
  request is observable on stream-json but the V0 adapter does not surface
  it as a control event. Approval routing (the `runtime_permission_switch`
  capability flips to `true`) is a V1 deliverable.
- **`stderr` discrimination**: Claude's `tool_result.content` for the `Bash`
  tool collapses stdout and stderr into one text block. The adapter cannot
  always distinguish them. The `TOOL_OUTPUT` event takes a `stream` field
  but for Claude built-in tools the adapter labels all output `"stdout"` and
  relies on the per-tool config (`stderr: collapsed`) to keep the rendering
  consistent. **Open question**: could the adapter parse Bash stderr from
  the `<stderr>...</stderr>` markers some tools emit? Punt to V1.
- **Cost extraction**: Claude `result` line carries `total_cost_usd` and
  `usage`. The adapter must extract these into both `RUN_FINISHED` (for
  the AG-UI stream) and `report.md` / `output.jsonl` (for the existing
  artifact contract). The current Claude adapter already extracts to
  artifacts; the streaming path adds the AG-UI emission step.

---

## Codex (`codex app-server`)

### Wire Format Overview

Codex is invoked as `codex app-server` (NOT `codex exec`) and speaks
JSON-RPC 2.0 over stdio. Method calls follow `thread/start`, `thread/resume`,
`turn/start`, `turn/interrupt`. The harness emits notifications under the
`item/*` family — `item/agentMessage/*`, `item/reasoning/*`,
`item/tool_call/*`, `item/commandExecution/*`, `item/fileChange/*`,
`item/webSearch/*`, `item/mcpToolCall/*`, `item/contextCompaction/*`. Tool
approval requests are `item/*/requestApproval` requests where the server
responds with a decision. Status: stable for the core protocol; WebSocket
transport and `experimentalApi` methods are out of scope. See
[`findings-harness-protocols.md` §Codex](../../findings-harness-protocols.md)
and the
[companion `web/CODEX_MAPPING.md`](https://github.com/The-Vibe-Company/companion)
reference (MIT-licensed; pattern only, not a dependency).

### Mapping Table

> **Item notation grounding (C6).** The `item/*` notation below uses the
> JSON-RPC notification family documented in
> [`../../findings-harness-protocols.md` §Codex](../../findings-harness-protocols.md)
> and the companion reference adapter's
> [`web/CODEX_MAPPING.md`](https://github.com/The-Vibe-Company/companion).
> The `start`/`delta`/`end` decomposition for streaming content (reasoning
> and assistant text) is companion's pattern; for Codex builds that bulk
> their content into a single notification, the adapter emits one
> `*_START` + one `*_CONTENT` + one `*_END` from the bulk frame and the
> reducer accumulates correctly. Validate the exact notification names
> against the live `codex app-server` build during Phase 1 implementation —
> the field shapes below are the best-known mapping and are expected to
> need minor renames once a real Codex stream is captured.

| Codex JSON-RPC method/notification | AG-UI event(s) |
|---|---|
| `initialize` response | `RUN_STARTED`. The capability bundle (`mid_turn_injection: "interrupt_restart"`, `structured_reasoning_stream: false` (V0 — companion bulks reasoning; see gaps below), `runtime_model_switch: false`, `runtime_permission_switch: false`, `cost_tracking: false` for V0) is written to `params.json` at launch time, not as a wire event. |
| `thread/start` response | session id captured to `output.jsonl` and the `RUN_STARTED` payload |
| `turn/start` (call) | `STEP_STARTED` (emitted when Codex acknowledges) |
| `notifications/item/reasoning` (or `item/reasoning/start` if streaming) | `THINKING_START` |
| `notifications/item/reasoning/delta` (when streaming; bulk for V0) | `THINKING_TEXT_MESSAGE_CONTENT` |
| `notifications/item/reasoning/end` (when streaming) | (THINKING blocks have no explicit END in AG-UI; the next event closes the block) |
| `notifications/item/agentMessage/start` | `TEXT_MESSAGE_START` |
| `notifications/item/agentMessage/delta` | `TEXT_MESSAGE_CONTENT` |
| `notifications/item/agentMessage/end` | `TEXT_MESSAGE_END` |
| `notifications/item/tool_call/start` (with `name`, `id`, optional `arguments_partial`) | `TOOL_CALL_START` `{toolName, toolCallId}` only (no per-tool config on the wire) |
| `notifications/item/tool_call/delta` (arguments stream) | `TOOL_CALL_ARGS` |
| `notifications/item/tool_call/end` | `TOOL_CALL_END` |
| `notifications/item/commandExecution/output` (stdout/stderr lines) | `TOOL_OUTPUT {stream: "stdout"\|"stderr"}` |
| `notifications/item/tool_call/completed` (with `result`, `exit_code`) | `TOOL_CALL_RESULT` |
| `notifications/item/fileChange/*` | `TOOL_OUTPUT` if part of a tool call's progress, else logged to `output.jsonl` only |
| `notifications/item/webSearch/*` | `DISPLAY_RESULT {resultType: "markdown"}` summarizing results |
| `notifications/item/mcpToolCall/*` | mapped through the same `tool_call/*` shape (Codex models MCP calls as a tool-call subtype) |
| `notifications/item/contextCompaction/*` | logged to `output.jsonl`; not currently surfaced as an AG-UI event (V1 — could become a `STEP_STARTED` boundary marker) |
| `notifications/turn/completed` (with `usage`, `cost`) | `RUN_FINISHED {inputTokens, outputTokens, total_cost}` |
| `notifications/turn/error` | `RUN_FINISHED` with error metadata |
| `requests/item/*/requestApproval` | V0: auto-accept (matching companion's behavior); V1: surface as a control event for the consumer |

**Display result synthesis**: Codex doesn't have a built-in `result.json`
convention either. The adapter synthesizes `DISPLAY_RESULT` from notification
families that carry rich content (e.g., `webSearch` results become
`markdown`). The same rule as Claude applies: only the meridian-flow
`resultType` set is used.

### Tool Naming Coordination

Same rule as Claude: the wire payload on `TOOL_CALL_START` is just
`{toolName, toolCallId}`, and meridian-flow's `toolDisplayConfigs`
registry decides the render. The Codex adapter's job is to translate
each `item/tool_call/*` `name` field into a canonical tool name that
matches a key in the registry. The names below match the JSON-RPC
`item/tool_call/*` family as documented in companion's
`CODEX_MAPPING.md`.

**Coordination checklist** (Codex-canonical tool names to verify
against the registry before V0 ships):

- `shell` / `commandExecution` → `bash` (the registry's shell entry)
- `apply_patch` / `fileChange` → `edit` (or whatever the registry
  uses for patch/edit-style tools)
- `read_file` → `read`
- `write_file` → `write`
- `web_search` → `webSearch` or `web_search` (whichever the registry
  uses)
- `mcp__*` (MCP server tools) → emit the MCP tool name verbatim;
  the registry handles unknowns with a default config

Codex models more operations as variants of `commandExecution` than
Claude does, so the Codex adapter naturally emits fewer distinct
tool names. When an item type doesn't map to a registry key, the
adapter emits the most descriptive Codex name available and the
reducer falls back to its default config — acceptable but visible.

### Gaps and Open Questions

- **`item/reasoning/delta` streaming**: companion's adapter does not
  currently stream reasoning — it bulks it into a single block. The V0
  Codex adapter inherits that gap and declares
  `structured_reasoning_stream: false` in the `params.json` capability
  bundle. The adapter should still emit one `THINKING_START` +
  `THINKING_TEXT_MESSAGE_CONTENT` from the bulk frame so the reducer
  renders something coherent. Flip the capability flag to `true` and
  switch to per-delta emission once a real Codex stream confirms
  `item/reasoning/delta` notifications are emitted in practice.
- **`turn/completed` cost tracking**: companion's adapter doesn't extract
  `usage` and `cost` from `turn/completed`, and the V0 Codex adapter
  inherits that gap. The capability bundle declares `cost_tracking: false`
  in V0. Flip to `true` once an implementation wires `usage`/`cost` from
  `turn/completed` through to `RUN_FINISHED` and the existing artifact
  contract.
- **MCP and `webSearch` approvals**: companion's reference auto-accepts
  these. meridian-channel matches that behavior in V0 to keep parity. V1
  exposes approvals as a control surface and flips
  `runtime_permission_switch` in the capability bundle to `true`.
- **Runtime model and permission switching**: not supported by Codex (set
  at `thread/start`). The capability bundle reports `false` for both in
  `params.json`. The consumer must respect this and not render the
  affordances.
- **WebSocket transport** is flagged experimental upstream and is not used
  by meridian-channel — the adapter speaks stdio only.
- **`item/contextCompaction/*`**: not currently mapped. V1 could surface it
  as a `STEP_STARTED` boundary so the consumer knows context was compacted,
  but V0 just logs it.

---

## OpenCode

### Wire Format Overview

OpenCode is invoked as `opencode serve` and exposes an HTTP session API.
The streaming surface is Server-Sent Events (SSE) over the session endpoint:
`POST /session/{id}/message` to send a turn, `GET /session/{id}/events` to
stream events. Some flows use ACP (Agent Communication Protocol) NDJSON over
stdin for non-HTTP integrations, but the meridian-channel adapter targets
the HTTP path because it's the documented external-driver surface. Status:
stable per
[`findings-harness-protocols.md` §OpenCode](../../findings-harness-protocols.md)
— OpenCode is designed modularly to support external drivers like this.

### Mapping Table

OpenCode SSE event names below are based on the project's documented session
event family. Where the precise event name needs validation against the
current OpenCode version, the adapter discovers them at startup and the
mapping is the per-row best-known equivalent.

| OpenCode HTTP/SSE event | AG-UI event(s) |
|---|---|
| `POST /session` response (session created) | `RUN_STARTED` (extract `session_id`). The capability bundle (`mid_turn_injection: "http_post"`, `structured_reasoning_stream: <version-detected>`, `runtime_model_switch: false`, `runtime_permission_switch: false`, `cost_tracking: true`) is written to `params.json` at launch time, not as a wire event. |
| SSE `session.turn.started` | `STEP_STARTED` |
| SSE `message.reasoning.delta` (when present) | `THINKING_START` (first delta) + `THINKING_TEXT_MESSAGE_CONTENT` (each delta) |
| SSE `message.text.start` / `message.delta` / `message.text.end` | `TEXT_MESSAGE_START` / `TEXT_MESSAGE_CONTENT` / `TEXT_MESSAGE_END` |
| SSE `tool.invoked` (with `tool_name`, `tool_call_id`) | `TOOL_CALL_START` `{toolName, toolCallId}` only (no per-tool config on the wire) |
| SSE `tool.args.delta` (streaming args) | `TOOL_CALL_ARGS` |
| SSE `tool.args.complete` | `TOOL_CALL_END` |
| SSE `tool.output` (with `stream: stdout\|stderr`) | `TOOL_OUTPUT {stream}` |
| SSE `tool.completed` (with `result`, `exit_code`) | `TOOL_CALL_RESULT` |
| SSE `tool.display_result` (when emitted) | `DISPLAY_RESULT {resultType}` (mapped to meridian-flow's set) |
| SSE `session.completed` (with `usage`, `cost`) | `RUN_FINISHED {inputTokens, outputTokens, total_cost}` |
| SSE `session.error` | `RUN_FINISHED` with error metadata |

**Mid-turn POST**: when meridian-channel's adapter delivers a `user_message`
control frame, it issues `POST /session/{id}/message` with the new content.
OpenCode acknowledges asynchronously, then begins a new turn — the adapter
sees `session.turn.started` and emits `STEP_STARTED`. See
[`../harness/mid-turn-steering.md`](../harness/mid-turn-steering.md).

### Tool Naming Coordination

Same rule as Claude and Codex: the wire payload on `TOOL_CALL_START`
is just `{toolName, toolCallId}`, and meridian-flow's
`toolDisplayConfigs` registry decides the render. The OpenCode
adapter's job is to emit canonical tool names matching the registry.

**Coordination checklist** (OpenCode standard tool catalog to verify
against the registry before V0 ships):

- `bash` — shell commands
- `read` — file read
- `write`, `edit` — file mutation
- `grep`, `glob` — search
- `webfetch`, `websearch` — web tools
- `task` — sub-agent spawn
- custom MCP tools — emit verbatim; the registry handles unknowns
  with a default config

OpenCode's tool set is configurable per-deployment. When a deployment
adds a custom tool that isn't in the registry, the reducer falls back
to its default config — acceptable but visible. Deployments that need
custom render config push the change into meridian-flow's registry,
not into the OpenCode adapter.

### Gaps and Open Questions

- **SSE event naming**: the table above uses the documented OpenCode session
  event family, but specific event names should be validated against the
  current OpenCode build during Phase 1. The adapter is structured so a
  rename of one field is a one-line change in the mapping table; the
  taxonomy itself does not need to move.
- **Reasoning stream**: OpenCode's structured reasoning stream support
  varies by version. The `params.json` capability bundle reports
  `structured_reasoning_stream` based on the version detected at session
  create — the adapter probes once and caches.
- **ACP NDJSON path**: not used by meridian-channel. If a future deployment
  needs it (e.g., embedded OpenCode without HTTP server), a second adapter
  variant lives next to `opencode.py` rather than overloading the HTTP one.
- **Approval requests**: same V0/V1 split as Claude and Codex — auto-accept
  in V0, surface as control events in V1.
- **HTTP reconnection**: SSE drops are recovered by re-establishing the
  `GET /events` stream with a `last-event-id` header where supported. The
  adapter buffers events between drop and reconnect; if the drop is too
  long, it surfaces a `RUN_FINISHED` with a reconnection error and the
  consumer is expected to start a fresh spawn rather than partial-replay.

---

## Cross-Harness Notes

### Capabilities Bundle

The capability bundle uses the canonical flat shape from
[`../harness/abstraction.md`](../harness/abstraction.md), grounded in
[`findings-harness-protocols.md` §1](../../findings-harness-protocols.md).
It is reported **out-of-band** via the per-spawn `params.json` artifact
at launch time, not as a wire event:

```python
@dataclass
class HarnessCapabilities:
    mid_turn_injection: Literal["queue", "interrupt_restart", "http_post", "none"]
    runtime_model_switch: bool
    runtime_permission_switch: bool
    structured_reasoning_stream: bool
    cost_tracking: bool
```

**Canonical V0 capability table** (flat fields, no `supports_` prefix,
no `supports_interrupt` — interrupt semantics fold into
`mid_turn_injection`):

| Harness | mid_turn_injection | runtime_model_switch | runtime_permission_switch | structured_reasoning_stream | cost_tracking |
|---|---|---|---|---|---|
| Claude Code | `queue` | `false` | `false` | `true` | `true` |
| Codex | `interrupt_restart` | `false` | `false` | **`false`** (V0 — companion bulks reasoning) | **`false`** (V0 — companion does not extract `usage` from `turn/completed`) |
| OpenCode | `http_post` | `false` | `false` | version-detected | `true` |

The full per-harness wire-level details — how `queue`, `interrupt_restart`,
and `http_post` actually deliver the user message — live in
[`../harness/mid-turn-steering.md`](../harness/mid-turn-steering.md). This
table is the *what the consumer sees* view; the harness doc is the
*how the adapter implements it* view.

**On Claude and `interrupt`.** There is no `supports_interrupt` flag.
Claude in queue mode has no clean interrupt primitive — when an
`interrupt` control frame arrives, the Claude adapter writes a
`rejected` entry to `control.log` and the in-flight turn keeps
running. Codex and OpenCode honor `interrupt` through their
respective primitives (Codex `turn/interrupt`, OpenCode session-cancel
where supported). The interrupt semantics are entirely captured by
the `mid_turn_injection` enum plus the per-adapter `control.log`
behavior; no boolean flag is needed.

### Event Order Invariants

Every adapter must honor these ordering rules so the meridian-flow frontend
reducer behaves consistently. The reducer assumes them and breaks if they
are violated.

1. **Run boundary**: `RUN_STARTED` precedes every event; `RUN_FINISHED` is
   the last event. The capability bundle is reported out-of-band via
   `params.json` at launch time, not as a wire event — the consumer reads
   it before opening the AG-UI stream and does not need an in-stream
   capability marker.
2. **Step boundary**: every content block is wrapped by a `STEP_STARTED`
   and a subsequent `STEP_STARTED` (or `RUN_FINISHED`) as the closing
   boundary. There is no explicit `STEP_FINISHED` event today — the next
   step boundary or `RUN_FINISHED` closes the prior step.
3. **Tool call lifecycle**: `TOOL_CALL_START` precedes `TOOL_CALL_ARGS`,
   which precedes `TOOL_CALL_END`. `TOOL_CALL_RESULT` follows
   `TOOL_CALL_END`. `TOOL_OUTPUT` events for a given `toolCallId` are
   emitted between `TOOL_CALL_END` and `TOOL_CALL_RESULT`. `DISPLAY_RESULT`
   events for a given `toolCallId` are emitted *after* `TOOL_CALL_RESULT`.
4. **Text message lifecycle**: `TEXT_MESSAGE_START` precedes one or more
   `TEXT_MESSAGE_CONTENT` deltas, which precede `TEXT_MESSAGE_END`. The
   reducer accumulates deltas between START and END.
5. **Thinking lifecycle**: `THINKING_START` precedes one or more
   `THINKING_TEXT_MESSAGE_CONTENT` deltas. There is no explicit thinking
   END — the reducer closes the thinking block on the next non-thinking
   event.
6. **Per-toolCallId monotonic ordering**: within a single `toolCallId`,
   adapters must not interleave events out of order even if the harness
   reorders them on the wire. Adapters buffer briefly to enforce this if
   the harness's wire format does not.
7. **Capabilities are immutable for the spawn lifetime.** They are set at
   `thread/start` time for Codex, at harness launch for Claude, and at
   session create for OpenCode. Because they are reported via `params.json`
   and not on the wire, no in-stream "capability event" exists to order.

These rules come from meridian-flow's
[`streaming-walkthrough.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md)
and the `useReducer(reduceStreamEvent)` implementation it documents. Any
ordering question not covered here should be resolved by checking what the
reducer expects, not by inventing new ordering.

### Translation-Layer Home

Per [`../refactor-touchpoints.md` Structural Analysis](../refactor-touchpoints.md#structural-analysis),
the AG-UI translation lives in a **new sibling module**
`src/meridian/lib/harness/ag_ui_events.py` — not in `transcript.py` and not
in `common.py`.

`ag_ui_events.py` owns:

- The AG-UI event dataclasses / typed dicts (`AGUIRunStarted`,
  `AGUIToolCallStart`, `AGUIDisplayResult`, etc.) so the three adapters
  cannot drift on payload shape.
- The `HarnessCapabilities` dataclass and the canonical enum values
  (used by adapters when they write the capability bundle into
  `params.json` at launch time — not for in-stream emission).
- The serializer that turns events into JSONL lines on the streaming
  spawn's stdout.
- A small helper for synthesizing `DISPLAY_RESULT` events from common
  rich-content shapes (image bytes, markdown text, table data) to keep the
  three adapters DRY.

`ag_ui_events.py` deliberately does **not** own per-tool render config.
`ToolDisplayConfig` is frontend-resident in meridian-flow's
`toolDisplayConfigs: Record<string, ToolDisplayConfig>` registry
([`frontend/component-architecture.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md)),
keyed by `toolName`. Adapters emit `{toolName, toolCallId}` only and the
reducer looks up render config when it sees the event. Per-tool table
sprawl in the adapter layer would re-create the registry meridian-flow
already owns (D36).

Each adapter (`claude.py`, `codex.py`, `opencode.py`) imports
`ag_ui_events` and is responsible for:

- Parsing its harness-native event stream (already partly done in
  `common.py` and `launch/stream_capture.py`).
- Calling the right `ag_ui_events.AGUI*` constructor for each native
  event.
- Emitting canonical tool names that match the keys in meridian-flow's
  `toolDisplayConfigs` registry — the per-harness "Tool Naming
  Coordination" sections above are the V0 checklist.
- Implementing its mid-turn delivery semantic
  (see [`../harness/mid-turn-steering.md`](../harness/mid-turn-steering.md)).

This split keeps the adapter contract — what `harness/abstraction.md`
defines — focused on the lifecycle and control plane, and the events
contract — what this subtree defines — focused on the wire-level
translation. Neither layer leaks into the other.

The plumbing between the adapter and the streaming spawn's stdout is the
existing `launch/stream_capture.py` event-observer callback, extended to
serialize `ag_ui_events` instead of raw harness JSONL. That keeps the
parser, redaction, and large-line handling in one place.
