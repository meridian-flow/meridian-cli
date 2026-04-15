# Orchestrator-restructure v3: two-tree instantiation

The orchestrator-restructure design package at `$MERIDIAN_WORK_DIR/design/` has converged on v3 SDD shape (decisions D16–D26). Three parallel pre-spawns produced the step-A inputs: `design/feasibility.md`, `design/refactors.md`, and a dev-principles correction (D24 revision) across existing body docs. Those artifacts are already on disk when you start.

The remaining work is the structural pass: migrate the 9 existing flat design docs into the two-tree layout (`design/spec/` + `design/architecture/`) with leaf IDs, root TOC indexes, cross-links, and wired-in references to the pre-produced artifacts.

This is the dogfooding exercise — the v3 package describes a two-tree convention for all future work items, and applying it to its own project tests whether the convention holds against reality. If something doesn't fit, flag it as a convention refinement in `decisions.md` (e.g., "D27: EARS applies naturally to runtime behaviors; orchestration semantics use supplementary prose within architecture leaves") rather than force-fit.

## Starting state

Read these before beginning:
- `$MERIDIAN_WORK_DIR/decisions.md` — especially D16–D26, and the revised D24 from the parallel correction spawn.
- `$MERIDIAN_WORK_DIR/design/feasibility.md` — evidence base from the parallel writer spawn. Read it fully. The structural constraints and probe records ground the choices you make.
- `$MERIDIAN_WORK_DIR/design/refactors.md` — refactor agenda from the parallel writer spawn. Read it fully. The entries name what moves where in this pass.
- `$MERIDIAN_WORK_DIR/design/*.md` — the existing 9 flat design docs that hold the content being migrated.
- `$MERIDIAN_WORK_DIR/reviews/` — v2 reviewer reports for context.

## Target state

After this pass, `$MERIDIAN_WORK_DIR/design/` holds:

```
design/
  spec/
    overview.md              # TOC index: one-line summaries of every spec leaf
    <subsystem>/
      overview.md            # subsystem-level contracts
      <component>.md         # leaf EARS statements with S<N>.<section>.<ID> tags
  architecture/
    overview.md              # TOC index: one-line summaries of every architecture leaf
    <subsystem>/
      overview.md            # subsystem target-state
      <component>.md         # interfaces, types, dependency directions with A<N>.<section>.<ID> tags
  refactors.md               # already in place from pre-spawn
  feasibility.md             # already in place from pre-spawn
  terrain-contract.md        # update cross-links to match the new layout
  redesign-brief.md          # update cross-links to match the new layout
  preservation-hint.md       # update cross-links to match the new layout
  feasibility-questions.md   # update cross-links to match the new layout
```

The 9 flat docs are absorbed into the tree. Some become leaves (design-orchestrator.md → subtree in architecture/), some become artifacts (terrain-contract.md stays as a shared contract). Use judgment on where each piece of content fits best given the two-tree separation (business spec vs technical design).

## Content migration shape

The existing doc set splits naturally along the spec/architecture boundary:

**Spec tree candidates** — behavior contracts for orchestrator interactions:
- When dev-orchestrator receives user input, the system shall gather requirements in `requirements.md`
- When design-orchestrator converges, the system shall produce `design/spec/`, `design/architecture/`, `refactors.md`, and `feasibility.md`
- When impl-orchestrator starts a phase, the system shall verify spec leaves X, Y, Z
- When a phase's runtime evidence contradicts a spec leaf, the system shall emit a redesign brief
- Structural contracts (what each artifact must contain) — e.g. redesign-brief.md and preservation-hint.md become spec leaves that name the artifact's required fields

**Architecture tree candidates** — technical design for how the system realizes the specs:
- Agent topology (which orchestrators exist, how they call each other)
- Skill loading conventions (`dev-principles` universal, `feasibility-questions` shared)
- Artifact flow (design package → plan → execution → redesign cycle)
- Cross-cutting patterns (K_fail/K_probe cycle caps, preserved-phase re-verification, terminated-spawn plan review contract)

**Shared contracts staying flat:**
- `terrain-contract.md` — already a shared contract, stays at `design/terrain-contract.md`
- `redesign-brief.md`, `preservation-hint.md` — artifact format specs, stay flat (they could become spec leaves but they're format contracts, not behavior contracts; flat keeps them reusable as references)
- `feasibility-questions.md` — shared skill content, stays flat

Use judgment on edge cases. If a doc doesn't fit cleanly into either tree, flag it in the terminal report with your reasoning and pick the closest fit.

## Leaf ID namespace

Per D25, leaf IDs follow `S<subsystem>.<section>.<letter><number>` (spec) and `A<subsystem>.<section>.<letter><number>` (architecture). The letter encodes EARS pattern: `u`=ubiquitous, `s`=state-driven, `e`=event-driven, `o`=optional, `c`=complex. Architecture leaves use the same letter convention where behavior is involved, or drop the letter for pure structural leaves.

Reserved `S00.*` and `A00.*` namespaces (per p1535's convergence changes to overview.md) hold root-level invariants that apply across subsystems. Use them for system-wide contracts that don't belong to any single subtree.

## EARS application

Apply EARS per D17 and D25 — five patterns, per-pattern mechanical parsing rules, explicit escape valve for leaves that can't mechanically parse. For orchestrator behavior, the common patterns will be event-driven (`When <trigger>, the <system> shall <response>`) and complex (`While <state>, when <trigger>, the <system> shall <response>`). Ubiquitous patterns cover invariants that always hold (e.g., "The redesign brief shall contain status, evidence, falsification case, design change scope, preservation, and constraints sections.").

If a behavior genuinely doesn't fit any EARS pattern, don't force it — use the escape valve from D25. Flag the leaf with a note explaining why EARS doesn't capture it naturally, and surface the pattern(s) during the terminal report so the convention can be refined if needed.

## What stays consistent with v3 as-landed

- v2's planner-rehoming (impl-orch spawns planner) carries forward.
- The K_fail/K_probe cycle caps stay as landed.
- The escape hatch criteria (falsified spec leaves) stay as landed.
- D24 (post-correction — dev-principles universal) is authoritative; update any body language that still reflects the pre-correction "gate" framing.
- The refactor agenda in refactors.md is authoritative; treat its entries as work to reference, not work to re-decide.
- The feasibility evidence in feasibility.md is authoritative; treat its constraints as inputs to the tree design.

## Reviewer fan-out

Run a scoped reviewer fan-out after the tree is in place. Lighter than the p1535 pass since the main structural concerns are already resolved. Target:

1. **Two-tree fit review** — does the structure honestly fit the content, or are leaves forced into EARS when the behavior doesn't suit it? Does the spec/architecture split hold clean, or do leaves cross the boundary?
2. **Cross-link integrity review** — do spec leaves link to architecture leaves that actually exist? Does refactors.md reference real architecture leaves? Does feasibility.md ground real spec leaves?
3. **Alignment review** — does the restructured package read consistently with the dev-principles correction from the parallel spawn? Is the "gate" framing fully removed?

Pick diverse strong models per `meridian models list` for cross-coverage.

## Decision log

Append to `decisions.md`:

- **D27** (if applicable): any convention refinement discovered during the dogfooding pass. For example: "EARS applies naturally to runtime behaviors; orchestration semantics lean on supplementary prose within architecture leaves." Only add this if the restructure actually surfaced a convention gap.
- Mark D24 as revised by the parallel correction spawn with a pointer to that spawn's report for traceability.

## Convergence

Run your normal design-orchestrator loop. Revise in place — replace flat files with tree structure atomically, let git history preserve the v2 and pre-tree v3 shapes.

## Return

Terminal report summarizing:
- The final tree structure (directory listing with leaf counts per subtree)
- Which flat docs became which tree content, or stayed flat, or got absorbed into multiple leaves
- Any EARS escape-valve invocations (leaves where the pattern didn't fit and prose was used) with reasoning
- Any convention refinements recorded as new decisions
- Reviewer findings flagged for user attention
- Cross-link integrity check: does the tree cross-link cleanly with refactors.md and feasibility.md?
- Follow-up work (coordinated skill edit in `meridian-dev-workflow`, agent profile updates for dev-principles loading, etc.)
