# S04.4: Pre-execution structural gate

## Context

After @planner returns a plan and the planning impl-orch has accepted it as complete and consistent, the next check is the plan's `Parallelism Posture` field. The gate has one trigger: when `Cause: structural coupling preserved by design` is named on a `Parallelism Posture: sequential` plan (including the foundational-prep variant), impl-orch must **not** proceed to execution and must **not** route the plan to dev-orch as a normal plan-review checkpoint. Instead, impl-orch writes a planning-time redesign brief naming the structural coupling, cites the planner's reasoning, names the design assumption the planner could not decompose around (typically an architecture subtree shape or a refactors.md entry that the planner could not route around), and emits a terminal report routing the brief to dev-orch as a `structural-blocking` signal. The gate is the load-bearing mechanism that keeps the parallelism-first frame concrete — without it, the planner would surface structural coupling as prose in `plan/overview.md` and downstream consumers would either miss it or interpret it as an aesthetic complaint.

**Realized by:** `../../architecture/orchestrator-topology/planning-and-review-loop.md` (A04.1).

## EARS requirements

### S04.4.u1 — Structural gate fires on one specific cause

`The pre-execution structural gate shall fire when the returned plan carries Parallelism Posture: sequential and Cause: structural coupling preserved by design, and shall not fire on any other Parallelism Posture value or Cause classification.`

**Reasoning.** The other Cause values (`inherent constraint`, `runtime constraint`, `feature work too small to fan out`) describe sequential plans that are real plans and must execute normally. Firing the gate on `inherent constraint` would treat a physics-of-the-problem limitation as a design flaw.

### S04.4.e1 — Gate fires before execution and before plan-review checkpoint

`When the structural gate fires, the planning impl-orchestrator shall not proceed to the execution loop, shall not route the plan to dev-orch as a normal plan-review checkpoint, and shall terminate with a structural-blocking terminal report.`

### S04.4.e2 — Planning-time redesign brief contents

`When the structural gate fires, the planning impl-orchestrator shall write a planning-time redesign brief using the Parallelism-blocking structural issues section of redesign-brief.md, naming the specific structural coupling the planner identified, citing the planner's reasoning verbatim, and naming the design assumption the planner could not decompose around (typically an architecture subtree shape or a refactors.md entry the planner could not route around).`

### S04.4.e3 — Terminal report carries the brief reference

`When the planning impl-orchestrator emits a structural-blocking terminal report, the report shall cite the planning-time redesign brief's path on disk, summarize the structural coupling in one sentence, and route to dev-orch via the normal terminal-report channel.`

### S04.4.s1 — Gate distinguishes design problem from planner failure

`While the planning impl-orchestrator is evaluating a returned plan, the structural gate shall treat structural-blocking as a design-side signal that cannot be resolved by re-spawning the planner against the same design, and shall not consume any K_fail or K_probe slot per S04.3.e3.`

### S04.4.w1 — Foundational-prep variant is also a gate trigger

`Where @planner signals a missing foundational prep entry (net-new scaffolding, types, abstract base classes, or interface contracts that do not exist in design/feasibility.md §Foundational prep) as the cause of sequential parallelism, the structural gate shall treat the signal as equivalent to a missing-refactor signal and fire, because both are design-side gaps that impl-orch cannot route around without a design-orch revision cycle.`

### S04.4.c1 — Plan without Parallelism Posture fails the gate indirectly

`While the planning impl-orchestrator is evaluating a returned plan, when plan/overview.md omits the Parallelism Posture field or leaves Cause unnamed, the structural gate shall not fire (because no trigger is present) but the plan shall fail completeness under S04.3.e1, advancing K_fail on the planner re-spawn loop.`

**Reasoning.** The gate trigger is a positive signal from the planner; absence of the signal is a completeness failure, not a gate firing. Routing an incomplete plan through the gate would conflate two separate error modes.

## Non-requirement edge cases

- **Gate fires on `limited` posture.** An alternative would fire the gate on `Parallelism Posture: limited` with structural-coupling cause, not just on `sequential`. Rejected because a `limited` plan with some parallel rounds is still an executable plan, and firing the gate on it would forbid the common case of "most of the work parallelizes but one round is inherently serial." Flagged non-requirement because the posture-plus-cause pairing rule is load-bearing for execution viability.
- **Impl-orch attempts to decompose around the coupling.** An alternative would let impl-orch try to rewrite the plan itself when the gate fires. Rejected because impl-orch does not author plans (the single-author rule for @planner), and because the decomposition-around-coupling move is exactly what the planner already tried and failed. Flagged non-requirement to document the rejected alternative.
- **Gate routes to design-orch without dev-orch.** An alternative would have impl-orch route the structural-blocking brief directly to design-orch, skipping dev-orch. Rejected because dev-orch must classify the signal as a design problem vs a scope problem (per S06.1) and must track the redesign cycle cap counter. Flagged non-requirement because the dev-orch routing altitude is load-bearing for the autonomous redesign loop's accountability.
