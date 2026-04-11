# redesign-brief.md: Artifact Format

This doc specifies the format of `redesign-brief.md`, the artifact impl-orchestrator writes when its escape hatch fires. The brief is consumed by dev-orchestrator to scope a redesign session and by design-orchestrator to understand what must change. It is also the mechanism the system uses to audit autonomous redesign cycles after the fact. Under v3, the brief cites falsified spec leaves and named subtrees of the two-tree design package rather than flat design doc sections.

Read [overview.md](overview.md) and [impl-orchestrator.md](impl-orchestrator.md) for the surrounding behavior.

## Location and lifecycle

The brief lives at `$MERIDIAN_WORK_DIR/redesign-brief.md`. Impl-orch writes it before emitting its terminal report. Dev-orch reads it directly when the report cites it. If a subsequent redesign cycle triggers another bail-out, impl-orch appends a new brief entry below the first — the file is append-only across cycles so the history of the work item is preserved in one place.

The file name is stable across cycles so that consumers do not have to guess which brief is current. The latest entry is always at the bottom.

## Structure

Each brief entry is a self-contained section describing one bail-out. Entries start with a cycle heading and carry six required sections plus one optional planning-time section: status, evidence, falsification case, design change scope, preservation, constraints that still hold, and (for planning-time bail-outs only) parallelism-blocking structural issues. The escape hatch fires both at execution time (test/smoke evidence falsifies a design assumption mid-execution) and at planning time (planner cannot decompose the design or planner returns `Cause: structural coupling preserved by design`); the brief format covers both arms.

### Cycle heading

`## Cycle <n>: <one-line summary>`

The cycle number is the nth bail-out on this work item. The one-line summary is a terse human-readable description — "Codex approval semantic cannot be expressed by app-server", "Smoke test reveals OpenCode session API mismatch", etc.

### Status

What was completed, what was in-flight at the moment of bail-out, and what had not started. This gives design-orch and dev-orch a snapshot of the work item's state without having to read the git log or status.md separately.

The status section names each phase and its terminal state for this cycle — committed (with SHA), uncommitted work abandoned, not-started. Committed phases form the starting point for preservation decisions. Uncommitted work is implicitly abandoned because impl-orch stopped spawning coders; the brief does not need to list every half-finished tester run.

### Evidence

What specifically happened that triggered the bail-out. Not a feeling or a concern — concrete evidence that can be verified by reading test output, smoke reports, or session logs.

Good evidence looks like: test names and what they checked, smoke test commands and their outputs, session IDs of agents that reported the findings, specific line numbers in logs where the contradiction is visible, quoted excerpts from real-binary probes that contradict design assumptions.

Weak evidence looks like: "testers kept finding issues", "the design seems wrong", "performance is bad". A brief with only weak evidence should be rejected by dev-orch and pushed back to impl-orch for stronger justification or patched forward in the normal fix loop.

### Falsification case

The heart of the brief. Impl-orch states explicitly:

1. **The design assumption** that is being falsified. Under v3 this is cited as a specific **spec leaf ID** (e.g. `design/spec/permission-pipeline/codex.md §S02.3.e1`) or a specific **architecture subtree assumption** (e.g. `design/architecture/permission-pipeline/codex.md §"Target state — streaming channel"`). Quote or paraphrase the statement so design-orch does not have to re-read it to understand what is being falsified.
2. **What would have to be true** for the spec leaf or architecture assumption to hold.
3. **What the evidence shows** instead — the specific mismatch between the assumption and reality.
4. **Why a local fix is insufficient.** Why patching in the current phase would leave the next phase or the overall integration broken. If the falsification is "the EARS response clause in leaf S02.3.e1 is unachievable given observed binary behavior," say so explicitly — the spec leaf itself is what has to change, not just the code.

This section is the counterweight to the cheap-to-invoke escape hatch. Impl-orch has to make the case that this is not a fixable bug, not a scoping error, not a tester disagreement — that it is runtime evidence against a spec leaf or architecture assumption and that continuing would compound the error. A brief that cannot make that case should not bail.

Dev-orch reviewing the brief evaluates the falsification case. A case that fails evaluation is pushed back for patch-forward or for a stronger case; it does not advance the redesign cycle counter.

### Design change scope

What has to change in the design package to resolve the falsification. Scoped as narrowly as possible — impl-orch should not propose a full redesign when a subtree-level revision would suffice.

Content:
- **Spec tree revisions.** Which spec leaves must be revised or replaced, named by leaf ID (e.g. "`design/spec/permission-pipeline/codex.md §S02.3.e1` — revise the EARS response clause"). Which spec subtrees stay untouched.
- **Architecture tree revisions.** Which architecture docs must be revised, named by path (e.g. "`design/architecture/permission-pipeline/codex.md` — target-state streaming channel section"). Which architecture subtrees stay untouched.
- **Refactors agenda deltas.** Whether `design/refactors.md` needs new entries (the falsification may have revealed a coupling that was not refactored), existing entries need to be reprioritized, or no changes are needed.
- **Feasibility deltas.** Whether `design/feasibility.md` needs to record new probe results or revise existing entries in light of the falsification evidence.
- **New spec leaves.** Any previously-unknown edge cases the falsification surfaces — enumerated with proposed leaf IDs, target subtrees, and a one-line EARS sketch each. Design-orch may renumber or relocate them during the revision but the set is fixed by the brief.
- **What the revision should address.** Not the answer — the question design-orch needs to answer at each revision point.

The design change scope is a brief for design-orch, not a prescription. Design-orch is still the one that decides how to revise; impl-orch is identifying what needs to be revised and why.

### Preservation

Which committed phases can stay and which must be rebuilt. This is where default-preserve is made explicit: every committed phase is listed, and each one is marked as preserved, partially-invalidated, or fully-invalidated.

- **Preserved** phases are safe. The next impl cycle skips them entirely and starts from the first invalidated phase forward. Their commits stay in place.
- **Partially-invalidated** phases had work that is still valid but also had work that depends on the falsified assumption. The brief names exactly what has to be reworked — specific files, specific interfaces, specific behaviors. The partial invalidation shows design-orch and the next impl cycle which parts of the existing commit can be salvaged.
- **Fully-invalidated** phases are rebuilt from scratch in the next cycle. Their commits are not reverted — git history is preserved — but the next impl-orch run treats them as not-yet-done.

The default is preserved. Anything not explicitly marked invalidated stays preserved. Impl-orch has to justify each invalidation with a pointer back to the falsification case — why this phase's work depends on the assumption that is being changed.

### Constraints that still hold

Requirements from the original user intent that must not drift during the redesign. This is a guardrail against scope creep: a redesign session is invited to change the design docs, not the user's original goals. The constraints section names what the redesign cannot negotiate.

Examples: "The user explicitly rejected approach X in the original design session." "Performance must stay within Y of baseline." "The external API must remain Z-compatible." "No backwards-compatibility requirement — the user said we can break wire format."

Design-orch reading the brief treats this section as a hard boundary. A revised design that drifts outside the constraints is a scope creep problem and dev-orch will push back on it.

### Parallelism-blocking structural issues *(planning-time bail-outs only)*

Required for `structural-blocking` and `planning-blocked` briefs. Omitted for execution-time briefs (where the falsification case section already covers the relevant evidence).

This section is the planning-time analog of the falsification case section. Where falsification case describes runtime evidence that contradicts a design assumption mid-execution, this section describes the structural reason the planner could not produce a parallelism-rich plan from the design as written. Impl-orch states explicitly:

1. **Bail-out trigger.** Which planning-time signal fired:
   - `structural-blocking` — planner returned `Parallelism Posture: sequential` (or `limited`) with `Cause: structural coupling preserved by design`. Cite the planner's reasoning paragraph from `plan/overview.md`.
   - `planning-blocked` — planner cycle cap (K=3) was exhausted without convergence. Cite each spawn's failure mode and the gap reasoning impl-orch provided on each re-spawn.
2. **The structural coupling.** Named with specific modules, interfaces, or shared state. Not "the auth surface is tangled" — "module `auth/handler.py` mixes parsing and persistence; every feature phase that touches auth has to read both, so no two feature phases on the auth surface can run in parallel."
3. **Why the planner could not route around it.** What decomposition moves the planner attempted (or would have attempted) and why each one was blocked by the coupling. The point is to demonstrate that this is not "the planner gave up" — it is "the planner tried and the structure resists every approach."
4. **What the design would have to do differently.** A pointer to the structural change that would unlock parallelism. Not a full redesign — the smallest structural change that would let the planner produce a parallelism-rich plan. This is the question for design-orch, not the answer.
5. **Pre-planning notes referenced.** Cite the specific module-scoped constraints from `plan/pre-planning-notes.md` that ruled out alternative decompositions, so design-orch can read them without re-running the probes.

This section is the counterweight to planning-time bail-outs the same way falsification case is for execution-time bail-outs. A planning-time bail-out without a strong "the structure resists every approach" case is rejected by dev-orch and pushed back to impl-orch for either a stronger case or a re-spawn with better pre-planning notes.

## What the brief is not

- Not a bug report. Bugs go in fix loops, not briefs.
- Not a plan for the redesign session. Design-orch still runs its own convergence loop with architects and reviewers; the brief provides input, not structure.
- Not a substitute for decisions.md. Decisions during the impl cycle still land in decisions.md. The brief is a handoff artifact, not a running log.
- Not a way to escape unfinished work. Impl-orch cannot bail because tests are hard or coders are stuck. The falsification requirement makes that explicit.

## Example shape

```markdown
# Redesign Brief: <work item name>

## Cycle 1: Codex approval semantic cannot be expressed by app-server

### Status
- Phase 1: committed (SHA abc123)
- Phase 2: committed (SHA def456)
- Phase 3: in-flight, uncommitted — abandoned
- Phases 4–8: not started

### Evidence
Smoke test `codex-approval-confirm.md` against `codex app-server --help` output shows...
Session p1234 (@smoke-tester) report excerpt: "..."
Log file `.meridian/spawns/p1234/stderr.log` lines 48–67 capture the real binary rejecting...

### Falsification case
**Assumption (spec leaf `design/spec/permission-pipeline/codex.md §S02.3.e1`):** "When the user selects confirm-mode for a Codex session, the streaming projection SHALL emit approval requests on a channel distinct from the YOLO channel."

**Architecture assumption (`design/architecture/permission-pipeline/codex.md §Target state — streaming channel`):** Codex app-server exposes a distinct wire channel for confirm-mode approvals separate from the YOLO channel.

**What would have to be true:** The `codex app-server` binary would have to accept an approval-mode argument or expose a runtime approval callback API.

**What the evidence shows:** `codex app-server --help` has no approval-mode flag and the runtime JSON-RPC protocol does not include an approval request method. Our streaming connection can only send the YOLO sentinel; the spec leaf's response clause describes behavior that does not exist in the real binary.

**Why local fix is insufficient:** Phase 4's projection assumes two distinct approval wire values. Every subsequent phase that reads from the projection (6, 7, 8) claims spec leaves that depend on that shape (`S02.4.e1`, `S02.5.e1`, `S02.6.e1`). Patching Phase 4 to collapse the two values silently would recreate the H1 sandbox-downgrade bug the original design set out to prevent, and would leave three spec leaves claiming behavior that the code does not implement.

### Design change scope
- **Spec tree revisions:** `design/spec/permission-pipeline/codex.md §S02.3.e1` — revise the EARS response clause to describe fail-closed behavior on single-channel wires. `§S02.4.e1`, `§S02.5.e1`, `§S02.6.e1` may need minor cross-link updates but their core EARS statements likely stay.
- **Architecture tree revisions:** `design/architecture/permission-pipeline/codex.md §Target state — streaming channel` — how confirm-mode maps to the real single-channel app-server surface.
- **Refactors agenda deltas:** no new refactors required (this is a spec/architecture reshape, not a structural coupling).
- **Feasibility deltas:** add a new entry to `design/feasibility.md` recording the `codex app-server --help` probe result and the wire-protocol observation, so future redesign cycles do not re-probe.
- **New spec leaves:** one new leaf `design/spec/permission-pipeline/codex.md §S02.3.e2` covering the confirm-mode-on-single-channel case with the intended fail-closed behavior.
- **Stay:** `design/spec/overview.md`, `design/architecture/overview.md`, `design/spec/typed-harness/**`, `design/architecture/runner-shared-core/**`.

### Preservation
- Phase 1: preserved — typed leaves are unaffected
- Phase 2: preserved — permission pipeline is affected but the fix targets Codex-specific semantics, not the shared pipeline
- Phase 3: fully-invalidated (if committed) — not applicable this cycle
- Phase 4: fully-invalidated — the projection is the falsified component

### Constraints that still hold
- Meridian must never silently downgrade a confirm-mode request to YOLO. The original design's fail-closed requirement must be preserved.
- User explicitly rejected an approach in cycle 0 that routed all approvals through a user-space proxy. That approach remains rejected.
- Phase 1's type contracts must not be broken.
```

## Why this format

The brief format is shaped by its consumers. Dev-orch needs the status and the falsification case to decide whether to route a redesign. Design-orch needs the design change scope and the constraints to run the revision session without re-learning everything from scratch. Impl-orch's next cycle needs the preservation section to know where to start. Separating those concerns into discrete sections lets each consumer read only what it needs.

The falsification section is the part that distinguishes this artifact from a bug report. Every bail-out has to make the case that a local fix is insufficient, and the review of that case is what keeps the escape hatch from being abused.

## Open design questions

None at this draft. Format details that fall out of implementation land in [../decisions.md](../decisions.md) as they are resolved.
