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
3. **Per-tool render config** — the tool set the adapter knows about and the
   `ToolDisplayConfig` it attaches to `TOOL_CALL_START`.
4. **Gaps and open questions** — what the harness does not emit cleanly, per
   `findings-harness-protocols.md`.

After the three harness sections, **Cross-Harness Notes** documents the
shared capability enum, ordering invariants, and the placement of the
translation layer in `harness/ag_ui_events.py`.

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
| `{type:"system", subtype:"init", session_id, model, tools, ...}` | `RUN_STARTED` (extract `session_id`, `model`); `CAPABILITY {mid_turn_injection: "queue", structured_reasoning_stream: true, ...}` |
| First `{type:"assistant", message:{...}}` after a user turn | `STEP_STARTED` |
| `assistant.content[].type == "thinking"` (block opens) | `THINKING_START` |
| `assistant.content[].type == "thinking"` (delta) | `THINKING_TEXT_MESSAGE_CONTENT` |
| `assistant.content[].type == "text"` (block opens) | `TEXT_MESSAGE_START` |
| `assistant.content[].type == "text"` (delta) | `TEXT_MESSAGE_CONTENT` |
| `assistant.content[].type == "text"` (block closes) | `TEXT_MESSAGE_END` |
| `assistant.content[].type == "tool_use"` (block opens) — emit `id`, `name` | `TOOL_CALL_START` (attach per-tool render config from the table below) |
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

### Per-Tool Render Config

Claude Code's built-in tool set with the `ToolDisplayConfig` the adapter
attaches to each `TOOL_CALL_START`. Field semantics are
meridian-flow's `ToolDisplayConfig` from
[`frontend/component-architecture.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md).

| Tool name | input | stdout | stderr | producesResults | Notes |
|---|---|---|---|---|---|
| `Bash` | `collapsed` | `collapsed` | `hidden-popup` | `false` | Shell commands; per-meridian-flow `bash-tool.md` defaults |
| `Read` | `collapsed` | `collapsed` | `collapsed` | `false` | File read; long output collapses cleanly |
| `Write` | `collapsed` | `collapsed` | `collapsed` | `false` | File write; output is just confirmation |
| `Edit` | `collapsed` | `collapsed` | `collapsed` | `false` | Patch edits |
| `Glob` | `collapsed` | `collapsed` | `collapsed` | `false` | Filename pattern search |
| `Grep` | `collapsed` | `collapsed` | `collapsed` | `false` | Content search; collapsed by default — user expands when needed |
| `WebFetch` | `collapsed` | `collapsed` | `collapsed` | `true` | Returns markdown via `DISPLAY_RESULT {resultType: "markdown"}` |
| `WebSearch` | `collapsed` | `collapsed` | `collapsed` | `true` | Search results rendered as `DISPLAY_RESULT {resultType: "markdown"}` |
| `Task` | `collapsed` | `collapsed` | `hidden-popup` | `false` | Sub-agent spawn; output is the sub-agent's report |
| `TodoWrite` | `collapsed` | `collapsed` | `collapsed` | `false` | Internal task tracking; cheap row |
| `NotebookEdit` | `collapsed` | `collapsed` | `collapsed` | `false` | Jupyter cell edit |
| `BashOutput` | `collapsed` | `collapsed` | `collapsed` | `false` | Background-shell follow-up reads |
| `KillBash` | `collapsed` | `collapsed` | `collapsed` | `false` | Terminate a background bash |
| MCP-provided tools (`mcp__*`) | `collapsed` | `collapsed` | `collapsed` | `false` | Adapter falls back to a sensible default; consumers can override per-tool by name if needed |

The `Bash` row aligns with meridian-flow's `bash-tool.md` example
(input collapsed, stdout collapsed). meridian-channel's Claude `Bash` tool
behaves like a shell command runner just like meridian-flow's bash tool, so
the same defaults apply. There is no Claude equivalent of meridian-flow's
`Python` tool yet — Claude Code doesn't have a built-in persistent Python
kernel — but if a Claude MCP added one, the adapter would copy the
meridian-flow `python` row (`stdout: visible`).

**Adapter rule**: tool config defaults are read from `harness/ag_ui_events.py`
shared table. When a Claude tool isn't in the table, the adapter emits with
the conservative fallback (`input: collapsed, stdout: collapsed,
stderr: hidden-popup`) and logs the unknown tool to `stderr.log` so the
config can be added without code-side changes elsewhere.

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
  it as a control event. Approval routing through the `CAPABILITY` event
  (`runtime_permission_switch`) is a V1 deliverable.
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

| Codex JSON-RPC method/notification | AG-UI event(s) |
|---|---|
| `initialize` response | `RUN_STARTED`; `CAPABILITY {mid_turn_injection: "interrupt_restart", structured_reasoning_stream: false /* gap, see below */, runtime_model_switch: false, runtime_permission_switch: false, cost_tracking: true /* turn/completed carries usage */}` |
| `thread/start` response | session id captured to `output.jsonl` and the `RUN_STARTED` payload |
| `turn/start` (call) | `STEP_STARTED` (emitted when Codex acknowledges) |
| `notifications/item/reasoning/start` | `THINKING_START` |
| `notifications/item/reasoning/delta` | `THINKING_TEXT_MESSAGE_CONTENT` |
| `notifications/item/reasoning/end` | (THINKING blocks have no explicit END in AG-UI; the next event closes the block) |
| `notifications/item/agentMessage/start` | `TEXT_MESSAGE_START` |
| `notifications/item/agentMessage/delta` | `TEXT_MESSAGE_CONTENT` |
| `notifications/item/agentMessage/end` | `TEXT_MESSAGE_END` |
| `notifications/item/tool_call/start` (with `name`, `id`, optional `arguments_partial`) | `TOOL_CALL_START` (attach per-tool render config) |
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

### Per-Tool Render Config

Codex's tool set is more shell- and exec-oriented than Claude's. The names
below match the JSON-RPC `item/tool_call/*` `name` field as documented in
companion's `CODEX_MAPPING.md`.

| Tool name | input | stdout | stderr | producesResults | Notes |
|---|---|---|---|---|---|
| `shell` / `commandExecution` | `collapsed` | `collapsed` | `hidden-popup` | `false` | Codex's shell tool — same defaults as Claude `Bash` |
| `apply_patch` / `fileChange` | `collapsed` | `collapsed` | `collapsed` | `false` | File edit; output is patch confirmation |
| `read_file` | `collapsed` | `collapsed` | `collapsed` | `false` | Mirrors Claude `Read` |
| `write_file` | `collapsed` | `collapsed` | `collapsed` | `false` | Mirrors Claude `Write` |
| `web_search` | `collapsed` | `collapsed` | `collapsed` | `true` | Emits `DISPLAY_RESULT {resultType: "markdown"}` |
| `mcp__*` (MCP server tools) | `collapsed` | `collapsed` | `collapsed` | `false` | Conservative fallback; per-tool overrides as MCP catalog stabilizes |

The Codex tool set is smaller than Claude's because Codex models more
operations as variants of `commandExecution` rather than as named tools.
The adapter knows about the named ones above; for unknown tool names it
falls back to the conservative default and logs to `stderr.log`.

### Gaps and Open Questions

- **`item/reasoning/delta`** is documented in companion's mapping but
  companion's adapter does not currently stream it — it bulks reasoning into
  a single block. meridian-channel's Codex adapter should attempt to stream
  it (`THINKING_TEXT_MESSAGE_CONTENT` per delta) and fall back to a single
  bulked emission if Codex doesn't actually deliver deltas in practice.
  Validate against a real Codex stream during Phase 1.
- **`turn/completed` cost tracking**: companion's adapter doesn't extract
  `usage` and `cost` from `turn/completed`. meridian-channel must extract
  both for `RUN_FINISHED` and for the existing artifact contract. This is a
  small addition, not a research project.
- **MCP and `webSearch` approvals**: companion's reference auto-accepts
  these. meridian-channel matches that behavior in V0 to keep parity. V1
  exposes approvals as a `CAPABILITY {runtime_permission_switch: true}`
  control event.
- **Runtime model and permission switching**: not supported by Codex (set
  at `thread/start`). The `CAPABILITY` event reports `false` for both. The
  consumer must respect this and not render the affordances.
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
| `POST /session` response (session created) | `RUN_STARTED` (extract `session_id`); `CAPABILITY {mid_turn_injection: "http_post", structured_reasoning_stream: TBD-per-version, runtime_model_switch: false, runtime_permission_switch: false, cost_tracking: true}` |
| SSE `session.turn.started` | `STEP_STARTED` |
| SSE `message.reasoning.delta` (when present) | `THINKING_START` (first delta) + `THINKING_TEXT_MESSAGE_CONTENT` (each delta) |
| SSE `message.text.start` / `message.delta` / `message.text.end` | `TEXT_MESSAGE_START` / `TEXT_MESSAGE_CONTENT` / `TEXT_MESSAGE_END` |
| SSE `tool.invoked` (with `tool_name`, `tool_call_id`) | `TOOL_CALL_START` (attach per-tool render config) |
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

### Per-Tool Render Config

OpenCode's tool set is configurable per-deployment. The adapter ships
defaults for the standard OpenCode tool catalog; deployments with custom
tools can extend the table at install time (V1 — V0 ships the canonical set
only).

| Tool name | input | stdout | stderr | producesResults | Notes |
|---|---|---|---|---|---|
| `bash` | `collapsed` | `collapsed` | `hidden-popup` | `false` | Mirrors meridian-flow `bash-tool.md` |
| `read` | `collapsed` | `collapsed` | `collapsed` | `false` | File read |
| `write` | `collapsed` | `collapsed` | `collapsed` | `false` | File write |
| `edit` | `collapsed` | `collapsed` | `collapsed` | `false` | Patch edit |
| `grep` / `glob` | `collapsed` | `collapsed` | `collapsed` | `false` | Search tools |
| `webfetch` / `websearch` | `collapsed` | `collapsed` | `collapsed` | `true` | Markdown `DISPLAY_RESULT` |
| `task` | `collapsed` | `collapsed` | `hidden-popup` | `false` | Sub-agent spawn |
| custom MCP tools | conservative fallback | conservative fallback | `collapsed` | `false` | Logged to `stderr.log` for catalog growth |

### Gaps and Open Questions

- **SSE event naming**: the table above uses the documented OpenCode session
  event family, but specific event names should be validated against the
  current OpenCode build during Phase 1. The adapter is structured so a
  rename of one field is a one-line change in the mapping table; the
  taxonomy itself does not need to move.
- **Reasoning stream**: OpenCode's structured reasoning stream support
  varies by version. The `CAPABILITY` event reports
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

### Capabilities Enum

The `CAPABILITY` event uses the semantic enum from
[`findings-harness-protocols.md` §1](../../findings-harness-protocols.md):

```python
@dataclass
class HarnessCapabilities:
    mid_turn_injection: Literal["queue", "interrupt_restart", "http_post", "none"]
    runtime_model_switch: bool
    runtime_permission_switch: bool
    structured_reasoning_stream: bool
    cost_tracking: bool
```

| Harness | mid_turn_injection | runtime_model_switch | runtime_permission_switch | structured_reasoning_stream | cost_tracking |
|---|---|---|---|---|---|
| Claude Code | `queue` | `false` | `false` | `true` | `true` |
| Codex | `interrupt_restart` | `false` | `false` | `true` (planned, may bulk in V0) | `true` |
| OpenCode | `http_post` | `false` | `false` | version-detected | `true` |

The full per-harness wire-level details — how `queue`, `interrupt_restart`,
and `http_post` actually deliver the user message — live in
[`../harness/mid-turn-steering.md`](../harness/mid-turn-steering.md). This
table is the *what the consumer sees* view; the harness doc is the
*how the adapter implements it* view.

### Event Order Invariants

Every adapter must honor these ordering rules so the meridian-flow frontend
reducer behaves consistently. The reducer assumes them and breaks if they
are violated.

1. **Run boundary**: `RUN_STARTED` precedes every event; `RUN_FINISHED` is
   the last event. `CAPABILITY` is emitted exactly once, immediately after
   `RUN_STARTED`, before any `STEP_STARTED`.
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
7. **`CAPABILITY` is emitted exactly once per spawn.** Capabilities do not
   change mid-spawn (they're set at `thread/start` time for Codex, at
   harness launch for Claude, at session create for OpenCode).

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
- The `HarnessCapabilities` dataclass and the canonical enum values.
- The shared `ToolDisplayConfig` type and the per-harness tool config
  tables (Claude / Codex / OpenCode), so a tool config update is one row
  in one file.
- The serializer that turns events into JSONL lines on the streaming
  spawn's stdout.
- A small helper for synthesizing `DISPLAY_RESULT` events from common
  rich-content shapes (image bytes, markdown text, table data) to keep the
  three adapters DRY.

Each adapter (`claude.py`, `codex.py`, `opencode.py`) imports
`ag_ui_events` and is responsible for:

- Parsing its harness-native event stream (already partly done in
  `common.py` and `launch/stream_capture.py`).
- Calling the right `ag_ui_events.AGUI*` constructor for each native
  event.
- Owning its tool config table rows.
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
