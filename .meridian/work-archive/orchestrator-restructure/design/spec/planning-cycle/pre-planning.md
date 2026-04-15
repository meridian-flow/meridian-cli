# S04.1: Pre-planning step

## Context

When the planning impl-orch starts, its first action is reading the design package and any preservation hint from a prior redesign cycle, then running the four feasibility questions against runtime context to gather the runtime data design-orch could not have. The output is `plan/pre-planning-notes.md` — a materialized runtime-observations file that the @planner spawn consumes via `-f`. Pre-planning is not a separate spawn; it is work impl-orch does in its own context, because impl-orch is the only agent in the loop with both the design package and codebase access needed to gather runtime data. The central discipline is that pre-planning enumerates module-scoped constraints and does not pre-bind a decomposition — the test for whether impl-orch is straying is whether any sentence in the notes uses the word "phase." If it does, impl-orch is doing the planner's job.

**Realized by:** `../../architecture/orchestrator-topology/planning-and-review-loop.md` (A04.1) and `../../architecture/artifact-contracts/terrain-analysis.md` (A02.1).

## EARS requirements

### S04.1.u1 — Pre-planning runs in impl-orch's own context

`The planning impl-orchestrator shall perform pre-planning as work inside its own spawn context and shall not outsource any step of pre-planning to another spawn.`

**Reasoning.** Outsourcing pre-planning to a separate agent rebuilds the v1 chain of context loss — impl-orch is the only layer with both the design package and codebase-probe access. Separating them reintroduces the handoff gap the v3 topology exists to close.

### S04.1.u2 — Pre-planning notes materialize to disk

`The planning impl-orchestrator shall write its pre-planning observations to $MERIDIAN_WORK_DIR/plan/pre-planning-notes.md before spawning @planner, and shall not hold pre-planning state only in its conversation context.`

**Reasoning.** The planner consumes pre-planning notes via `-f`. Holding them in conversation context defeats the purpose, because the legibility of the runtime observations is the value, and legibility requires materialization. A planner spawn that re-runs after a compaction should read the same inputs the original spawn did.

### S04.1.e1 — Six-step pre-planning sequence

`When the planning impl-orchestrator starts pre-planning, impl-orch shall execute the following six steps in order: read design/spec/overview.md, read design/architecture/overview.md, read design/refactors.md, read design/feasibility.md, read plan/preservation-hint.md if present (redesign cycles only), and apply the four feasibility-questions against runtime context to cover the impl-orch-tagged known unknowns from feasibility.md plus any runtime constraints design could not anticipate.`

### S04.1.e2 — Pre-planning notes carry six required sections

`When the planning impl-orchestrator writes plan/pre-planning-notes.md, the file shall contain six labeled sections: Feasibility answers (runtime deltas vs feasibility.md), Probe results (for known unknowns plus integration boundaries that needed re-verification), Architecture re-interpretation (anything runtime data contradicts or refines), Module-scoped constraints (facts about modules, never proposed phases), Spec-leaf coverage hypothesis (clusters of leaf IDs, not phases), and Probe gaps (questions impl-orch could not answer).`

### S04.1.s1 — Module-scoped constraints never pre-bind phases

`While the planning impl-orchestrator is writing pre-planning-notes.md, every runtime constraint shall be stated as a fact about specific modules (e.g. "modules X and Y share fixture Z"), and any sentence that uses the word "phase" shall be rewritten as a module-level fact, because mapping constraints onto phases is the planner's job and not impl-orch's.`

**Reasoning.** The test for whether impl-orch is straying into decomposition is whether the notes describe phases. Impl-orch's job is to make the constraint surface visible, not to pre-bind it. Pre-binding reproduces the v1 in-context mashing the restructure exists to prevent.

### S04.1.s2 — Preservation-hint scoping on redesign cycles

`While the planning impl-orchestrator is performing pre-planning on a redesign cycle, impl-orch shall scope runtime probing to the invalidated portion named in plan/preservation-hint.md and shall not re-run probes against the preserved portion, because pre-planning runtime work is proportional to the scope of the change and not to the total work item size.`

**Edge case.** If the preservation hint's `replan-from-phase` anchor is absent or ambiguous, impl-orch treats the entire work item as invalidated and runs full pre-planning. This degrades safely; over-probing is wasteful but not incorrect, under-probing could miss real gaps.

### S04.1.s3 — No re-running of probes feasibility.md already answered

`While the planning impl-orchestrator is performing pre-planning, impl-orch shall not re-run probes that design/feasibility.md already recorded with results, unless runtime context suggests the recorded result has gone stale.`

### S04.1.w1 — Cluster-hypothesis front-loading mandatory above ten leaves

`Where the design/spec/ tree contains more than ten spec leaves, the planning impl-orchestrator shall include a populated Spec-leaf coverage hypothesis section in pre-planning-notes.md before spawning @planner, clustering the leaves into parallel-eligible groups; for ten or fewer leaves the hypothesis is optional because the planner can derive it in-context without consuming a probe-request cap slot.`

**Reasoning.** Front-loading the cluster analysis the planner would otherwise derive via probe-request rounds protects both `K_fail` and `K_probe` counters from being exhausted on pre-planning gaps the notes should have caught. The ten-leaf threshold is the boundary where front-loading is cheaper than letting the planner re-derive it.

### S04.1.c1 — Pre-planning must answer impl-orch-tagged known unknowns

`While the planning impl-orchestrator is performing pre-planning, when any entry in design/feasibility.md is tagged "impl-orch must resolve during pre-planning", impl-orch shall run probes against that entry and record the answer in pre-planning-notes.md §Probe results before spawning @planner.`

**Edge case.** If the probe cannot be run (environment unavailable, required tool missing, etc.), impl-orch records the blockage in pre-planning-notes.md §Probe gaps and decides whether to spawn the planner with the gap flagged or to bail out via the planning-time arm of the escape hatch (per S05.4). The bail-out criterion is whether the gap blocks the planner from producing a converging plan — a bail-out is overreach if the gap is a single narrow question the planner could route around.

## Non-requirement edge cases

- **Pre-planning as a separate spawn.** An alternative shape would outsource pre-planning to a dedicated @pre-planner agent. Rejected because impl-orch is the only layer with both the design package and codebase-probe access, and separating the two rebuilds the v1 chain of context loss. Flagged non-requirement to document the rejection.
- **Tentative decomposition in pre-planning.** An alternative would let impl-orch sketch a tentative phase layout first and then enumerate constraints against it. Rejected because it reproduces v1 in-context mashing. Flagged non-requirement because the module-scoped-constraint-only rule is the discipline that keeps the planning boundary clean.
- **Full re-probe on every redesign cycle.** An alternative would re-run every probe on every redesign cycle regardless of preservation hint. Rejected because pre-planning runtime work should scale with change scope, not total work size. Flagged non-requirement because the preservation-scoped probing rule is load-bearing for redesign-cycle cost.
