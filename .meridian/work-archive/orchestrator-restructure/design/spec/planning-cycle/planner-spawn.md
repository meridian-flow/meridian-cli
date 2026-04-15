# S04.2: Planner spawn

## Context

After pre-planning notes land, the planning impl-orch spawns @planner with the design package, the pre-planning notes, the preservation hint (if present), and the decision log — all attached via `-f` because materialized handoffs survive compaction and rerun. @planner is a separate agent because fresh context isolates planning from execution noise, compaction-tolerant handoffs survive crashes, decomposition-optimized model routing is independent from execution-coordination routing, and a separate spawn forces legibility by forcing runtime observations to be written down instead of held implicitly in conversation state. The planner's job is not "write a plan" — it is "sequence the refactor agenda design-orch produced, sequence the architecture subtrees for parallel execution, and map phases to spec leaves at EARS-statement granularity." @planner does not invent refactors or foundational prep; missing structure escalates via the structural-blocking signal.

**Realized by:** `../../architecture/orchestrator-topology/planning-and-review-loop.md` (A04.1).

## EARS requirements

### S04.2.u1 — @planner is spawned by planning impl-orch, not dev-orch

`The planning impl-orchestrator shall be the sole caller of @planner, and dev-orch shall not spawn @planner directly.`

**Reasoning.** @planner needs runtime context only impl-orch can gather during pre-planning. Inserting dev-orch between impl-orch and the planner would force dev-orch to relay information it does not own. See planner.md's five LLM-specific reasons for the separate-agent boundary.

### S04.2.u2 — Planner is single-shot

`The @planner agent shall run once per planner spawn, write plan artifacts to disk, and terminate; it shall not loop, supervise execution, or spawn other agents.`

### S04.2.e1 — Full `-f` input set on every spawn

`When the planning impl-orchestrator spawns @planner, the spawn shall attach via -f: design/spec/ (every leaf plus the root overview), design/architecture/ (every leaf plus the root overview), design/refactors.md, design/feasibility.md, decisions.md, plan/pre-planning-notes.md, requirements.md when present, and plan/preservation-hint.md on redesign cycles only.`

### S04.2.e2 — Planner writes four artifact files

`When the @planner spawn terminates with a converged plan, the spawn shall have written plan/overview.md (with Parallelism Posture, per-round parallelism justifications, refactor-handling table, Mermaid diagram), per-phase plan/phase-N-<slug>.md blueprints, plan/leaf-ownership.md at EARS-statement granularity, and plan/status.md seeded with phase values.`

### S04.2.e3 — No-refactor-invention rule

`When @planner is decomposing the work, @planner shall not add a cross-cutting prep phase anchored to any refactor or foundational-prep item that does not already exist in design/refactors.md or design/feasibility.md §Foundational prep; any missing refactor or missing foundational prep the planner detects shall escalate via either the probe-request channel or the structural-blocking signal.`

**Reasoning.** Laundering a design problem into a plan problem breaks the traceability chain from design intent to executed refactor. The planner's move when it catches itself reaching for "add a new cross-cutting prep phase" is to classify the gap and escalate, not to silently patch.

### S04.2.e4 — Every refactor entry accounted

`When @planner finalizes plan/overview.md, every entry in design/refactors.md shall be in one of three states: landed as part of a named phase, bundled with another entry into a single refactor-prep phase, or skipped with a one-sentence reason in the refactor-handling table; unaccounted entries shall cause impl-orch to reject the plan per S04.3.`

### S04.2.e5 — Spec-leaf claim at EARS-statement granularity

`When @planner writes plan/leaf-ownership.md, claims shall be at EARS-statement ID granularity (S<subsystem>.<section>.<letter><number>), every EARS statement in design/spec/ shall be claimed by exactly one phase, and a single leaf file may have its multiple EARS statements split across multiple phases.`

**Reasoning.** Leaf-file-granularity ownership would collapse inside-a-leaf parallelism into a false serialization. A leaf with three EARS statements (e.g. an integration invariant plus two feature variants) legitimately splits across a feature-fanout phase and a later integration phase.

### S04.2.s1 — Terminal-shape contract

`While the planning impl-orchestrator is waiting on a @planner spawn, the spawn shall terminate with exactly one of three terminal shapes: a converged plan (all four artifact files written), a probe-request report (named questions, no plan files), or a structural-blocking signal (plan/overview.md with Parallelism Posture: sequential + Cause: structural coupling preserved by design).`

### S04.2.c2 — Probe-request channel routes through impl-orch, not feasibility.md

`While @planner is running, when @planner identifies runtime data it needs that neither design-orch nor impl-orch captured, @planner shall terminate with a probe-request report naming the specific runtime questions, and impl-orch shall run the requested probes, append results to plan/pre-planning-notes.md, and re-spawn @planner with the expanded notes; @planner shall not append to design/feasibility.md directly.`

**Reasoning.** design/feasibility.md is design-orch's artifact, owned by design-orch per S02.3.c1. Letting @planner append would cross the author boundary and break the single-author rule that keeps terrain analysis auditable.

### S04.2.s3 — Pre-planning-notes as projection, not runtime ground truth

`While @planner is consuming plan/pre-planning-notes.md, @planner shall treat the notes as a projection of runtime context — the runtime data impl-orch chose to write down — and shall use the probe-request channel when its decomposition requires runtime context the notes do not cover, rather than guessing silently.`

### S04.2.w1 — Preservation hint is an additional `-f` on redesign cycles

`Where a prior redesign cycle has produced plan/preservation-hint.md, the planning impl-orchestrator shall attach the hint via -f to the @planner spawn, and @planner shall honor the replan-from-phase anchor and populate leaf-ownership.md entries for preserved phases from the hint's Spec leaves satisfied column with revised-leaf re-verification annotations.`

### S04.2.c1 — Planner may not silently guess on missing runtime context

`While @planner is producing a plan, when @planner must make a decomposition assumption because of a missing pre-planning observation, @planner shall surface the assumption explicitly in plan/overview.md under a Pre-planning gaps section naming the missing data and the assumed value, or terminate with a probe-request; silent assumptions that do not appear in either channel shall be treated as a planner bug.`

## Non-requirement edge cases

- **In-context planning inside impl-orch.** An alternative would fold planning into impl-orch's own context and skip the spawn. Rejected because fresh context isolates planning from execution noise, compaction tolerance requires materialized handoffs, different skill loadouts focus each agent, and model routing for decomposition can diverge from model routing for execution coordination. Flagged non-requirement because the separate-agent boundary is load-bearing.
- **Dev-orch spawns @planner before impl-orch.** An alternative (v0 topology) would have dev-orch spawn @planner before impl-orch starts, then hand the plan to impl-orch. Rejected because the planner would be running before runtime context exists, which is the v1 streaming-parity-fixes stale-plan failure mode this restructure exists to close. Flagged non-requirement to document the rejected ordering.
- **Planner appends to feasibility.md on probe-request.** An alternative would let @planner append probe results directly to feasibility.md. Rejected because feasibility.md is design-orch's single-author artifact and cross-author writes break auditability. Flagged non-requirement because the single-author rule is load-bearing for terrain-analysis trust.
