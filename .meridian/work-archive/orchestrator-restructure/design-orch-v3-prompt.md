# Revise orchestrator-restructure design package — v3: spec-driven shape

The v2 design package at `$MERIDIAN_WORK_DIR/design/` is a starting point. Subsequent user conversation has reframed the direction around spec-driven development (SDD). Revise v2 in place so it reflects the new direction coherently, then run your normal review fan-out to converge on a revised package.

Read the entire existing v2 draft first — every file in `design/` plus `decisions.md` plus any reviewer reports under `reviews/`. Preserve what is still correct. The v2 package rests on an earlier v1 iteration; the revisions below extend the existing D1-D15 decision log by appending new entries and marking reversals explicitly.

Across every doc below, scenario references migrate to spec-tree references — spec leaves carry what scenarios used to carry (inputs, outputs, failure modes, edge cases, invariants) at higher fidelity inside the hierarchy.

## The reframe

Design phase produces **hard concrete specs + technical architecture**, both hierarchical, both user-facing, both load-bearing. The shape is spec-anchored SDD in the Kiro mold.

### Core principles for v3

1. **Hierarchical two-tree structure.** Design produces two sibling trees under `design/`:
   - `design/spec/` — hierarchical specification tree. System-level invariants at the root, subsystem contracts in subtrees, leaf scenarios with observable behaviors.
   - `design/architecture/` — hierarchical technical design tree. System topology at the root, subsystem internals in subtrees, interfaces/types/dependency directions at leaves.

   The two trees mirror each other. Every architecture node exists to realize one or more spec nodes; every spec leaf is covered by one or more architecture leaves. Cross-links live as explicit references between the trees.

2. **EARS notation for spec leaves.** All acceptance criteria and observable behaviors use EARS (Easy Approach to Requirements Syntax) templates:
   - Ubiquitous: `The <system> shall <response>`
   - State-driven: `While <precondition>, the <system> shall <response>`
   - Event-driven: `When <trigger>, the <system> shall <response>`
   - Optional feature: `Where <feature>, the <system> shall <response>`
   - Complex: `While <precondition>, when <trigger>, the <system> shall <response>`

   EARS makes triggers, preconditions, and expected responses explicit. Every EARS requirement maps directly to a smoke test target. Surface the rule in `design-orchestrator.md` and flag it for the coordinated `dev-artifacts` skill follow-up.

3. **Root-level TOC index in each tree.** `design/spec/overview.md` and `design/architecture/overview.md` each act as an extended table of contents — one-line summaries of every leaf, organized by subtree — so reviewers and planner can navigate the trees without loading everything. Context offloading is a first-class design concern: orchestrators at higher altitudes load the overview; agents doing specific work load relevant leaves on demand.

4. **Refactors as a named artifact.** `design/refactors.md` holds the refactor agenda as a first-class artifact that planner consumes directly as a decomposition input. Each refactor entry names what it does, why the target architecture needs it, what parallelism it unblocks, and what files/modules it touches. Planner sequences cross-cutting refactors first so feature work downstream can parallelize — this is the central parallelism-first mechanism.

5. **Feasibility / gap-finding results as a first-class artifact.** `design/feasibility.md` holds the record of what design-orch actively probed during the design phase — real binary outputs, schema extractions, smoke probes, assumption validations. Each entry names what was checked, what the evidence showed, and what design constraint it produced. Gap-finding is part of design, and its outputs are part of the design package.

6. **Spec-anchored authority.** Specs stay authoritative through maintenance, not only at design time. When impl-orch surfaces runtime evidence that contradicts a spec leaf, design-orch revises the leaf before code changes land. The escape hatch sharpens: "runtime evidence contradicts spec leaf X" → impl-orch bails → design-orch revises the leaf → impl-orch resumes against the revised spec. Redesign brief cites the falsified leaves.

7. **`dev-principles` gate during convergence.** Design-orch loads `dev-principles` as a convergence gate. "Does this design honor project-wide structural principles?" blocks convergence if the answer is no. This is the lightweight equivalent of constitutional gates, reusing machinery the project already has.

8. **Problem-size scaling.** The design-orchestrator body carries explicit guidance on when the full hierarchical spec earns its cost and when lighter-weight design fits. A one-line fix gets a light design; a cross-cutting refactor gets the full hierarchy. The "match process to problem" principle from the existing @dev-orchestrator body carries into v3 intact. Every section of a spec or architecture doc earns its length by guiding an agent or gets trimmed — brevity is a craft concern, not a page-count goal.

9. **Smoke tests against spec leaves.** Verification runs smoke tests that exercise the behavior each EARS requirement describes. Unit tests stay surgical per the project's existing "prefer smoke tests over unit tests" rule from CLAUDE.md. Verification framing is "does the implementation satisfy spec leaves X, Y, Z?"

10. **Reviewers as drift-prevention.** Detailed specs alone carry partial weight against agent misinterpretation; cross-model review fan-out is what actually catches drift at every gate (design convergence, plan review, final implementation loop). Review is load-bearing in v3, with the fan-out split across tree boundaries (spec reviewers, architecture reviewers, alignment reviewers checking cross-links, refactor reviewer on the architecture tree).

## Research anchors

The direction is grounded in current SDD research. Use these as anchors when revising:

- **Fowler's three levels of SDD** (spec-first / spec-anchored / spec-as-source): target spec-anchored. Specs persist through maintenance; code is the artifact, spec is the contract.
- **Kiro shape** (requirements / design / tasks, EARS notation, human-in-the-loop at each gate, verification via smoke tests): closest existing shape to v3.
- **Thoughtworks separation of business and technical specs** validates the two-tree structure. Spec tree is business-level (intent, behavior, invariants, quantified constraints); architecture tree is technical-level (modules, interfaces, refactors, gap-finding).
- **Hierarchical summary / TOC index pattern** from Addy Osmani's agent-spec writeup validates the root-level TOC index approach.
- **Constitutional gates** (spec-kit's pre-implementation enforcement) inform the `dev-principles` convergence gate.

## Per-doc revisions

**`overview.md`** — revise the topology narrative under SDD:
- Add the two-tree structure (`design/spec/` + `design/architecture/`) as the primary design output.
- Add the EARS notation rule and the root-level TOC index pattern.
- Strengthen problem-size-scaling guidance.
- Update the "what design produces" list to include spec tree + architecture tree + refactors.md + feasibility.md.

**`design-orchestrator.md`** — largest revision:
- Reframe the body: design-orch's primary output is the spec tree + architecture tree + refactors + feasibility package, returned to dev-orch for user approval.
- Include a short EARS reference (five patterns with one example each).
- Make gap-finding an active design-phase activity with explicit guidance: probe real systems during design. Run the binary. Read the schema. Validate the assumption. Each probe result lands in `feasibility.md`.
- Make refactor planning part of the design output: `refactors.md` is produced during design.
- Load `dev-principles` as a convergence gate.
- Include problem-size scaling guidance — when the full hierarchical spec is warranted, when lighter design fits.
- Sharpen the review fan-out: spec reviewers check concreteness/testability/coverage/ambiguity on the spec tree; architecture reviewers check structural soundness/refactor sufficiency/parallelism-readiness on the architecture tree; alignment reviewers check cross-links between the two trees. Structural/refactor reviewer stays, focused on architecture tree.

**`impl-orchestrator.md`** — medium revision:
- Verification framing shifts to "does this phase satisfy spec leaves X, Y, Z?"
- Escape hatch sharpens: bail-out criterion is "runtime evidence contradicts spec leaf X." Redesign brief cites the falsified leaves and the architecture nodes that must change to realize them differently.
- Spec-drift rule: when a phase discovers the spec is wrong during execution, the spec gets revised before code changes land.
- v2's planner-rehoming (impl-orch spawns planner) carries forward unchanged.
- Skills loaded list review — feasibility-questions stays loaded, planning skill stays off impl-orch.

**`planner.md`** — medium revision:
- Planner takes `design/architecture/` + `design/refactors.md` + spec leaves and produces phases. Each phase declares which spec leaves it satisfies. Parallelism comes from disjoint subtrees in the architecture plus disjoint leaf coverage in the spec.
- Pre-planning notes shrink: design-orch has already done gap-finding and landed it in `design/feasibility.md`. Planner reads it as input.
- Planner's role narrows: sequence the refactor agenda design identified, sequence the architecture subtrees for parallel execution, map phases to spec leaves. When runtime evidence shows a refactor is needed that design missed, that triggers a planner→design escalation (the structural-blocking bail-out).

**`dev-orchestrator.md`** — small revision:
- Approval walk: dev-orch walks user through root-level spec overview + root-level architecture overview + refactor agenda by default. User drills into any subtree on demand.
- Requirements gathering stays lightweight — conversational intent capture in `requirements.md`. Specs crystallize in design-orch from requirements.

**`feasibility-questions.md`** — small revision:
- The four questions carry forward (feasible / parallel / break down / foundational). Framing shifts: feasibility-questions answers land in `design/feasibility.md` at design time and in `plan/pre-planning-notes.md` at planning time.
- Sharpen "does something need foundational work first?" to lean on design-orch having already answered it via `refactors.md`.

**`redesign-brief.md`** — small revision:
- "new spec leaves in the affected subtree" replaces the scenarios-related section in the design change scope.
- Update the cycle 1 example accordingly.
- Falsification case section references spec leaves explicitly — "assumption (spec/permission-pipeline/codex.md) is falsified by..."

**`terrain-contract.md`** — small revision:
- Terrain section produces refactor-agenda candidates (landed in `design/refactors.md`) and feasibility-probe results (landed in `design/feasibility.md`) as first-class outputs.
- The "structural delta" concept from v2 maps onto the refactors artifact.
- Terrain section is one gap-finding surface among several; gap-finding is distributed across design-orch's body.

**`preservation-hint.md`** — minimal revision, aligned with the scenario-to-spec-leaf migration.

**`decisions.md`** — revise and extend:
- Preserve existing D1-D15 entries with their original alternatives and reasoning where still valid.
- Mark reversals explicitly ("D9 reversed: scenarios subsumed by spec tree — see D16").
- Append:
  - D16: SDD shape adoption (spec-anchored, Kiro-shaped). Rationale from Fowler's three levels + Thoughtworks separation.
  - D17: EARS notation rule for spec leaves. Rationale from testability + AI-decomposability.
  - D18: Hierarchical two-tree structure with root-level TOC index. Rationale from context offloading.
  - D19: Refactors as named artifact consumed by planner. Rationale from parallelism-first decomposition.
  - D20: Feasibility / gap-finding as first-class design output. Rationale from the prior session's broken-structure lesson.
  - D21: Smoke tests against spec leaves; verification by behavior, driven by EARS. Rationale from project CLAUDE.md + Kiro precedent.
  - D22: Spec leaves subsume scenarios. Explicit reversal of any v2 scenarios decision.
  - D23: Problem-size scaling — light path for small changes. Rationale from Fowler's observation that uniform process hurts feedback.

## New docs

The revision lands inside the existing doc set. If during revision a concept genuinely doesn't fit any existing doc, give it its own doc. Default is revise-in-place.

## Coordinated skill edit (follow-up)

The `dev-artifacts` skill in `meridian-dev-workflow` needs a coordinated edit to match the new artifact convention. After v3 lands, the skill defines:

- `requirements.md` — dev-orch's conversational intent capture (unchanged)
- `design/spec/` — hierarchical spec tree, root TOC, EARS-format leaves
- `design/architecture/` — hierarchical architecture tree, root TOC, technical design leaves
- `design/refactors.md` — refactor agenda, first-class planner input
- `design/feasibility.md` — gap-finding results
- `decisions.md` at work root (unchanged placement)
- `plan/` (unchanged)
- `plan/status.md` (unchanged)

Flag this as a required follow-up in the revised package. The coordinated edit happens after user approval of v3.

## Convergence

Run your normal design-orchestrator loop. The revised package lives at `$MERIDIAN_WORK_DIR/design/` — replace v2 atomically by updating files in place. Git history preserves prior iterations.

Fan out reviewers across diverse strong models (run `meridian models list` for current options). Review focus areas:

1. **Design alignment** — does this package match the reframe direction? Does it complete the migration from scenarios to spec leaves? Does it preserve what still works from v2?
2. **SDD shape review** — is this genuinely spec-anchored per Fowler's levels? Are the spec leaves hard concrete (EARS) or hand-wavy? Is the hierarchical structure clean or tangled?
3. **Structure / modularity / refactor review** — does the architecture tree enable parallelism-first decomposition downstream? Is the refactor agenda complete? Is there structural debt the planner would trip on?
4. **Decomposition sanity** — does the architecture tree decompose into parallel subtrees, or does hidden coupling force sequential phases?

Cross-model diversity matters — the reframe is a real direction change, and each model has different blind spots that cross-coverage catches.

## Scope

- Output is revised markdown artifacts under `design/`, updated `decisions.md`, and reviewer reports under `reviews/`.
- v2's planner-rehoming decision (impl-orch spawns planner) carries forward to v3.
- The escape hatch criteria sharpen to cite falsified spec leaves; surrounding machinery carries over from v2.
- Target spec-anchored SDD per Fowler's three levels.
- Use `dev-principles` during convergence as the convergence gate.
- Revise the existing doc set in place; default to revise rather than fragment.

## Deliverables

- Revised `design/` package reflecting the SDD reframe, with spec tree + architecture tree + refactors.md + feasibility.md + updated versions of existing docs.
- Updated `decisions.md` with D16-D23 added and any reversals marked explicitly.
- Review reports from the fan-out under `reviews/`.
- A terminal report summarizing:
  - What changed between v2 and v3 (doc-by-doc summary).
  - Which decisions were added and which were reversed.
  - Reviewer findings flagged for the user's attention before approval.
  - Follow-up work the user should know about (coordinated skill edit, any open questions).

Return the terminal report on completion. Your caller (dev-orchestrator) walks the user through the revised package.
