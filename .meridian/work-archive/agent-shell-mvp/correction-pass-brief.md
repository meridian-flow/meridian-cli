# Correction Pass Brief — agent-shell-mvp design

You are executing a comprehensive correction pass on the `agent-shell-mvp`
design corpus. This is a rewrite + restructure, not an annotation pass. Treat
the existing flat `design/*.md` as raw material to be transformed, not
canonical text to preserve.

## Inputs you MUST read first, in this order

1. `$MERIDIAN_WORK_DIR/decisions.md` — **all of it**, but especially D21–D28.
   D21–D28 are the governing corrections for this pass.
2. `$MERIDIAN_WORK_DIR/requirements.md` — original contract (still binding
   except where D21–D28 override).
3. `$MERIDIAN_WORK_DIR/synthesis.md` — prior-pass synthesis.
4. `$MERIDIAN_WORK_DIR/findings-harness-protocols.md` — harness protocol
   facts (Claude / Codex / OpenCode).
5. `$MERIDIAN_WORK_DIR/design/overview.md`
6. `$MERIDIAN_WORK_DIR/design/harness-abstraction.md`
7. `$MERIDIAN_WORK_DIR/design/event-flow.md`
8. `$MERIDIAN_WORK_DIR/design/frontend-protocol.md`
9. `$MERIDIAN_WORK_DIR/design/frontend-integration.md`
10. `$MERIDIAN_WORK_DIR/design/interactive-tool-protocol.md`
11. `$MERIDIAN_WORK_DIR/design/local-execution.md`
12. `$MERIDIAN_WORK_DIR/design/repository-layout.md`
13. `$MERIDIAN_WORK_DIR/design/agent-loading.md`

Also consider prior reviewer findings at
`$MERIDIAN_WORK_DIR/reviews/` (alignment, feasibility, refactor, solid,
convergence) — and the most-recent p1138 review summary in this brief's
"Prior review" section below.

## What you produce

### 1. Restructured `design/` tree (hierarchical, progressive disclosure)

Replace the flat `design/*.md` layout with a folder hierarchy. Proposed
starting taxonomy (refine as needed, but justify deviations):

```
design/
├── overview.md                    # whole-MVP, complete at this level
├── strategy/
│   ├── overview.md                # D21/D22/D23/D28 in one place
│   └── funnel-and-moat.md         # optional split if overview grows too big
├── harness/
│   ├── overview.md
│   ├── abstraction.md             # HarnessAdapter protocols, split interfaces
│   ├── adapters.md                # Claude V0 adapter; Codex/OpenCode V1 stubs
│   └── mid-turn-steering.md       # tier-1 V0 per findings
├── events/
│   ├── overview.md
│   ├── normalized-schema.md       # canonical contract (D1) — wire contract block
│   └── flow.md                    # router / turn orchestrator / tool coordinator
├── frontend/
│   ├── overview.md                # generic chat UI (D25), ships no domain code
│   ├── chat-ui.md                 # message list, input, chrome
│   ├── content-blocks.md          # dispatcher, 3–5 core renderers only
│   └── protocol.md                # published wire contract — VERSION field
├── extensions/
│   ├── overview.md                # D26 interaction-layer model
│   ├── interaction-layer.md       # composite frontend+MCP pair contract
│   ├── relay-protocol.md          # frontend ↔ backend ↔ paired MCP, VERSION field
│   └── package-contract.md        # what a mars extension declares (points to mars-mcp-packaging)
├── execution/
│   ├── overview.md
│   ├── local-model.md             # subprocess tool execution, NO shell-owned venvs
│   └── project-layout.md          # user project is a normal uv-managed Python project
└── packaging/
    ├── overview.md                # mars item kinds relevant to shell; link out
    └── agent-loading.md           # updated from current agent-loading.md
```

**Progressive-disclosure discipline** (hard rule):

- A reader who stops at `design/overview.md` must have a coherent,
  complete-at-that-level picture of the whole MVP. It must not depend on
  any child doc to make sense.
- A reader who stops at any folder's `overview.md` must understand that
  subsystem's purpose, boundaries, and key contracts without reading leaf
  docs.
- Leaf docs add detail. They must not re-explain parent context beyond a
  one-line orientation link back up.
- Every overview links down to its children. Every child links up.
- Every doc has a 1–3 line "what this is / what it's not" header before
  anything else.

Refer to the `tech-docs` skill for writing conventions (structure, clarity,
navigability).

### 2. Apply D21–D28 corrections throughout

This is the substantive content change. Propagate consistently.

**D21 — MVP posture.** agent-shell-mvp replaces meridian-flow. BYO-Claude
local shell, zero hosting. Frame the shell as "top of the funnel," not the
product. Strip all framing that treats the shell or biomedical as the
destination.

**D22 — Moat is mars packaging.** The shell is neutral substrate. Verticals
ship as (agent + skill + MCP + extension) packages through mars. The overview
must lead with this.

**D23 — Marketplace as acquisition funnel.** Three-act framing:
V0 local shell → V0.5 marketplace surface → V1 hosted continuity. "Same
packages, different runtime." Provenance/signing/discoverability are V0.5.

**D24 — Concierge authoring.** First 5–10 packages are hand-written with
customers (Yao Lab first). V0 must exercise every extension point Yao Lab
needs. Note this in strategy and link from extensions/.

**D25 — Generic chat UI + renderer plugins.** Frontend ships ZERO domain
code. 3–5 core renderers only (text/markdown, image, table, simple chart).
PyVista is an external mars package, not a shell feature. Kill every
shell-internal biomedical code reference.

**D26 — Interaction-layer extensions (BIG ONE).** Extensions are composite
(frontend component + MCP server) pairs with **bidirectional** event flow.
Reverse channel is V0 and load-bearing. Frontend → shell backend → paired
MCP via **relay** (not direct). `interactive-tool-protocol.md` (current
content) gets a near-total rewrite into `extensions/interaction-layer.md`
+ `extensions/relay-protocol.md`.

**D27 — CLI plugins deferred but not rejected.** Mars `ItemKind` is an
open/extensible enum. V0 ships 4 kinds: agent, skill, MCP server,
interaction-layer extension. `ItemKind::CliCommand` /
`ItemKind::HarnessAdapter` added later without migration. Do not hardcode
the kind list in places that would require rewriting.

**D28 — Architecture wide, implementation narrow.** GOVERNING PRINCIPLE.
Every seam is a published versioned contract from V0. Every V0 choice must
pass both tests: "does removing this block Yao Lab?" AND "does keeping this
trap us in six months?" Call this out in `strategy/overview.md` and
reference it in every wire-contract section.

### 3. Publish wire contracts at every seam (per D28)

Treat these as first-class published contracts. Each gets a dedicated
"Wire Contract" section in its doc with: `VERSION` field, envelope shape,
example payload, additive-only evolution rule for V0, link to canonical
source-of-truth file (if any).

- **Normalized event schema** (harness ↔ shell backend) →
  `events/normalized-schema.md` (D1 canonical)
- **Content block wire format** (backend ↔ frontend) → `frontend/protocol.md`
- **Interaction-layer relay protocol** (frontend ↔ backend ↔ paired MCP) →
  `extensions/relay-protocol.md` (NEW per D26)
- **Mars package manifest schema** → reference `.meridian/work/mars-mcp-packaging/`,
  DO NOT re-specify. Leave a pointer stub in `packaging/overview.md`.
- **Shell ↔ mars install/sync contract** → reference same work item.

### 4. Handle the prior review findings (p1138)

The prior reviewer (p1138) flagged these issues before the correction pass
spec landed. Resolve each one in the rewrite:

- **H1 — Mid-turn injection rests on reverse-engineered Claude behavior.**
  Keep the V0 tier-1 commitment but explicitly note in
  `harness/mid-turn-steering.md` that a Phase 1.5 verification spike is
  required before the V0 Claude adapter commits to `queue` mode; if
  verification fails, Claude V0 falls back to `mid_turn_injection="none"`.
- **H2 — Codex app-server breaks persistent-kernel tool execution.** This
  is now MOOT under D25: the shell ships no persistent kernel at all
  (meridian ships no domain tools). Biomedical kernel work happens inside a
  mars-shipped MCP server subprocess. Document this correction explicitly
  in `execution/local-model.md` and in `harness/adapters.md` §Codex.
- **M1 — SEND_USER_MESSAGE wire shape contradicts itself.** Reconcile in
  `frontend/protocol.md`; use the `{messageId, content, turnHints}` shape.
- **M2 — Attachment carrier contradicts translator rename-only rule.**
  Pick: normalized UserMessage carries the content-block array, adapters
  do per-harness packaging. Document in `events/normalized-schema.md`.
- **M3 — `--agents` vs `--append-system-prompt` inconsistency.** Fix in
  the new `packaging/agent-loading.md` and `harness/adapters.md`.
- **M4 — Q7 is bigger than current scope treats.** Leave Q7 as an explicit
  open question in `strategy/overview.md`. Do NOT resolve Q7 in this pass.
- **M5 — Two-tab race contradicts itself.** Pick one rule and document in
  `events/flow.md`. Recommendation: single-session / single-tab in V0 per
  existing D9; second tab is read-only observer.
- **L1–L6 — low-severity cleanups.** Fold into the rewrite where they
  naturally land; list anything you couldn't address in your report.

### 5. Kill the biomedical-shipped-in-shell assumption everywhere

The previous docs treat PyVista and the biomedical venv as shell-internal.
That is now wrong. The following content must die or be rewritten:

- `local-execution.md` discussion of `~/.meridian/venvs/biomedical/` and
  pre-installed stacks → the user's project is a **normal** uv-managed
  Python project; the shell does not own any venvs. Rewrite into
  `execution/local-model.md` + `execution/project-layout.md`.
- `harness-abstraction.md` §9.5.1 PyVista-as-shell-internal → delete
  entirely. PyVista is a mars package example, not a shell component.
- `interactive-tool-protocol.md` treating interactive tools as backend
  subprocesses owned by the shell → rewrite as mars-shipped interaction-
  layer extensions per D26, in `extensions/`.
- `frontend-integration.md` domain-specific renderers → rewrite as
  `frontend/content-blocks.md` (core renderers only) + pointer to
  `extensions/` for anything beyond core.
- `overview.md` §5 Dad-specific walkthrough → trim to one neutral example
  ("a package installer mounts a custom 3D mesh viewer"). The Yao Lab
  narrative moves to `strategy/overview.md` as a validation-customer note.

### 6. Must NOT do in this pass

- Do NOT design the mars-mcp-packaging schema — that's a parallel work item.
  Leave pointers.
- Do NOT resolve Q7 (unify meridian-channel spawn/session under
  HarnessAdapter). Leave it as an open question with recommended resolution
  noted.
- Do NOT extract the frontend into its own repo. Design for extraction
  (protocol is the seam), but keep it in-repo.
- Do NOT invent new architecture to cover gaps. If you find an unresolvable
  gap, leave a clearly-marked TODO pointing at the relevant decision and
  flag it in your report.

### 7. File-management rules

- **Replace atomically.** Approved design lives at `design/`. Move the
  current flat files into the new hierarchy by rewriting, not appending.
  Delete the old flat files (`rm $MERIDIAN_WORK_DIR/design/overview.md`,
  etc) after their content is redistributed. Git history preserves them.
- **Commit checkpoints are encouraged** but not required inside this single
  spawn — the orchestrator will commit after review converges.
- Do NOT touch files outside `$MERIDIAN_WORK_DIR/design/`. Requirements,
  decisions, synthesis, findings, reviews stay as-is.

## Your report should cover

1. New `design/` folder tree (one `tree`-style listing).
2. Mapping table: old flat file → new location(s) (merged, split, retired).
3. Places where D21–D28 forced a decision that wasn't previously covered —
   what you decided and why.
4. Any contradictions you found between D21–D28 and earlier D1–D20, with
   your recommended resolution (or flag as unresolved for the user).
5. Anything deferred and why (including Q7 and any new open questions
   surfaced during the rewrite).
6. Prior-review findings disposition: how each of H1, H2, M1–M5, L1–L6 was
   addressed or why it wasn't.
7. Known gaps with TODO markers, keyed to the decision that needs to resolve
   them.

Keep the report under 1500 words. It's a delta summary, not a replay of the
design.
