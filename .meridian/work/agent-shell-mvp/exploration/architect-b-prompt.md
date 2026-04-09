# Architect B: rewrite design/events/ for AG-UI translation

## Context

The agent-shell-mvp work item has been **reframed** (see
`$MERIDIAN_WORK_DIR/reframe.md` and decisions D34–D40 at
`$MERIDIAN_WORK_DIR/decisions.md`). The pre-reframe design tree has
already been sliced — strategy/extensions/packaging/frontend/execution
subtrees are deleted. `design/events/` is the only subtree you are
responsible for in this spawn.

### One-line scope for your docs

`design/events/` describes **how meridian-channel's harness adapters
translate each harness's native event stream into the canonical AG-UI
event taxonomy defined in meridian-flow.** It is the event-level view
of the refactor from D36.

The pre-reframe `events/normalized-schema.md` is gone — it
speculatively defined a parallel normalized schema, which D36 rejects.
The corrected docs **anchor to AG-UI as the canonical schema** and
describe meridian-channel's translation responsibility.

### External contract (read-only references)

**The AG-UI event taxonomy is defined in meridian-flow, not here.** Your
job is to describe the translation, not redefine the taxonomy. Canonical
sources:

- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md` — **this is your primary reference.** End-to-end AG-UI event sequence during a turn, with traces. Read it fully before drafting.
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md` — 3-WS topology, Agent WS role, streaming reducer
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/backend/python-tool.md` — per-tool config example (python: stdout inline)
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/backend/bash-tool.md` — per-tool config example (bash: everything collapsed)
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/backend/display-results.md` if you can find it — structured result rendering

Reference them; do not duplicate them.

### What you must read first

1. `$MERIDIAN_WORK_DIR/reframe.md` — the corrected architecture
2. `$MERIDIAN_WORK_DIR/decisions.md` D34–D40 (bottom) — the decisions (especially D36 for AG-UI schema and the rejected parallel normalized schema)
3. `$MERIDIAN_WORK_DIR/findings-harness-protocols.md` — authoritative source for Claude stream-json NDJSON, Codex JSON-RPC `item/*` notifications, and OpenCode HTTP session event semantics. **All three harnesses are tier-1.**
4. `$MERIDIAN_WORK_DIR/design/refactor-touchpoints.md` — the per-file refactor map. Use it to ground where AG-UI translation belongs (adapter-level, with a new `harness/ag_ui_events.py` sibling per the structural analysis).
5. meridian-flow's `streaming-walkthrough.md` (top of this prompt). **Read this before drafting.**

## Deliverables

Write **three files** under `$MERIDIAN_WORK_DIR/design/events/`. The old files (`overview.md`, `flow.md`, `normalized-schema.md`) are being overwritten — do not preserve their content, start fresh.

### 1. `design/events/overview.md`

**Orientation page for the events subtree.** Short (1 page). Content:

- **What this subtree describes**: the adapter-level view of AG-UI event translation. meridian-channel harness adapters translate Claude stream-json / Codex `item/*` / OpenCode HTTP session events into the canonical AG-UI event taxonomy.
- **Where the taxonomy lives**: meridian-flow's biomedical-mvp design (link the two canonical files: `streaming-walkthrough.md` and `frontend/data-flow.md`). This subtree does **not redefine** the taxonomy.
- **Why AG-UI is the canonical schema (D36)**: one paragraph citing D36. Briefly explain that a parallel normalized schema was rejected because meridian-flow's frontend reducer already consumes AG-UI events and agent-shell-mvp is a local-deployment shape of the same frontend, not a new product.
- **Where translation happens**: at the adapter boundary, inside each harness adapter. Structural analysis in `refactor-touchpoints.md` recommends a new sibling module (`harness/ag_ui_events.py`) as the canonical home for the event model types and the per-tool behavior config used across all three adapters. Point to the harness subtree (`design/harness/abstraction.md`, `adapters.md`) for the adapter-side contract; this subtree covers the event-level view.
- **Navigation**: short TOC to `flow.md` (the AG-UI event sequence during a spawn with example traces) and `harness-translation.md` (per-harness wire format → AG-UI mapping tables).

### 2. `design/events/flow.md`

**The AG-UI event sequence during a meridian-channel streaming spawn,** from `RUN_STARTED` to `RUN_FINISHED`. Content:

- **Event sequence overview**: describe the canonical flow in order. Use the event names from meridian-flow's `streaming-walkthrough.md`:
  - `RUN_STARTED` → `CAPABILITY` (adapter-emitted capability frame per harness)
  - `STEP_STARTED` — turn boundary
  - `THINKING_START` / `THINKING_TEXT_MESSAGE_CONTENT` — where the harness supports it (Claude does, Codex partially per findings, OpenCode TBD)
  - `TEXT_MESSAGE_START` / `TEXT_MESSAGE_CONTENT` / `TEXT_MESSAGE_END` — assistant text deltas
  - `TOOL_CALL_START` / `TOOL_CALL_ARGS` / `TOOL_CALL_END` — tool lifecycle
  - `TOOL_OUTPUT {stream: stdout|stderr}` — streaming tool execution output
  - `TOOL_CALL_RESULT` — tool completion
  - `DISPLAY_RESULT {resultType}` — structured tool results (text, markdown, image, table, mesh_ref, etc.)
  - `RUN_FINISHED`
- **Per-event origin**: for each event, briefly note which harness fields produce it. Example: `TOOL_CALL_START` from Claude comes from a stream-json `assistant` event with `content.type == "tool_use"`; from Codex from an `item/tool_call/start` notification; from OpenCode from a session SSE `tool.invoked` event. Keep this level terse — the full mapping tables live in `harness-translation.md`, so link there.
- **Example traces**: borrow the trace format from meridian-flow's `streaming-walkthrough.md` (the sequence-diagram + step-by-step walkthrough). Show at least two example traces:
  1. **Simple text turn** (no tool calls): user message → assistant text deltas → `RUN_FINISHED`. Pick a minimal example.
  2. **Tool-call turn with inline output** (e.g., bash tool running a command that prints stdout): show `TOOL_CALL_START` → `TOOL_CALL_ARGS` → `TOOL_CALL_END` → `TOOL_OUTPUT` (streaming) → `TOOL_CALL_RESULT`, with per-tool behavior config notes (e.g., "bash: input collapsed, stdout collapsed by default; Python: stdout visible inline").
  Use mermaid `sequenceDiagram` per the streaming-walkthrough.md style. Keep the actors to: User, Frontend/Consumer, meridian-flow backend (optional — it's just a pass-through), meridian-channel streaming spawn, Harness subprocess, LLM. The actor of interest is the meridian-channel streaming spawn because that's where this refactor lives.
- **Per-tool behavior config attachment**: explain that `TOOL_CALL_START` events carry the per-tool render config (`input: visible|collapsed`, `stdout: visible|collapsed|inline`, `stderr: ...`) so the frontend reducer doesn't have to special-case tool names. Reference the meridian-flow backend tool examples (`python-tool.md`, `bash-tool.md`) for the concrete config values. Mention that each adapter owns its harness's tool-config dictionary and emits it on `TOOL_CALL_START`.
- **Capability event placement**: the adapter emits `CAPABILITY` right after `RUN_STARTED` so the consumer knows which mid-turn injection semantic to render before the first turn even begins. Cite D37 and `findings-harness-protocols.md`.
- **Lifecycle integration** with existing meridian-channel artifacts: call out that even in streaming mode, the adapter still writes `report.md`, `output.jsonl`, `stderr.log`, `prompt.md`, `params.json` to `.meridian/spawns/<id>/` per the touchpoints map, so `spawn show`, `spawn log`, `spawn wait`, `--from`, `--fork`, and `reaper.py` keep working. The AG-UI stream is additive to, not a replacement for, the existing artifact contract.
- **Stdin control frames**: do NOT deep-dive here — point to `design/harness/mid-turn-steering.md`. Mention only that control frames arriving mid-turn can cause `STEP_STARTED` → new turn boundary events (Codex) or will be queued and appear at the next turn boundary (Claude) or will be POSTed and acknowledged asynchronously (OpenCode). Refer to the harness doc for per-harness semantics.

### 3. `design/events/harness-translation.md`

**The mapping tables — one section per harness.** This replaces the pre-reframe `normalized-schema.md`. Content:

**Structure**: three sections — Claude Code, Codex, OpenCode. Each section has the same shape.

For each harness:
1. **Wire format overview** (1 paragraph): the harness's native streaming format. For Claude: NDJSON over stdout, stream-json `type` discriminator. For Codex: JSON-RPC 2.0 over stdio, `item/*` notifications. For OpenCode: HTTP session API / SSE. Cite findings-harness-protocols.md.
2. **Mapping table**: two columns, harness-native event → AG-UI event(s). Example rows:

   | Harness event | AG-UI event(s) |
   |---|---|
   | `stream-json {type:"assistant", content:[{type:"text", text:"..."}]}` | `TEXT_MESSAGE_START` (first delta), `TEXT_MESSAGE_CONTENT` (each delta), `TEXT_MESSAGE_END` (on completion) |
   | `stream-json {type:"assistant", content:[{type:"tool_use", ...}]}` | `TOOL_CALL_START` + `TOOL_CALL_ARGS` (streaming JSON deltas) + `TOOL_CALL_END` |
   | ... | ... |

   Cover: run lifecycle, thinking, text, tool call lifecycle, tool output, tool result, display results. You do NOT need to enumerate every possible harness event — focus on what's load-bearing for the frontend reducer meridian-flow already expects.
3. **Per-tool behavior config**: enumerate the harness's tool set and the render config meridian-flow's reducer expects. For Claude Code: its built-in tool set (Read, Write, Edit, Bash, Grep, Glob, Task, etc.). For Codex: its tool set. For OpenCode: its tool set. Reference the meridian-flow canonical tool config examples (`python-tool.md`, `bash-tool.md`). Do NOT invent tool configs; use the ones that already exist and extend minimally where a Claude-specific tool (e.g., `Grep`) is not in the meridian-flow examples.
4. **Gaps and open questions**: what does this harness NOT emit cleanly, per findings-harness-protocols.md? (Examples: companion's Codex adapter doesn't stream `item/reasoning/delta`; MCP approvals are auto-accepted; Codex `turn/completed` cost tracking not extracted yet.) Call these out so implementers know what to push back on.

After the three harness sections, add a **Cross-harness notes** section:
- **Capabilities enum**: `mid_turn_injection: Literal["queue","interrupt_restart","http_post","none"]` — point to `design/harness/mid-turn-steering.md` and `findings-harness-protocols.md`.
- **Event order invariants**: what ordering assumptions the frontend reducer makes that all three adapters must honor (e.g., `TOOL_CALL_START` must precede `TOOL_CALL_ARGS`, `TOOL_CALL_RESULT` follows `TOOL_CALL_END`, etc.). Use meridian-flow's `streaming-walkthrough.md` as the source of truth.
- **Translation-layer home**: one paragraph recapping that the translation lives in a new `harness/ag_ui_events.py` sibling module per the refactor-touchpoints structural analysis, not in `transcript.py` (post-hoc text) and not in `common.py` (would become a dumping ground). Each adapter owns its per-harness translation logic and calls into the shared `ag_ui_events.py` types.

## Principles

1. **Reference, don't duplicate.** meridian-flow owns the AG-UI event taxonomy. Your docs describe **how meridian-channel's adapters translate into it** — they do NOT restate the taxonomy. Every section should link to the canonical meridian-flow doc when describing an event.
2. **D36 is the basis.** No parallel normalized schema. If you find yourself defining "our own" event types, stop — you're drifting from D36.
3. **Match findings-harness-protocols.md.** It is the authoritative source for Claude/Codex/OpenCode wire formats and their known gaps. Do not contradict it.
4. **Example traces for clarity.** Abstract tables are less useful than a real trace showing "user says X → these events come out." Borrow the format from meridian-flow's `streaming-walkthrough.md`.
5. **Dogfood compatibility.** The streaming AG-UI output is additive to `report.md` / `output.jsonl` / `stderr.log`, which existing dogfood workflows (spawn show/log/wait, --from, --fork, reaper) depend on per the touchpoints map. Call this out in `flow.md`.

## Anti-patterns to avoid

- Do NOT redefine the AG-UI event taxonomy. Link to meridian-flow.
- Do NOT invent a parallel "meridian-channel normalized schema." D36 killed it.
- Do NOT describe Codex as experimental or deferred. All three harnesses are tier-1.
- Do NOT touch anything outside `design/events/`. Architect A is handling `overview.md` + `design/harness/` in parallel.
- Do NOT touch `.agents/` or `.claude/agents/`.
- Do NOT propose streaming mode as a replacement for the existing artifact contract — it is additive.

## Deliverable paths

Overwrite these three files. Nothing else in the design tree:
- `$MERIDIAN_WORK_DIR/design/events/overview.md`
- `$MERIDIAN_WORK_DIR/design/events/flow.md`
- `$MERIDIAN_WORK_DIR/design/events/harness-translation.md`

The previous `normalized-schema.md` is being replaced by
`harness-translation.md`. Use `git rm design/events/normalized-schema.md`
if you have the capability, or just overwrite it with an empty file and
mention it in your report — the orchestrator will handle the deletion.

## Coordination with Architect A

Architect A is rewriting `design/overview.md` and `design/harness/*.md`
**in parallel** with you. Harness covers:
- `harness/overview.md` — harness-layer orientation
- `harness/abstraction.md` — adapter protocol interface
- `harness/adapters.md` — per-harness translation rules (high-level)
- `harness/mid-turn-steering.md` — stdin control protocol detail

**Do not touch `design/harness/` or `design/overview.md`.** When your
events docs need to reference the harness contract, link by path.

**Division of labor on harness overlap**: `design/harness/adapters.md`
covers the per-harness translation at the *adapter contract* level
(what each adapter must do, what its risks are). `design/events/harness-translation.md`
covers the per-harness translation at the *event mapping* level (which
native event becomes which AG-UI event). The harness doc is an adapter
story, the events doc is a protocol mapping story. They link to each
other but don't duplicate.

## Report format

At the end, report back with:
- Files written (with line counts)
- What `normalized-schema.md` is being replaced by and confirm the old file is either overwritten or flagged for deletion
- Anything you found in meridian-flow's streaming-walkthrough.md that contradicts findings-harness-protocols.md (if nothing, say so)
- Any cross-harness invariants you surfaced that weren't in the source docs
- Design choices you made and the reasoning
