# A04.4: Design phase

## Summary

Design-orch is the sole author of the design package. It reads `requirements.md`, authors `design/spec/` first (spec-first ordering), derives `design/architecture/` from the committed spec, produces `design/refactors.md` and `design/feasibility.md` alongside the architecture tree, runs a convergence fan-out across diverse @reviewers with design-alignment + structural + refactor-reviewer lanes, and terminates with a design-ready terminal report. Design-orch runs once per design cycle — first cycle on new work items, every redesign cycle thereafter when dev-orch routes a design-problem.

## Realizes

- `../../spec/requirements-and-scoping/user-intent-capture.md` — S01.1.u1 (`requirements.md` as the intent artifact), S01.1.e1 (conversational capture on new work-item entry), S01.1.s1 (altitude discipline — non-system-behavior kept out of requirements), S01.1.s2 (no in-flight user-intent rewrites mid-cycle). These are dev-orch upstream behaviors that design-orch consumes when reading `requirements.md` as its sole intent input; the design-phase leaf realizes them because it is the earliest arch leaf that depends on their output.
- `../../spec/requirements-and-scoping/problem-size-scaling.md` — S01.2.e1 (selection happens at spawn boundary — dev-orch picks tier before spawning design-orch), S01.2.s1 (trivial path skips design entirely, so design-orch is never spawned), S01.2.s2 (small path produces a degenerate root-only tree), S01.2.s3 (medium path produces one level of subtrees), S01.2.s4 (large path allows multi-level subtrees), S01.2.s5 (large path mandatory on scope triggers), S01.2.w1 (demotion allowed when feasible, promotion is free mid-run via termination signal).
- `../../spec/design-production/spec-tree.md` — S02.1.u1 (spec tree is the authoritative behavior contract), S02.1.u2 (every leaf carries the canonical section set), S02.1.e1 (spec-first ordering with pause-architecture exception), S02.1.s1 (overview is a strict TOC, not prose), S02.1.s2 (root-level invariants live in reserved-namespace leaves), S02.1.s3 (hand-wavy acceptance is a convergence blocker), S02.1.w1 (verification notes are optional and must not be load-bearing), S02.1.c1 (problem-size scaling degenerates the tree to root-only for small work items).
- `../../spec/design-production/architecture-tree.md` — S02.2.u1 (every architecture leaf carries the canonical section set), S02.2.u2 (architecture is observational, not prescriptive), S02.2.e1 (architecture derives from spec — every arch leaf realizes at least one spec leaf), S02.2.e2 (bi-directional cross-link coverage), S02.2.s1 (root topology lives in reserved-namespace leaves, not prose), S02.2.c1 (current-state citation by file path and symbol), S02.2.w1 (open-questions escalation surface for unresolved architecture decisions).
- `../../spec/design-production/refactors-and-feasibility.md` — S02.3.u1 (two first-class sibling artifacts, always produced), S02.3.c1 (refactors and foundational-prep are design-orch-exclusive authorship), S02.3.s1 (gap-finding during design, not deferred), S02.3.w1 (parallel-cluster hypothesis is conditional above the leaf-count threshold).
- `../../spec/design-production/convergence.md` — S02.4.u1 (convergence is multi-lens), S02.4.e1 (reviewer fan-out includes spec, architecture, alignment, structural, and feasibility lanes), S02.4.e2 (structural reviewer is required and blocks PASS), S02.4.s1 (convergence exit requires addressed findings, not clean first pass), S02.4.s2 (spec reviewer enforces EARS shape mechanically), S02.4.s3 (non-requirement flags must be audited, not trusted blindly), S02.4.s4 (structural reviewer sketches decomposition before PASS), S02.4.c1 (spec-first ordering is a convergence criterion — architecture-first spec trees fail), S02.4.w1 (`dev-principles` as shared behavioral lens during convergence, not a binary gate).

## Current state

- v2 design-orch is already the sole author of the design package, but the package is flat (nine sibling docs) rather than two-tree. Spec-first ordering is not enforced because there is no spec tree — behavioral requirements are mixed into overview prose.
- v2 refactors agenda lives inside `design/overview.md` Terrain section, not as a sibling artifact. Design-orch cannot attach refactors.md to reviewer spawns via `-f` because the file does not exist.
- v2 convergence is driven by a @reviewer fan-out, but the structural-reviewer requirement is implicit rather than a mandatory lane, and dev-principles is partially framed as a convergence gate rather than as shared context.

## Target state

### Design-orch spawn lifecycle

1. **Dev-orch spawns design-orch.** First cycle: fresh spawn with `requirements.md` and no prior design. Redesign cycle: spawn with `requirements.md`, prior design package, the redesign brief, and `plan/preservation-hint.md` (if present) attached via `-f`.
2. **Design-orch reads inputs.** Always reads `requirements.md` first (S01.1.u1 — the sole intent capture). On redesign cycles, reads the brief to identify which spec leaves need revision and the preservation hint to understand which claims must stay stable.
3. **Design-orch authors the spec tree (first).** Spec-first ordering per S02.1.e1 is load-bearing: `design/spec/` is authored before `design/architecture/`, directly from `requirements.md`. Every behavioral requirement becomes an EARS statement with a stable ID. Root-scope invariants land in `design/spec/root-invariants.md` under the reserved `S00.*` namespace (S02.1.c1).
4. **Design-orch authors the architecture tree (second).** Every architecture leaf derives from at least one spec leaf (S02.2.e1). Root-scope structural observations land in `design/architecture/root-topology.md` under the reserved `A00.*` namespace (S02.2.s1). Every architecture leaf's `Realizes` field names the spec leaves it realizes; every spec leaf's `Realized by` cross-link (implicit via architecture cross-link) is populated by at least one architecture leaf (S02.2.e2 bi-directional coverage).
5. **Design-orch authors `design/refactors.md` and `design/feasibility.md` alongside the architecture tree.** Refactors entries follow the nine-field shape (A02.1); feasibility entries follow the per-section shape (Probe records, Fix-or-preserve verdicts, Assumption validations, Open questions, optional Foundational prep, optional Parallel-cluster hypothesis).
6. **Design-orch runs probes during the cycle, not after.** Gap-finding lands in `design/feasibility.md §Probe records` during design (S02.3.s1). Design-orch spawns @internet-researchers for external context, @architects for structural exploration, and @coder prototypes for feasibility probes — each probe lands as a feasibility entry before design termination.
7. **Design-orch runs the alignment-and-structural reviewer fan-out.** Multiple @reviewers across diverse model families, each with a specific focus area. Design-alignment reviewer required; structural reviewer required; refactor-reviewer required. `dev-principles` is loaded as shared context (not a gate) per A05.
8. **Design-orch iterates on review findings until convergence.** Every spec leaf is named in at least one architecture leaf's `Realizes` list (S02.2.e2 coverage check). Every refactor entry has an Architecture anchor resolving to a specific leaf. Every feasibility known-unknown is tagged `impl-orch must resolve during pre-planning`.
9. **Design-orch terminates with design-ready terminal report.** Report names the new or revised spec leaves, the new or revised architecture leaves, the refactor agenda, the feasibility evidence, and any unresolved questions that need user input.

### Spec-first ordering (load-bearing)

The spec tree commits first because:

- **It forces intent to be written down before structure is designed.** If an architect can describe structural shapes without first pinning down behavior, the shapes end up solving the wrong problem.
- **It gives the architecture tree a traceability spine.** Every architecture leaf must realize at least one spec leaf; that rule cannot be enforced until the spec leaves exist.
- **It prevents structure-first drift.** A design that starts with "let's have three components" tends to shape requirements to fit the components, not vice versa. Spec-first ordering inverts the dependency.

The pause-architecture exception (S02.1.e1): if while authoring the architecture tree design-orch discovers that a spec leaf is missing, ambiguous, or contradictory, design-orch pauses the architecture work, returns to the spec tree, closes the gap, and then resumes the architecture work. This is the only permitted backflow from architecture to spec within a single design cycle.

### @internet-researcher and @architect delegation

Design-orch spawns @internet-researchers for external context — library comparisons, prior art, best practices, known failure modes — using a fast, cheap model. Multiple researchers can run in parallel on unrelated questions. Research output lands in `design/feasibility.md §Probe records` with the `How probed: browsed <source>` convention.

Design-orch spawns @architects to explore structural approaches when the design space has genuinely different options. Each @architect receives a scoped brief naming the specific option to evaluate. Architect output becomes candidate material for an architecture leaf; design-orch decides which approach to commit after reviewing architect outputs.

Design-orch spawns @coder prototypes sparingly, only when a feasibility question requires actually running code to answer. Prototype scope is tight — measure a specific behavior, validate a library does what the docs claim — so the prototype does not drift into unscoped implementation.

### Convergence through reviewer fan-out

Design-orch runs reviewers in multiple lanes per S02.4.u1:

- **Design alignment** — does the package still match `requirements.md`? Does it satisfy every constraint the user named? Is there any user intent the spec tree does not cover?
- **Structural** — can the design be decomposed for parallel execution? Does the parallel-cluster hypothesis (if present) name concrete modules? Does any architecture leaf couple in ways the refactor agenda does not address?
- **Refactor-reviewer** — does the refactor agenda cover every structural coupling the reviewer can identify in the target state? Does every refactor entry's Architecture anchor actually point at a committed leaf (not a sketchy draft)?
- **Cross-link integrity** — are bi-directional cross-links complete? Does every spec leaf have a realizing architecture leaf? Does every architecture leaf realize at least one spec leaf?
- **EARS parseability** — does every EARS statement parse mechanically per A03.3? Any statement the reviewer cannot parse as trigger/fixture/assertion is a convergence blocker.

`dev-principles` is loaded by every reviewer as shared context (A05, revised D24). Reviewers apply the principles as judgment context — flagging over-abstraction, premature optimization, missing edge-case enumeration, or structural debt — but design-orch does not run a binary `principles: pass/fail` gate as a separate convergence criterion. Principle violations are reviewer findings, handled through the normal iteration loop like any other finding.

### Small work path

Tier selection belongs to dev-orch at the spawn boundary per S01.2.e1 — design-orch receives the tier as input (via `requirements.md` or `decisions.md`), not as its own judgment call. Design-orch materializes the package at exactly the tier dev-orch selected.

For a work item classified **small** per S01.2.s2, design-orch produces the degenerate root-only tree: `design/spec/overview.md` + `design/spec/root-invariants.md` + `design/architecture/overview.md` + `design/architecture/root-topology.md` + a possibly-empty `design/refactors.md` + `design/feasibility.md`. No subsystem directories under `spec/` or `architecture/`. The strict-TOC discipline still holds (no prose in overviews per S02.1.s1) and the two-file-minimum spec rule still holds — a single-file spec with inline EARS in `overview.md` is not legal because it violates the root-scope reserved-namespace rule S02.1.s2.

For a work item classified **medium** per S01.2.s3, design-orch produces root overviews plus one level of subtrees; each subsystem overview carries its own TOC. For **large** per S01.2.s4, design-orch produces root overviews plus two or more levels of subtrees where the work genuinely demands the depth.

If design-orch discovers mid-run that the tier was wrong — the work is larger than dev-orch estimated — design-orch terminates with a promotion signal per S01.2.w1 and dev-orch restarts design-orch on the heavier tier. Demotion is the harder direction: design-orch never demotes mid-run; the in-flight spawn terminates and dev-orch records the rationale in `decisions.md` before a lighter-tier restart.

**Trivial** work (S01.2.s1) never reaches design-orch at all — dev-orch spawns a coder + verifier directly, skipping design-orch, impl-orch, and @planner. No design package is produced.

## Interfaces

- **`meridian spawn -a design-orchestrator -f requirements.md [-f design/... -f redesign-brief.md -f plan/preservation-hint.md]`** — dev-orch spawn.
- **`meridian spawn -a internet-researcher -p "Research <topic>"`** — design-orch delegation for external context.
- **`meridian spawn -a architect -p "Evaluate <option>"`** — design-orch delegation for structural exploration.
- **`meridian spawn -a coder -p "Prototype <probe>"`** — design-orch delegation for feasibility probes.
- **`meridian spawn -a reviewer -m <diverse-model> -p "Review <focus area>"`** — design-orch convergence fan-out.
- **`meridian spawn report create --stdin`** — design-ready terminal report.

## Dependencies

- `../design-package/two-tree-shape.md` — the layout design-orch writes into.
- `../artifact-contracts/terrain-analysis.md` — the refactors.md and feasibility.md shapes.
- `../verification/ears-parsing.md` — the EARS parsing discipline design-orch must satisfy.
- `../principles/dev-principles-application.md` — the shared-context loading design-orch applies during convergence.
- `./redesign-loop.md` — the dev-orch loop that triggers redesign-cycle spawns.

## Open questions

None at the architecture level.
