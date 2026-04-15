# S01.2: Problem-size scaling

## Context

Not every work item earns the full hierarchical SDD ceremony. A one-line fix does not justify a two-tree design package with EARS leaves and a companion architecture tree. D23 names four tiers — **trivial**, **small**, **medium**, **large** — and this leaf encodes when each tier applies. The selector runs during dev-orch's requirements-gathering pass (S01.1) and binds the depth of S02 (design production) before design-orch is spawned. Forcing heavy ceremony on small work is Fowler's critique of one-size-fits-all SDD; scaling depth to scope is how v3 dodges it.

**Realized by:** `../../architecture/orchestrator-topology/design-phase.md` (A04.4).

## EARS requirements

### S01.2.e1 — Selection happens at spawn boundary

`When dev-orch completes the user-intent conversation for a work item, dev-orch shall select exactly one path from {trivial, small, medium, large} and record the selection in requirements.md or decisions.md before spawning design-orch (or skipping design-orch for the trivial path).`

### S01.2.s1 — Trivial path skips design entirely

`While a work item is classified trivial (one-line fix, rename, documentation typo), dev-orch shall spawn a coder + verifier directly and shall not spawn design-orch, impl-orch, or @planner.`

**Edge case.** A "trivial" classification is cheap to revise: if the coder or verifier surfaces unexpected scope during execution, dev-orch terminates the trivial path and restarts the work item on the light design path. This is not a bail-out — no redesign brief is produced because there was no design to revise.

### S01.2.s2 — Light path produces a degenerate root-only tree

`While a work item is classified small (single concept, few files, obvious structure), design-orch shall produce design/spec/overview.md + design/spec/root-invariants.md + design/architecture/overview.md + design/architecture/root-topology.md + possibly-empty design/refactors.md + design/feasibility.md, with no subtrees under spec/ or architecture/.`

**Edge case.** An empty `refactors.md` is still produced — it contains one sentence ("no refactors required for this work item — reasoning: …") rather than being absent. Missing files are indistinguishable from "file not yet written," which breaks the completeness check downstream consumers run.

### S01.2.s3 — Medium path produces one level of subtrees

`While a work item is classified medium (multiple subsystems, non-trivial integration, some refactoring), design-orch shall produce root overviews plus one level of subtrees under design/spec/ and design/architecture/, with each subsystem overview carrying its own subtree TOC.`

### S01.2.s4 — Heavy path allows multi-level subtrees

`While a work item is classified large (multi-subsystem, protocol work, significant refactoring, many interacting capabilities), design-orch shall produce root overviews plus two or more levels of subtrees under design/spec/ and design/architecture/ where the work genuinely demands the depth.`

### S01.2.s5 — Heavy path is mandatory on scope triggers

`While a work item touches more than three subsystems, introduces a cross-cutting refactor, or involves an external integration boundary, dev-orch shall select medium or large (never trivial or small) regardless of how compact the user's intent appears.`

**Edge case.** The scope triggers override user-facing perception. A user may describe a feature in two sentences that requires editing four subsystems and a protocol wire; the feature's observable simplicity does not make the design trivial. Dev-orch evaluates scope against the codebase, not against the user's framing.

### S01.2.w1 — Demotion allowed when feasible, promotion is free

`Where a work item was initially classified at one tier and a subsequent cycle reveals the tier was wrong, dev-orch shall promote to a heavier tier without user input, and may demote to a lighter tier only after the in-flight design-orch spawn has terminated and `decisions.md` records the rationale.`

**Edge cases.**

- **Promotion during design.** If design-orch is mid-run and discovers the work is larger than dev-orch estimated, design-orch terminates with the new-tier recommendation and dev-orch restarts design-orch on the heavier path. Dev-orch does not need to re-ask the user.
- **Demotion is harder.** Demoting mid-cycle risks discarding in-progress design work. The termination-and-rationale gate prevents ad-hoc demotion that could lose context.

## Non-requirement edge cases

- **Per-phase tier inheritance.** Individual phases within a work item do not get their own tier classification. The tier is a property of the work item, set once at dev-orch's entry to the cycle. Flagged non-requirement because trying to tier phases would turn the selector into a per-phase gate.
- **Automatic tier inference from repo metrics.** Counting modified files or subsystems programmatically is tempting but out of scope for v3. The selector is dev-orch's judgment informed by the codebase, not a script. Flagged non-requirement because adding a metric pipeline to dev-orch would bloat the orchestrator without measurable gain.
