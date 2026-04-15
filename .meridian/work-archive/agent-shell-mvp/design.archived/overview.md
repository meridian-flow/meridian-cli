# agent-shell-mvp Design Overview

> What this is: the meridian-channel refactor that lets a Go backend
> drive Claude Code, Codex, and OpenCode through one streaming spawn
> and steer them mid-turn.
>
> What this is not: a new product, a new frontend, a new wire schema, or
> a Go rewrite of meridian-channel.

Read [`reframe.md`](../reframe.md) first if you have not already. It is
the architectural correction that supersedes the pre-D34 framing of this
work item. This overview assumes that correction.

## What This Work Item Is

A scoped refactor of **meridian-channel** that adds three capabilities
to its existing harness layer. The contract those capabilities have to
match — the AG-UI event taxonomy, the 3-WS topology, the per-tool
behavior config — already lives in **meridian-flow** and is treated
here as a **read-only external contract**, not a thing this work item
defines.

External contract anchors (do not duplicate):

| File | Role |
|---|---|
| [`meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md`](../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md) | 3-WS topology, the three hooks, reconnect recovery, snapshot order |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md`](../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md) | End-to-end AG-UI event sequence with code traces |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/frontend/foundations.md`](../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/foundations.md) | Cross-cutting frontend model |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/frontend/state-management.md`](../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/state-management.md) | Store specs the activity stream reducer drives |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/frontend/thread-model.md`](../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/frontend/thread-model.md) | Thread/turn/work-item lifecycle |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/backend/python-tool.md`](../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/backend/python-tool.md) | Per-tool behavior config (example: python — stdout inline) |
| [`meridian-flow/.meridian/work/biomedical-mvp/design/backend/bash-tool.md`](../../../../../meridian-flow/.meridian/work/biomedical-mvp/design/backend/bash-tool.md) | Per-tool behavior config (example: bash — input + stdout collapsed) |

If a question is "what does the AG-UI event schema look like" or "how
does the activity stream reducer collapse a `bash` tool," the answer
lives in those files. This design tree only describes how
meridian-channel is going to **emit** that schema and **honor** that
config from inside its harness adapters.

## Three Deliverables

### 1. Harness adapters emit canonical AG-UI events (D36)

Today, each adapter (`claude.py`, `codex.py`, `opencode.py`) writes raw
harness wire output to `output.jsonl` and post-hoc extracts a final
`report.md`. The refactor adds **AG-UI event emission inside each
adapter** as a parallel output channel: the adapter consumes its own
harness's wire format (Claude stream-json NDJSON, Codex JSON-RPC over
stdio, OpenCode session events) and produces a normalized AG-UI event
stream that matches what meridian-flow's frontend reducer already
expects. Per-tool render config — `inputCollapsed`, `stdoutCollapsed`,
`stderrMode`, `producesResults` — is **frontend-resident** in
meridian-flow's `toolDisplayConfigs` registry; the wire only carries
`{toolName, toolCallId}` on `TOOL_CALL_START` and the reducer looks up
the config by tool name. The existing `report.md` and `output.jsonl`
artifacts stay intact — AG-UI is additive, not a replacement.

### 2. Streaming spawn mode + FIFO control protocol (D37)

A new invocation shape on `meridian spawn create` (working name
`--ag-ui-stream` to avoid colliding with the existing hidden `--stream`
debug flag at `cli/spawn.py:211`) where stdout is a JSONL stream of
AG-UI events. The control channel is a **per-spawn FIFO** at
`.meridian/spawns/<id>/control.fifo`, carrying JSONL `user_message`,
`interrupt`, and `cancel` frames. The FIFO is the **single
authoritative control ingress** — the streaming spawn does not also
read its own stdin as a control channel. The streaming spawn process
runs until the agent finishes naturally or a `cancel` frame arrives.
The existing per-spawn artifact directory (`.meridian/spawns/<id>/`),
the current report-extraction pipeline, and `meridian spawn show /
log / wait / files / stats` keep working unchanged — streaming is a
parallel invocation shape, not a replacement for the foreground or
background launches we already have.

### 3. `meridian spawn inject <spawn_id> "message"` CLI primitive (D37)

A top-level CLI command that injects a mid-turn `user_message` into a
running streaming spawn from a different process. Two consumers:
existing dev-workflow orchestrators steering their children mid-execution,
and meridian-flow's Go backend forwarding frontend user messages into a
running agent turn. Underneath, the CLI writes a `user_message` control
frame to a per-spawn control surface owned by the streaming spawn — see
[`harness/mid-turn-steering.md`](harness/mid-turn-steering.md) for the
full ownership story.

## Out Of Scope

Per D38 and D39, none of the following are part of this work item:

- **Strategy, extensions, packaging, frontend.** Pre-reframe `design/`
  subtrees were deleted; their concerns either belong at product strategy
  level or live in meridian-flow.
- **Local deployment packaging** (localhost binding, static frontend
  serving, single-user defaults). That is meridian-flow's local deployment
  workstream (D39 #3).
- **Backend 3-WS refactor** (`issue #8` rename + Project WS handler).
  meridian-flow's backend workstream (D39 #2).
- **Meridian-channel subprocess adapter inside meridian-flow's backend**.
  Same workstream.
- **`providers/claude-code/` (or any harness-shim provider) in
  meridian-llm-go.** Explicitly rejected by D40. The shell path does not
  go through meridian-llm-go at all.
- **In-process harness streaming.** `direct.py` (in-process Anthropic
  Messages API) keeps `supports_stream_events=False` and stays out of
  this refactor. The streaming surface is a subprocess-harness concern.

## Refactor Touchpoints

The explorer pre-pass mapped the load-bearing files. **37 files** are
on the critical path; the full table — file, status (`must change` /
`may change` / `unchanged`), current role, expected impact, consumers,
and risk — lives in [`refactor-touchpoints.md`](refactor-touchpoints.md).

The three highest-risk touchpoints, all in the harness layer, are:

- `src/meridian/lib/harness/claude.py`
- `src/meridian/lib/harness/codex.py`
- `src/meridian/lib/harness/opencode.py`

All three must gain AG-UI event emission and a FIFO control dispatcher
**without** regressing the existing artifact contracts (`report.md`,
`output.jsonl`, `stderr.log`, session-id extraction, `--from`, `--fork`,
reaper liveness). The risk profile is the inverse of the visible work:
the new code is moderate, the regressions are easy.

Two structural concerns from the touchpoints map deserve flagging in
the overview:

1. **`state/spawn_store.py` has no live-control metadata today.** A
   per-spawn control handle (FIFO or socket path) has to be designed
   into `paths.py` and `spawn_store.py` before `spawn inject` has
   anything authoritative to target. Covered in
   [`harness/mid-turn-steering.md`](harness/mid-turn-steering.md).
2. **`launch/process.py` already copies parent stdin into the child
   PTY for primary launches.** A naïve "streaming spawn owns its own
   stdin" approach will collide with that path and break interactive
   `meridian` sessions. Resolved by treating streaming mode as a
   non-PTY launch shape and routing `meridian spawn inject` through a
   dedicated per-spawn control FIFO instead of the streaming process's
   stdin. Covered in `harness/mid-turn-steering.md`.

## How To Navigate This Design

| Doc | What you get |
|---|---|
| [`harness/overview.md`](harness/overview.md) | One-page orientation to the harness layer after the refactor |
| [`harness/abstraction.md`](harness/abstraction.md) | Adapter interface — new methods, new DTOs, capability semantics, what stays unchanged |
| [`harness/adapters.md`](harness/adapters.md) | Per-harness translation rules (Claude, Codex, OpenCode), tool naming coordination (no wire config), regression risks |
| [`harness/mid-turn-steering.md`](harness/mid-turn-steering.md) | FIFO control protocol, control frame model, per-harness injection mechanics, `meridian spawn inject` CLI |
| [`events/overview.md`](events/overview.md) | What the AG-UI event taxonomy is and where its canonical definition lives |
| [`events/flow.md`](events/flow.md) | The AG-UI event sequence inside a streaming spawn lifecycle |
| [`events/harness-translation.md`](events/harness-translation.md) | Harness wire format → AG-UI event mapping tables (one section per harness) |
| [`refactor-touchpoints.md`](refactor-touchpoints.md) | The 37-file impact map — read this before touching any source file |

## Decision Anchors

Every claim in this design tree must trace back to one or more of the
following decisions in [`../decisions.md`](../decisions.md):

- **D34** — agent-shell-mvp is meridian-channel's GUI, not a new product
- **D35** — meridian-channel stays Python, no Go rewrite
- **D36** — AG-UI event taxonomy is the canonical output schema
- **D37** — Streaming spawn mode + FIFO control protocol
- **D38** — Scope collapse of agent-shell-mvp design tree
- **D39** — Workstream split across repositories
- **D40** — No `providers/claude-code/` in meridian-llm-go

Findings that ground the harness work, especially mid-turn semantics
across the three harnesses:

- [`findings-harness-protocols.md`](../findings-harness-protocols.md) —
  authoritative reference. **All three harnesses are tier-1, mid-turn
  steering is V0, capability is a semantic enum and not a boolean.**
