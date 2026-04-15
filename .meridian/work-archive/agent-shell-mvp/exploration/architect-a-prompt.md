# Architect A: rewrite overview.md + design/harness/ for agent-shell-mvp refactor

## Context

The agent-shell-mvp work item has been **reframed** (see
`$MERIDIAN_WORK_DIR/reframe.md` and decisions D34–D40 at
`$MERIDIAN_WORK_DIR/decisions.md`). The pre-reframe design tree has
already been sliced — strategy/extensions/packaging/frontend/execution
subtrees are deleted. Only `overview.md` + `harness/` + `events/`
remain, and this spawn rewrites `overview.md` + `harness/` from scratch
for the corrected scope.

### One-line scope

meridian-channel gains (1) AG-UI event emission in its harness
adapters, (2) a streaming spawn mode with a stdin control protocol,
and (3) a `meridian spawn inject <spawn_id> "message"` CLI primitive.
That's the refactor. Nothing else.

### External contract (read-only references)

The frontend contract (AG-UI event taxonomy, 3-WS topology, hook
contracts, per-tool behavior config) lives in **meridian-flow**, not
here. Reference it; do not restate it. Canonical files:

- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/data-flow.md` — 3-WS topology, hooks
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/streaming-walkthrough.md` — AG-UI event sequence with traces
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/foundations.md`
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/state-management.md`
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/frontend/thread-model.md`
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/backend/python-tool.md` — per-tool behavior example
- `/home/jimyao/gitrepos/meridian-flow/.meridian/work/biomedical-mvp/design/backend/bash-tool.md` — per-tool behavior example

Read the top of data-flow.md and streaming-walkthrough.md before
drafting. Point to them; do not duplicate them.

### What you must read first

Read in order:
1. `$MERIDIAN_WORK_DIR/reframe.md` — the corrected architecture
2. `$MERIDIAN_WORK_DIR/decisions.md` D34–D40 at the bottom — the decisions that justify the reframe
3. `$MERIDIAN_WORK_DIR/findings-harness-protocols.md` — authoritative harness protocol reference (Claude, Codex, OpenCode mid-turn semantics). **Claude queues, Codex interrupt-restarts, OpenCode HTTP POSTs — all three are tier-1.**
4. `$MERIDIAN_WORK_DIR/design/refactor-touchpoints.md` — the per-file refactor map from the explorer pre-pass. Use it to ground your structural analysis.

## Deliverables

Write **five files** under `$MERIDIAN_WORK_DIR/design/`:

### 1. `design/overview.md` (rewrite — 2–3 pages)

Replaces the existing overview (which still carries pre-reframe framing). Short and navigable:

- **What this work item IS**: meridian-channel harness adapter refactor + streaming spawn mode + stdin control protocol + `meridian spawn inject` CLI primitive. Three deliverables from D36/D37.
- **The external contract** it matches: the AG-UI event taxonomy + 3-WS topology + per-tool behavior config **already defined in meridian-flow** (link the canonical files). This work item references that contract, does not duplicate or redefine it.
- **Three deliverables** (one short paragraph each):
  1. Harness adapters emit canonical AG-UI events (D36)
  2. Streaming spawn mode + stdin control protocol (D37)
  3. `meridian spawn inject` CLI primitive (D37)
- **What is explicitly NOT in scope**: strategy, extensions, packaging, frontend, local deployment packaging, providers/claude-code in meridian-llm-go. Point to D38 and D39 for workstream split.
- **Refactor touchpoints**: point to `design/refactor-touchpoints.md` rather than restate the table. Mention the 37 load-bearing files summary number and the top-3 highest-risk files.
- **How to navigate this design**: a short table of contents pointing at `design/harness/overview.md`, `design/harness/abstraction.md`, `design/harness/adapters.md`, `design/harness/mid-turn-steering.md`, `design/events/*`, and `design/refactor-touchpoints.md`.

Do NOT restate strategy, extensions, frontend design, or packaging. Those are gone.

### 2. `design/harness/overview.md`

What the harness layer **does after the refactor**. How Claude Code,
Codex, and OpenCode fit under one abstraction. The adapter contract
at a high level. Pointers to the deeper files:
- `abstraction.md` for the protocol/interface
- `adapters.md` for per-harness translation rules
- `mid-turn-steering.md` for the stdin control protocol detail

Keep it short (1 page). This is the orientation page for the harness subtree.

### 3. `design/harness/abstraction.md`

The adapter interface for the refactor, in Python (meridian-channel
is Python — D35). The document describes the **target state** of the
interface, matching the existing meridian-channel conventions shown in
`refactor-touchpoints.md` (`adapter.py`, `common.py`, `launch_types.py`).

Cover:
- **Adapter responsibilities after the refactor** — three axes:
  (a) emit AG-UI events on an output channel,
  (b) accept stdin control messages (`user_message`, `interrupt`, `cancel`),
  (c) report capabilities (mid-turn injection semantic, runtime model switch, cost tracking, etc.)
- **Event emission surface** — how an adapter hands AG-UI events to
  the shared plumbing. Point to `ag_ui_events.py` (new sibling module
  per refactor-touchpoints structural analysis) as the canonical home
  for the event model types and the per-tool behavior config. Do NOT
  redefine the AG-UI event taxonomy — it lives in meridian-flow.
- **Stdin control surface** — how an adapter consumes control frames.
  Point to `control_channel.py` (new sibling module per the structural
  analysis). Describe the control frame model (`user_message`,
  `interrupt`, `cancel`) at the level of "what frames, what each means
  across harnesses," not at the level of wire format.
- **Capability reporting** — extend `HarnessCapabilities` in
  `adapter.py` so the frontend can render the right affordance per
  harness. Use the semantic-enum pattern from findings-harness-protocols.md:
  `mid_turn_injection: Literal["queue", "interrupt_restart", "http_post", "none"]`.
  Not a boolean.
- **Relationship to existing interfaces**: how the new surface sits
  alongside `SubprocessHarness`, `InProcessHarness`, `RunPromptPolicy`,
  `SpawnParams`, `SpawnResult`, `StreamEvent`. Which methods are new,
  which are extended, which are unchanged. Point to
  `refactor-touchpoints.md` for file-level detail.
- **In-process harness (`direct.py`) treatment**: out of scope per
  the explorer findings — direct.py stays non-streaming. Call this
  out explicitly so reviewers don't flag it.

### 4. `design/harness/adapters.md`

Per-harness translation rules. **One section per harness.** Each section covers:

- **Wire protocol today** (1–2 paragraphs): Claude stream-json NDJSON, Codex JSON-RPC over stdio, OpenCode HTTP session events. Use findings-harness-protocols.md as the authority.
- **Event translation rules**: map each harness's wire format events to the canonical AG-UI event taxonomy. Use a mapping table (a small one — don't try to cover every field). Leave the per-field detail to `design/events/harness-translation.md` (Architect B is producing that in parallel — just link to it).
- **Per-tool behavior config**: for each harness, enumerate its tool set and the default render config (bash: input collapsed, stdout collapsed; Read/Grep/Glob: collapsed; Python: stdout inline/visible; etc.). Reference the meridian-flow tool config examples (`python-tool.md`, `bash-tool.md`) rather than reinventing.
- **Report/session compatibility**: what about the existing `report.md`, `output.jsonl`, `stderr.log` contracts stays load-bearing? The refactor must NOT regress `spawn show`, `spawn log`, `spawn wait`, `--from`, `--fork`, or reaper semantics. Flag per-adapter regression risks from the touchpoints map.

### 5. `design/harness/mid-turn-steering.md`

The stdin control protocol in detail. This is the **differentiating feature** per findings-harness-protocols.md section "Mid-Turn Steering is Tier-1, Not Optional." Content:

- **Why mid-turn steering is tier-1**: 2 paragraphs grounded in the findings doc. Not a footnote.
- **Control frame model**: `user_message`, `interrupt`, `cancel`. Fields, semantics, version field (per D37 open question #2 — recommend JSONL with `version: "0.1"` field from day one).
- **Per-harness injection mechanics**:
  - **Claude Code**: write stream-json user message frame to harness stdin → queues to next turn boundary
  - **Codex app-server**: JSON-RPC `turn/interrupt` followed by `turn/start` with the new message as initial prompt
  - **OpenCode**: POST to the session's message endpoint
- **Capability reporting via AG-UI CAPABILITY event on spawn start**: the adapter emits a `CAPABILITY` event declaring its `mid_turn_injection` semantic (`queue` | `interrupt_restart` | `http_post` | `none`). The frontend/consumer uses this to render the right affordance. **Do not lie about wire-level behavior to fake uniformity.**
- **Stdin ownership question** (D37 open question #1): should the streaming spawn own its own stdin exclusively, or sit behind a per-spawn control FIFO in `.meridian/spawns/<id>/`? Take a position with reasoning. The refactor-touchpoints map shows `launch/process.py` currently copies stdin straight to the child PTY for primary launches, so a naïve "own stdin" approach will collide with interactive `meridian` sessions. Recommend a design: e.g., streaming mode uses stdin as the control channel (harness stdin is the adapter's responsibility, not passed through), and `meridian spawn inject` writes to a per-spawn control FIFO at `.meridian/spawns/<id>/control.fifo` OR directly to the streaming spawn's stdin if the injector owns the pipe. Surface the tradeoff explicitly.
- **Error reporting** (D37 open question #3): when an injected message can't be delivered, does the injector get a synchronous error, or an async `CAPABILITY_ERROR` event on the spawn's AG-UI stream? Recommend one; explain.
- **Integration with `meridian spawn wait / show / log`** (D37 open question #4): does streaming mode change those, or is it a parallel invocation shape? Recommend "parallel invocation shape" — streaming is a *mode* (new flag or subcommand), existing spawn inspection commands keep working against `.meridian/spawns/<id>/` artifacts.
- **`meridian spawn inject <spawn_id> "message"` CLI detail**: how the CLI resolves the target spawn (via `.meridian/spawns/<id>/` anchor per the touchpoints analysis), how it writes the control frame, what happens if the spawn is not in streaming mode (error? warning? fallback? recommend error).
- **Capability honesty**: unify capability (send_user_message works), surface semantics (queue vs interrupt vs POST) so consumers can render the right UI affordance.
- **Open questions still requiring user input**: enumerate as a bulleted list. Don't leave them buried.

## Principles

1. **Reference, don't duplicate.** When meridian-flow already defines the event taxonomy, 3-WS topology, or per-tool config, link to the canonical file instead of restating. Searchable file paths, not inline schema copies.
2. **Match existing meridian-channel conventions.** The refactor grows the existing `adapter.py`/`common.py`/`launch_types.py` surfaces; don't propose a parallel abstraction that replaces them.
3. **Preserve dogfood workflows.** Every existing dev-workflow orchestrator use case must continue to function. Call out per-adapter risks from the touchpoints map where you see them.
4. **Normalization at the adapter boundary.** AG-UI event translation happens **inside each adapter**, not in a post-hoc parsing layer. The adapter contract grows — it does not get bypassed.
5. **Capability honesty.** Unify capability, surface semantics honestly. Claude queues, Codex interrupt-restarts, OpenCode HTTP POSTs — that's real; don't paper over it.
6. **Decisions D34–D40 are the basis.** Every design claim must trace back to one or more of them. Where a claim doesn't, either find the existing decision or flag it as a new open question.

## Anti-patterns to avoid

- Do NOT restate the AG-UI event schema. Link to the meridian-flow docs.
- Do NOT invent a parallel "normalized schema" — D36 says AG-UI is the canonical schema.
- Do NOT talk about "agent-shell-mvp as a new product" — it is not. It is a refactor of meridian-channel to match an existing contract.
- Do NOT say things like "we will design X in V2" — D37 says mid-turn steering is tier-1/V0.
- Do NOT describe Codex as experimental or deferred — findings-harness-protocols.md corrected that.
- Do NOT propose adding `providers/claude-code/` anywhere — D40 explicitly rejects that.
- Do NOT reintroduce strategy, extensions, or packaging concerns.
- Do NOT touch `.agents/` or `.claude/agents/` — other agents' in-flight work.

## What to do with existing content

The existing `overview.md` and `design/harness/*.md` files carry some
pre-reframe framing. **Overwrite them.** Git history preserves the prior
content. Do not try to diff or preserve — start fresh with the corrected
framing.

## Deliverable paths

Write/overwrite these five files. Do not touch anything else in the design tree:
- `$MERIDIAN_WORK_DIR/design/overview.md`
- `$MERIDIAN_WORK_DIR/design/harness/overview.md`
- `$MERIDIAN_WORK_DIR/design/harness/abstraction.md`
- `$MERIDIAN_WORK_DIR/design/harness/adapters.md`
- `$MERIDIAN_WORK_DIR/design/harness/mid-turn-steering.md`

## Coordination with Architect B

Architect B is rewriting `$MERIDIAN_WORK_DIR/design/events/` **in
parallel** with you. Events covers:
- `events/overview.md`
- `events/flow.md`
- `events/harness-translation.md`

**Do not touch `design/events/`.** When your harness docs need to
reference event translation detail, link to the appropriate
`design/events/*.md` file by name. Events ships its own overview of
the AG-UI taxonomy anchored to meridian-flow's canonical docs; your
harness docs point at events, events points at meridian-flow, nobody
duplicates anything.

## Report format

At the end, report back with:
- Files written (with line counts)
- Decisions you took on open questions and the reasoning
- Anything you discovered that's not anticipated by reframe.md / decisions / touchpoints
- Any places where you had to choose between two plausible designs — the tradeoff and your pick
