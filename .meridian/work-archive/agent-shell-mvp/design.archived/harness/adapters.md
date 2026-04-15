# Per-Harness Adapters

> What this is: per-harness translation rules — wire format today,
> AG-UI mapping summary, per-tool render config, regression risks.
>
> What this is not: the full per-field harness → AG-UI mapping table.
> That lives in [`../events/harness-translation.md`](../events/harness-translation.md)
> (Architect B). This doc points at it; do not duplicate it.

Up: [`overview.md`](overview.md).

## All Three Are Tier-1

Per [`../../findings-harness-protocols.md`](../../findings-harness-protocols.md),
**Claude Code, Codex app-server, and OpenCode are all tier-1** design
targets with stable, programmatic, mid-turn-capable control surfaces.
Earlier framing that treated Codex as experimental or deferred is
wrong and is corrected throughout this doc and
[`mid-turn-steering.md`](mid-turn-steering.md).

Implementation order is a product decision, not a protocol decision.
The abstraction has to fit all three from day one.

## Claude Code

### Wire Protocol Today

Claude Code runs as a subprocess driven by `--input-format stream-json
--output-format stream-json`, exchanging NDJSON frames over
stdin/stdout. The current `claude.py` adapter builds the command,
captures stdout into `output.jsonl`, runs `extract_report` /
`extract_session_id` / `extract_usage` against the captured artifacts
on completion, and returns a `SpawnResult`. Claude streams thinking,
text, and tool use as separate JSON message families, plus tool result
frames flow back in via the same stream.

Per-line frame families relevant to AG-UI translation:

- `system` boot/handshake frames — translate to `RUN_STARTED`
  (capabilities are reported out-of-band via `params.json` at launch
  time, not as a wire event — see
  [`mid-turn-steering.md`](mid-turn-steering.md))
- `assistant` message frames with content blocks (`text`, `thinking`,
  `tool_use`) — translate to `TEXT_MESSAGE_*`, `THINKING_*`,
  `TOOL_CALL_*`
- `user` message frames with `tool_result` content blocks — translate
  to `TOOL_CALL_RESULT` and `TOOL_OUTPUT`
- `result` summary frame — `RUN_FINISHED`

### AG-UI Translation Summary

| Claude wire | AG-UI event |
|---|---|
| `system` boot | `RUN_STARTED` |
| `assistant` text content | `TEXT_MESSAGE_START` / `TEXT_MESSAGE_CONTENT` / `TEXT_MESSAGE_END` |
| `assistant` thinking content | `THINKING_START` / `THINKING_TEXT_MESSAGE_CONTENT` |
| `assistant` `tool_use` block | `TOOL_CALL_START` (`{toolName, toolCallId}` only) + `TOOL_CALL_ARGS` |
| Tool start/finish boundary | `TOOL_CALL_END` |
| `user` `tool_result` content | `TOOL_CALL_RESULT` + `TOOL_OUTPUT` |
| `result` summary | `RUN_FINISHED` (with token usage) |

The full per-field mapping (which Claude attribute fills which AG-UI
field, how streaming text deltas frame `TEXT_MESSAGE_CONTENT`, how
`tool_use` argument streaming maps to incremental `TOOL_CALL_ARGS`)
lives in [`../events/harness-translation.md`](../events/harness-translation.md).

Claude is the only tier-1 harness that exposes a structured reasoning
stream today, so `capabilities.structured_reasoning_stream = true` in
the `params.json` capability bundle.

### Tool Naming Coordination (No Per-Tool Wire Config)

**The wire format does not carry per-tool render config.** Per
meridian-flow's [`frontend/component-architecture.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md),
`ToolDisplayConfig` is a **frontend-resident** dictionary
(`toolDisplayConfigs: Record<string, ToolDisplayConfig>`) keyed by
`toolName`. The reducer looks up the config when it sees
`TOOL_CALL_START` and applies whatever `inputCollapsed`,
`stdoutCollapsed`, `stderrMode`, `producesResults`, optional `label`,
and optional `icon` the registry provides.

The Claude adapter's job on `TOOL_CALL_START` is therefore to emit the
canonical Claude tool name on the `toolName` field, paired with a
`toolCallId`. That's it. No per-tool config dict on the wire, no
adapter-side render table, no in-Python lookup.

What this requires from the Claude adapter is **naming
coordination**: the tool names the adapter emits must match the keys
the meridian-flow reducer expects. The current cloud reducer uses keys
like `bash`, `python`, `Read`, etc. For each Claude built-in or MCP
tool the local-deployment path will exercise, the adapter emits the
same key the cloud path emits. If a Claude tool name and a
meridian-flow registry key disagree, the local path falls back to the
reducer's default render config — which is acceptable but visible.

**Coordination checklist** (one row per built-in to verify against the
meridian-flow registry before V0 ships):

- `Bash` / `bash`
- `Read`
- `Grep`
- `Glob`
- `Edit`, `Write`, `MultiEdit`
- `WebFetch`, `WebSearch`
- `Task` (sub-agent)
- MCP tool: `python`
- MCP tools: any other configured tools

Resolution discipline: when a name disagrees, **change the adapter's
emitted name** to match the registry, do not push a new key into
meridian-flow. The frontend registry is the source of truth (D36).

### Report / Session Compatibility

The Claude adapter must keep producing every artifact the existing
dogfood workflow depends on:

- `report.md` — produced by Claude itself or extracted from the
  assistant tail per the existing fallback chain (`launch/report.py`,
  `extract_report`).
- `output.jsonl` — the existing raw JSONL capture path stays. AG-UI
  events are written to a **separate sink** (the spawn's stdout in
  `--ag-ui-stream` mode, or a sibling artifact file in non-streaming
  mode).
- `stderr.log` — unchanged. `ops/spawn/query.py` reads it for the
  running-spawn last-assistant snippet that drives `--from`.
- Session id extraction — unchanged. `extract_session_id`,
  `resolve_session_file`, `detect_primary_session_id` continue against
  Claude's session file shape.
- `--continue` / `--continue --fork` — unchanged. The streaming-mode
  launch flavor inherits the existing session-resume path.

**Regression risks specific to Claude:**

- `tests/harness/test_extraction.py` exercises the report fallback,
  written-files extraction, and usage extraction against synthetic
  Claude output. Any change to how `output.jsonl` is written must
  keep those test fixtures parseable.
- `tests/exec/test_claude_*` (per the touchpoints map) covers
  Claude-specific lifecycle behavior. The streaming-mode launch
  flavor must not change finalization order, signal handling, or
  report-watchdog timing.
- `launch/process.py` already copies parent stdin to the child PTY
  for primary launches. Streaming mode must take a separate launch
  path that does **not** PTY-relay parent stdin — see
  [`mid-turn-steering.md`](mid-turn-steering.md).

## Codex (`codex app-server`)

### Wire Protocol Today

Codex runs as `codex app-server` (or `codex exec --json` for the
existing meridian-channel `codex.py` adapter), exchanging
**JSON-RPC 2.0** over stdio. Per the findings doc, the **core
protocol is stable**: `initialize`/`initialized` handshake,
`thread/start`, `thread/resume`, `turn/start`, `turn/interrupt`, plus
`item/*` notifications for streaming output. WebSocket transport is
the experimental part; meridian-channel uses stdio, which is stable.

The `item/*` notifications cover the same conceptual surface as
Claude's stream-json, just framed differently:

- `item/agentMessage` — assistant text / final response
- `item/commandExecution` — tool call lifecycle for shell-style tools
- `item/fileChange` — tool call lifecycle for edit-style tools
- `item/reasoning` — thinking content (bulk-only in companion's
  reference adapter; streaming reasoning is a known gap)
- `item/webSearch`, `item/mcpToolCall` — additional tool families
- `item/contextCompaction` — context-window management notifications
- `item/*/requestApproval` — approval gate requests (server responds
  with decision)

### AG-UI Translation Summary

| Codex wire | AG-UI event |
|---|---|
| `initialized` | `RUN_STARTED` |
| `item/agentMessage` (text deltas) | `TEXT_MESSAGE_START` / `_CONTENT` / `_END` |
| `item/reasoning` (bulk) | `THINKING_START` + a single `THINKING_TEXT_MESSAGE_CONTENT` |
| `item/commandExecution` start | `TOOL_CALL_START` (`{toolName: "bash", toolCallId}`) + `TOOL_CALL_ARGS` |
| `item/commandExecution` output stream | `TOOL_OUTPUT` (stream: stdout/stderr) |
| `item/commandExecution` complete | `TOOL_CALL_END` + `TOOL_CALL_RESULT` |
| `item/fileChange` lifecycle | `TOOL_CALL_START` (`{toolName: "edit"}` or matching registry key) + `TOOL_CALL_END` + `TOOL_CALL_RESULT` |
| `item/webSearch`, `item/mcpToolCall` | `TOOL_CALL_*` (canonical tool name only — no per-tool config on the wire) |
| `item/contextCompaction` | (internal — no AG-UI event in V0; logged for diagnostics) |
| `turn/completed` | `RUN_FINISHED` |

The detailed per-field translation (the JSON-RPC envelope, the item
type discriminators, how `turn/completed` is decoded for token usage
when present) lives in
[`../events/harness-translation.md`](../events/harness-translation.md).
**Companion's [`web/CODEX_MAPPING.md`](https://github.com/The-Vibe-Company/companion)
is the best available reference** for this translation — read it,
reimplement in Python against our own AG-UI model, do not vendor.

Known capability gaps from companion's reference adapter (per the
findings doc) the V0 Codex adapter inherits and declares honestly in
the `params.json` capability bundle, using the canonical flat shape
from [`abstraction.md`](abstraction.md):

- `structured_reasoning_stream: false` — companion handles reasoning
  bulk-only; `item/reasoning/delta` streaming is a known follow-up.
  V0 Codex adapter declares **false**.
- `runtime_model_switch: false` — Codex sets the model at
  `thread/start`; runtime switching is not in the protocol.
- `cost_tracking: false` for V0 — declare honestly. Companion does
  not surface per-token usage from `turn/completed` today, and the
  V0 Codex adapter inherits that gap. Flip to `true` when an
  implementation wires `turn/completed` token usage through to the
  artifact contract.

### Tool Naming Coordination (No Per-Tool Wire Config)

Same rule as Claude: the wire format does not carry per-tool config
(see [`frontend/component-architecture.md`](../../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/component-architecture.md)).
The adapter's job is to translate each Codex item type into a
canonical `toolName` that matches a key in meridian-flow's
`toolDisplayConfigs` registry. The reducer applies the registry's
config when it sees `TOOL_CALL_START`.

**Coordination checklist** (one row per Codex item type to verify
against the meridian-flow registry before V0 ships):

- `item/commandExecution` (shell) → `bash`
- `item/fileChange` → `edit` (or whatever the registry uses for
  edit-style tools)
- `item/webSearch` → `webSearch` (or `web_search`)
- `item/mcpToolCall` (python-style) → `python`
- `item/mcpToolCall` (other) → use the MCP-declared tool name
  verbatim; the registry handles unknown tools with a default config

When a name disagrees with the registry, change the adapter's emitted
name, not the registry. The frontend registry is the source of
truth (D36).

### Report / Session Compatibility

The Codex adapter must keep producing every artifact the existing
dogfood workflow depends on. The touchpoints map flags Codex as one
of the highest-risk adapters because command construction, fork
materialization, and session extraction are all coupled in `codex.py`
today:

- `report.md` — extracted from the agent's tail per the existing
  fallback chain. The streaming AG-UI path must not change when or how
  `report.md` becomes durable, because `state/reaper.py` treats
  `report.md` as a completion signal.
- `output.jsonl` — unchanged. The raw JSON-RPC frames continue to be
  written; AG-UI translation is teed off the same line stream and
  written to the AG-UI sink separately.
- Session fork (`continue_fork`) — `tests/test_launch_process.py`
  exercises Codex fork materialization. The streaming launch flavor
  must not break this path.
- Session-id extraction from `extract_session_id` and
  `resolve_session_file` — unchanged.

**Regression risks specific to Codex:**

- `tests/test_launch_process.py` covers Codex fork materialization
  and PTY winsize forwarding.
- `tests/harness/test_extraction.py` exercises Codex output
  extraction.
- The JSON-RPC framing is line-oriented but each frame can be larger
  than typical Claude frames. `launch/stream_capture.py` already
  handles large lines and redaction; the AG-UI translator must not
  introduce a new line-size assumption.

> **File size sprawl risk (deferred to implementation).** `codex.py`
> is already ~511 lines before the refactor and gains AG-UI
> translation plus FIFO control dispatch in this work item. Keep one
> adapter entrypoint (`codex.py`) but if the file grows past ~800
> LoC or accumulates more than three responsibilities (command
> building + JSON-RPC framing + AG-UI translation + control
> dispatch), split out small sibling helpers — `codex_translate.py`
> for the wire→AG-UI mapping or `codex_rpc.py` for the JSON-RPC
> envelope handling. Decide during the implementation pass once the
> real shape is visible; do not preemptively fragment the module in
> the design.

## OpenCode

### Wire Protocol Today

OpenCode is driven via the **HTTP session API** exposed by `opencode
serve` (also ACP NDJSON for some flows). The current `opencode.py`
adapter builds a launch command, captures session events to log files,
and resolves session ownership from those files. Per the findings doc,
this is the **cleanest of the three** wire protocols — session-scoped,
designed explicitly to be driven by external tools.

Mid-turn injection on OpenCode is a `POST` to the live session's
message endpoint. No interrupt, no queue, no stream-format negotiation.

### AG-UI Translation Summary

| OpenCode session event | AG-UI event |
|---|---|
| Session start | `RUN_STARTED` |
| Assistant text delta | `TEXT_MESSAGE_START` / `_CONTENT` / `_END` |
| Tool invocation start | `TOOL_CALL_START` (`{toolName, toolCallId}` only) + `TOOL_CALL_ARGS` |
| Tool invocation output | `TOOL_OUTPUT` |
| Tool invocation complete | `TOOL_CALL_END` + `TOOL_CALL_RESULT` |
| Session done | `RUN_FINISHED` |

OpenCode's reasoning surface is harness-dependent on the underlying
model; the adapter declares `structured_reasoning_stream` (in the
`params.json` capability bundle) based on what the wired model
actually returns. Default `false` in V0.

Per-field mapping lives in
[`../events/harness-translation.md`](../events/harness-translation.md).

### Tool Naming Coordination (No Per-Tool Wire Config)

Same rule as Claude and Codex: the wire format does not carry
per-tool config. The OpenCode adapter emits canonical `toolName`s
matching the meridian-flow registry; the reducer applies the
config. The OpenCode tool families overlap heavily with Claude's
built-ins (shell, read/search/glob, edit/write, MCP `python`, other
MCP), so the coordination checklist is the same shape as Claude's:
verify each emitted name against the registry before V0 ships, and
when in doubt, change the adapter's emitted name to match the
registry rather than pushing a new key into meridian-flow.

### Report / Session Compatibility

OpenCode's existing extraction paths in `opencode.py` and
`tests/ops/test_session_log.py` depend on the current session log
file shapes. The refactor must:

- Continue producing the same `report.md`, `output.jsonl`,
  `stderr.log` artifacts — AG-UI is additive, not a replacement.
- Continue resolving session ownership from log files (the
  `owns_untracked_session` path).
- Not regress the compaction-aware session log parser
  (`ops/session_log.py`) that exposes `meridian session log`.

**Regression risks specific to OpenCode:**

- `tests/ops/test_session_log.py` is the main regression boundary. If
  OpenCode session log files change shape because the refactor moves
  durable event capture into a new format, the compaction parser
  needs an update in lockstep.
- `tests/harness/test_extraction.py` exercises OpenCode output
  extraction.
- HTTP injection means the OpenCode `ControlDispatcher` needs an HTTP
  client and the live session URL — plumbing the URL through to the
  control reader is an OpenCode-specific concern that the other two
  adapters do not have.

## Summary Of Regression Surfaces (All Three)

The dogfood workflow depends on artifacts and behaviors that
**must not regress** for any adapter. From the touchpoints map:

| Surface | Owned by | Risk |
|---|---|---|
| `report.md` durability + content | `launch/extract.py`, `launch/report.py`, adapter `extract_report` | reaper treats `report.md` as completion signal |
| `output.jsonl` content | `launch/stream_capture.py`, `launch/runner.py` | `spawn log`, `--from`, transcript parsers all read it |
| `stderr.log` content | `launch/runner.py` | `ops/spawn/query.py` reads running-spawn assistant tail |
| Session id extraction | adapter `extract_session_id`, `detect_primary_session_id` | `--continue`, session ownership, `meridian session log` |
| Session fork (Codex) | adapter `fork_session`, `seed_session` | `tests/test_launch_process.py` |
| Per-spawn artifact directory | `state/paths.py` | every existing inspection command |
| Token usage extraction | adapter `extract_usage` | `meridian spawn stats`, dashboards |
| Reaper liveness | `state/reaper.py` | orphan detection on crash |

The refactor adds AG-UI events on top of these — it does not move them.
The implementation discipline is: **AG-UI sink first, every existing
artifact contract second**, and the existing artifact contracts win
when the two pull in different directions.

## Read Next

- [`mid-turn-steering.md`](mid-turn-steering.md) — the per-harness
  injection mechanics and the FIFO control protocol in detail.
- [`../events/harness-translation.md`](../events/harness-translation.md)
  — the per-field mapping tables this doc references.
- [`../refactor-touchpoints.md`](../refactor-touchpoints.md) — the
  per-file impact map and the regression test/smoke surface.
