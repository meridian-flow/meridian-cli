# S02.2: Architecture tree production

## Context

The architecture tree describes how the code realizes the spec tree's behaviors. It is authored **after** the spec tree (per S02.1.e1) and every architecture leaf exists because some spec leaf motivates it. The tree is **observational** — it describes the target system state as observations about how the code should be, not as prescriptions for phase ordering (phase ordering is @planner's output, not design-orch's). Impl-orch consumes the architecture tree during pre-planning, the structural reviewer reads it for decomposability, and @planner reads the subtree structure to identify disjoint parallel surfaces. Architecture-first drift is the failure mode S02.1 exists to prevent; this leaf encodes the mirror rules for the architecture side.

**Realized by:** `../../architecture/design-package/two-tree-shape.md` (A01.1).

## EARS requirements

### S02.2.u1 — Every architecture leaf carries the canonical section set

`Every architecture leaf under design/architecture/ shall contain exactly the following sections: leaf ID and title, one-line summary, Realizes cross-links to spec leaves, Current state with file paths and symbols, Target state with module layout and interfaces, Interfaces with type signatures or data shapes, Dependencies naming the local import DAG slice, and Open questions flagged for feasibility probes or impl-orch pre-planning resolution.`

### S02.2.u2 — Architecture is observational, not prescriptive

`The design-orch authoring flow shall treat the architecture tree as a description of the target system state and shall not encode phase ordering, sequencing prescriptions, or cross-cutting prep phases in architecture leaves — those responsibilities belong to @planner reading refactors.md and feasibility.md per S04.2.`

### S02.2.e1 — Architecture derives from spec

`When design-orch authors a new architecture leaf, the leaf shall include at least one Realizes cross-link to an existing spec leaf, and shall not be added to the tree unless the spec tree already contains or is about to contain the motivating spec leaf via the spec-first gap-closure rule in S02.1.e1.`

### S02.2.e2 — Bi-directional cross-link coverage

`When design-orch finalizes the design package, every spec leaf in design/spec/ shall be named in the Realized-by section of at least one architecture leaf, and every architecture leaf in design/architecture/ shall name at least one spec leaf in its Realizes section.`

**Edge cases.**

- **Orphan in spec = missing architecture.** A spec leaf with no Realized-by link means the architecture tree has not yet committed to how the behavior is implemented. This is a convergence blocker for the alignment reviewer.
- **Orphan in architecture = unmotivated target state.** An architecture leaf with no Realizes link describes code that has no spec-level justification. This is a convergence blocker: either the spec is missing a leaf or the architecture is over-specifying (possibly under-deleting).

### S02.2.s1 — Root topology lives in reserved-namespace leaves, not prose

`While design-orch is authoring an architecture tree, system-wide topology (import DAG slice, integration boundaries, current vs target posture that feeds refactors.md) shall live in design/architecture/root-topology.md (or a similarly named root-scope leaf) with IDs in the reserved A00.* namespace, and shall not live as inline prose in any overview.md.`

**Edge case.** Structural content that is not in a leaf cannot be cross-linked from `refactors.md` entries via the `Architecture anchor` field, so the structural reviewer cannot verify it. Moving posture content into a reserved-namespace leaf is the mechanical fix.

### S02.2.s2 — Observations, not recommendations

`While impl-orch may deviate from the architecture tree's observational shape when runtime evidence supports it, the deviation shall be logged in decisions.md with rationale, and impl-orch shall not silently ignore the architecture tree.`

**Edge case.** The spec tree is a contract (S00.u3). The architecture tree is an observation. Different agents have different authority: impl-orch may revise its reading of architecture when runtime data contradicts it, but may not revise a spec leaf without routing through the escape hatch or a scoped design revision. The asymmetry is load-bearing.

### S02.2.c1 — Current-state citation by file path and symbol

`While design-orch is authoring the Current state section of an architecture leaf, when the section refers to existing code, the reference shall cite file path and symbol (function/class/module name) rather than prose descriptions of what the code does.`

**Reasoning.** Prose descriptions of existing code drift immediately; file+symbol citations are falsifiable. The structural reviewer checks this during design convergence.

### S02.2.w1 — Open-questions escalation surface

`Where an architecture leaf flags a structural question design-orch could not answer with architectural reasoning alone, the leaf's Open questions section shall tag the question as either "requires feasibility probe" (routed to feasibility.md) or "requires impl-orch pre-planning resolution" (tagged `impl-orch must resolve during pre-planning`).`

## Non-requirement edge cases

- **Architecture tree as implementation plan.** A future refactor could fold impl-orch's pre-planning notes into the architecture tree. Rejected as a non-requirement because it would reintroduce the architecture-as-prescription failure mode v2 and v3 both rejected. Architecture stays observational; execution planning stays in `plan/`.
- **Deep module interfaces in architecture leaves.** An architecture leaf does not have to list every function signature — only the public contract that other leaves (or the spec) depend on. Flagged non-requirement because exhaustive signature enumeration would balloon architecture leaves and duplicate code-level documentation the `$MERIDIAN_FS_DIR` domain docs own.
