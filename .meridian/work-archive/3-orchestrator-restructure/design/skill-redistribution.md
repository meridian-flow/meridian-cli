# Skill Redistribution

## Current State (2 orchestrators)

| Orchestrator | Skills |
|---|---|
| dev-orchestrator | __meridian-spawn, __meridian-session-context, __meridian-work-coordination, architecture, planning, review-orchestration, agent-staffing, mermaid |
| impl-orchestrator (currently dev-runner) | __meridian-spawn, __meridian-work-coordination, agent-staffing, review-orchestration, dev-orchestration |

**Problem**: dev-orchestrator loads architecture, planning, agent-staffing — skills for design and execution it no longer does directly. impl-orchestrator loads dev-orchestration which teaches the full lifecycle including design phases it doesn't own.

## Proposed State (3 orchestrators)

| Orchestrator | Skills |
|---|---|
| dev-orchestrator | __meridian-spawn, __meridian-session-context, __meridian-work-coordination, agent-staffing, decision-log, dev-artifacts, context-handoffs |
| design-orchestrator | __meridian-spawn, __meridian-work-coordination, architecture, planning, review-orchestration, agent-staffing, tech-docs, decision-log, dev-artifacts, context-handoffs, mermaid |
| impl-orchestrator | __meridian-spawn, __meridian-work-coordination, agent-staffing, review-orchestration, decision-log, dev-artifacts, context-handoffs |

## Subagent Skill Updates

| Agent | Add | Why |
|---|---|---|
| architect | tech-docs, decision-log, context-handoffs | Writes hierarchical design docs, records design decisions, gets spawned with context |
| planner | tech-docs, decision-log, context-handoffs | Writes phase blueprints, records decomposition decisions, gets spawned with context |
| documenter | decision-log, context-handoffs | Mines conversations for decisions, gets spawned with --from |
| reviewer | decision-log, context-handoffs | Needs prior decision context, gets spawned with -f artifacts |
| investigator | context-handoffs | Gets spawned with --from for backlog sweeps, -f for bug investigation |

## Retired Skill: dev-orchestration

The monolithic lifecycle skill is retired. Its content distributes to:

| Content | Moves to |
|---|---|
| Orchestrator roles | Agent bodies (each orchestrator knows its own role) |
| Phases of work | dev-orchestrator body (decides which phases matter) |
| Scaling ceremony | dev-orchestrator body (makes the routing decision) |
| Design section | design-orchestrator body |
| Planning section | design-orchestrator body |
| Implementation loop | impl-orchestrator body |
| Spawning coders/testers | impl-orchestrator body |
| Documentation phase | impl-orchestrator body |
| Keeping state visible | New `dev-artifacts` skill (shared convention for design/, plan/, decisions.md) |
| Decision log | New `decision-log` skill |
| Cross-workspace coordination | Orchestrator bodies (just uses __meridian-work-coordination commands) |

## New Skills

### decision-log

**Craft**: How to capture decisions so future agents (and humans) can understand what was decided, why, and what alternatives were rejected.

**Teaches**:
- What to record: the reasoning, alternatives considered, constraints discovered, what changed
- When to record: while context is fresh — during design exploration, after review synthesis, when adapting during implementation. Not retroactively.
- How to structure entries: searchable, concrete (file paths, evidence), traceable back to design docs
- Decision types: design decisions (architecture, tradeoffs), execution decisions (pivots, adaptations), review decisions (what to fix, what to defer, overruling reviewers)

**Loaded by**: all 3 orchestrators, architect, planner, documenter, reviewer (7 agents)

**Does NOT teach**: where to put the file (that's agent-body context — orchestrators use `$MERIDIAN_WORK_DIR/decisions.md`, documenter promotes to `$MERIDIAN_FS_DIR`)

### context-handoffs

**Craft**: How to pass the right context when spawning agents — choosing between `-f`, `--from`, and materializing context into files first.

**Teaches**:
- `-f` — pass specific files the agent needs to read. Use when the context is concrete artifacts (design docs, phase specs, source files). Pass only what's relevant to the task — too little and the agent guesses, too much and it drowns.
- `--from` — pass conversation/session history. Use when the agent needs to understand decisions, discussion context, or prior reasoning that isn't materialized in files yet.
- Materializing first — when important context only exists in conversation, write it to a file before spawning so downstream agents don't depend on session history. Materialized context survives compaction and re-spawns.
- Scoping: pass the overview + the specific docs for the task. Tell the agent where to find more if it needs to explore. Don't dump entire directories.
- Cross-phase context: use `--from <prior-spawn-id>` to carry forward what the previous phase learned. The next agent can explore further on its own.

**Loaded by**: all 3 orchestrators, architect, planner, reviewer, documenter, investigator — any agent that spawns or gets spawned with context.

### dev-artifacts

**Craft**: The shared artifact convention between orchestrators — what goes where, how artifacts flow between phases, and what each directory means.

**Teaches**:
- `design/` — hierarchical spec for the target system state. SRP per doc, linked, unbounded depth. Includes existing parts the work interacts with.
- `plan/` — the delta. What changes from current codebase to designed state. Each phase is scoped, ordered, verifiable against design.
- `decisions.md` — execution-time pivots, review triage, overruled reviewers, with reasoning
- `status.md` — impl-orchestrator's ground truth for phase progress
- How artifacts flow: design-orchestrator writes design/ + plan/, impl-orchestrator reads them and writes status.md + decisions.md, dev-orchestrator reads everything to review with user
- Rejected design iterations: replaced atomically (approved artifacts live at design/ and plan/, not versioned alongside rejected drafts)

**Loaded by**: all 3 orchestrators

**Swappable**: A CLI-specific or project-specific workflow can replace this skill with its own artifact conventions without touching agent bodies.

## Skills That Need Rewriting

### tech-docs → rewrite as generic authoring craft

Currently teaches maintaining a compressed mirror in `$MERIDIAN_FS_DIR`. Refocus as a generic technical writing methodology — the craft of writing documents that humans and agents can navigate, understand, and act on.

**Teaches** (the craft):
- SRP per document — one concept per file, split when covering two concerns
- Hierarchical structure — depth matches complexity, no artificial ceiling
- Linked web — relative paths between related docs, traversable
- Writing for agents — self-contained, scannable, enough inline context
- Progressive disclosure — overview orients, detail docs go deep
- When to split vs merge — signals that a doc needs decomposition
- Mining decisions from conversations — finding and extracting important context

**File-specific guidance moves to agent bodies**:
- Where to put files (`$MERIDIAN_FS_DIR` vs `$MERIDIAN_WORK_DIR/design/`)
- What kind of docs to write (design specs vs reference docs vs blueprints)

**Loaded by**: architect, planner, documenter, design-orchestrator

### planning → minor updates

Still relevant for design-orchestrator. Update to emphasize:
- Plan describes the delta (what changes), not the system
- Plan phases reference design/ docs for the "what" and "why"
- Phase blueprints include verification criteria against the design spec

### agent-staffing → refocus

Remove the Orchestrators section (that routing decision is made by dev-orchestrator based on scaling ceremony in its body). Keep:
- Coders, Reviewers, Testers, Refactorer, Documenters, Backlog sections
- Add: design-phase staffing (architects, researchers, explorers)

### architecture → minor updates

No longer needs to teach doc structure (that's tech-docs). Focus purely on design thinking: problem framing, tradeoff analysis, approach evaluation.

### review-orchestration → already updated

The recent edits (Review Agents roster, judgment-based triage) are compatible with the 3-orchestrator model. Both design-orchestrator and impl-orchestrator use this.

### __meridian-orchestration (base) → light update

Mention the 3-orchestrator pattern as an example of how orchestrators can be composed. Don't mandate it.
