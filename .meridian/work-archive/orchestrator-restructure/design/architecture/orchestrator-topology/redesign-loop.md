# A04.3: Redesign loop

## Summary

Dev-orch runs the autonomous redesign loop. It receives bail-out briefs from planning impl-orch and execution impl-orch (three entry signals — execution-time falsification, structural-blocking, planning-blocked), classifies each brief as a design-problem or scope-problem, routes design-problems through a fresh design-orch spawn, routes scope-problems through a fresh impl-orch spawn, produces preservation hints on design-problem paths, tracks a K=2 cycle counter, and escalates to the user on the third bail-out within one work item.

## Realizes

- `../../spec/redesign-cycle/autonomous-loop.md` — S06.1.u1 (three entry signals, one loop), S06.1.e1 (design-vs-scope classification), S06.1.e2 (design-problem spawns design-orch), S06.1.e3 (scope-problem spawns fresh impl-orch), S06.1.s1 (autonomy default), S06.1.s2 (autonomy with visibility), S06.1.c2 (push back on weak briefs), S06.1.w1 (design-problem triggers hint production), S06.1.s4 (scope-problem skips hint).
- `../../spec/redesign-cycle/preservation-hint-production.md` — S06.2.u1 (dev-orch sole author), S06.2.u2 (overwrite per cycle), S06.2.e1 (six-step production sequence), S06.2.e3 (newly introduced leaves get fresh IDs), S06.2.s2 (replan-from-phase anchor scopes planning work), S06.2.s3 (constraints-that-still-hold land in direct context), S06.2.c1 (decision log records every preservation revision), S06.2.c2 (dev-orch may revise impl-orch's claims), S06.2.w1 (absent on first cycle and scope-problem paths).
- `../../spec/redesign-cycle/loop-guards.md` — S06.3.u1 (K=2 per work item), S06.3.u2 (advances on autonomous design-orch re-spawns), S06.3.e1 (escalation packages prior artifacts), S06.3.e2 (duplicate-evidence rejection), S06.3.s1 (per work item scoping), S06.3.s2 (distinct from planning cap), S06.3.s3 (heuristic threshold), S06.3.w1 (user escalation is not abandonment), S06.3.s4 (decision log records advances).

## Current state

- v2 has no autonomous redesign routing. A bail-out from impl-orch escalates to the user unconditionally, and every redesign cycle requires human intervention to decide whether to respawn design-orch.
- v2 has no formal cycle counter for redesigns. Work items can loop indefinitely on the same falsification without dev-orch noticing that framing has become unreliable.
- v2 has no preservation hint artifact; phase-preservation across redesigns is an implicit convention rather than an on-disk contract.

## Target state

### Three entry signals, one loop

Dev-orch receives terminal reports from impl-orch via `meridian spawn show` or `meridian spawn wait`. Three report types enter the redesign loop (S06.1.u1):

1. **Execution-time falsification** (from execution impl-orch) — the runtime evidence contradicts a claimed spec leaf. Brief cites the falsified EARS statement IDs and the tester evidence.
2. **Structural-blocking** (from planning impl-orch or execution impl-orch) — the structural gate fired, or final-review-time revealed structural coupling the design did not cover. Brief cites the Parallelism Posture claim or the coupling evidence.
3. **Planning-blocked** (from planning impl-orch) — K_fail or K_probe exhausted, @planner cannot produce a plan the structural gate accepts. Brief cites the exhausted counter and the repeated failure mode.

All three signals enter the same loop. Dev-orch does not branch on the signal type at the top of the loop — it branches on classification (design-problem vs scope-problem) after reading the brief.

### Classification: design-problem vs scope-problem

Dev-orch reads the brief and decides per S06.1.e1:

- **Design-problem** — the falsification reveals a gap or error in the design package. The spec tree is wrong, the architecture tree is wrong, or the refactor agenda missed a structural coupling. Action: respawn design-orch with the brief attached to revise the affected leaves.
- **Scope-problem** — the falsification is real but the design is still correct; the work item's scope was too broad or too narrow, or the implementation choice conflicts with the design without invalidating it. Action: respawn a fresh planning impl-orch with the brief attached, skip design-orch, do not advance the redesign cycle counter (S06.3.u2).

Borderline briefs (genuinely ambiguous between the two categories) default to design-problem because spec revision is the safer action — running design-orch on a scope-problem produces a revised design that is functionally equivalent to the original, while running an impl-orch cycle on a design-problem produces execution work that will re-falsify. The cost of an unnecessary design-orch spawn is lower than the cost of a misrouted impl-orch spawn.

### Design-problem routing

1. **Dev-orch advances the redesign cycle counter.** K = K + 1 (S06.3.u2). If K > 2, dev-orch escalates to the user instead of routing automatically (see "Cycle guards" below).
2. **Dev-orch writes `preservation-hint.md`.** Six-step production sequence per S06.2.e1:
   1. Read the brief's preservation section.
   2. Read the revised design docs — spec tree diff, architecture tree diff, updated refactors.md and feasibility.md — to confirm which phases are still valid.
   3. For each entry in the preservation section, decide whether the design revision changed the assessment.
   4. Enumerate the new and revised spec leaves introduced by the redesign so the planner claims every affected leaf.
   5. Write `plan/preservation-hint.md` with the final preservation lists, the replan-from-phase anchor, and the leaf delta.
   6. Prepare the design-orch spawn with revised design package + preservation-hint attached via `-f`.

   Dev-orch may revise impl-orch's preservation classification (S06.2.c2) if the design revision changed the assessment. The final hint is dev-orch's decision.

3. **Dev-orch spawns design-orch.** Fresh spawn with the brief and the prior design package attached. Design-orch revises the affected leaves and returns a revised design. On return, dev-orch reads the revised design and runs the design-walk + plan-review sequence as a new cycle.
4. **Dev-orch logs the counter advance.** `decisions.md` entry per S06.3.s4 naming the triggering signal, the brief reference, the classification decision, and the routing outcome. This is the audit trail that lets a post-hoc reader reconstruct the loop state from `decisions.md` alone.

### Scope-problem routing

1. **Dev-orch does not advance the redesign counter.** Scope-problem paths skip design-orch per S06.1.s4, so no design-orch re-spawn happens, and the counter stays where it was (S06.3.u2).
2. **Dev-orch does not write a preservation hint.** The design is unchanged, so there is no hint to derive (S06.2.w1, S06.1.s4). The planning impl-orch that re-spawns reads the existing plan and pre-planning notes, not a new hint.
3. **Dev-orch spawns a fresh planning impl-orch.** Attaches the brief and the existing design package. The fresh planning impl-orch re-runs pre-planning with the scope correction in mind, re-spawns @planner, and emits a plan-ready terminal report as usual.
4. **Dev-orch logs the classification.** `decisions.md` entry naming the scope correction and the routing choice.

### Cycle guards

K = 2 per work item (S06.3.u1). The counter advances once per autonomous design-orch re-spawn, regardless of entry signal. It does not advance on:

- Scope-problem paths that skip design-orch (S06.3.u2).
- Plan-review pushback cycles that stay within one design cycle (S03.2.s2).
- Planning-cycle cap failures at the impl-orch altitude (the planning cap K_fail/K_probe is distinct per S06.3.s2).

On the third bail-out within one work item, dev-orch escalates to the user per S06.3.e1. The escalation package carries:

- Every prior redesign brief (cycle-by-cycle).
- Every prior `decisions.md` entry for the work item.
- Every prior preservation hint (cycle-by-cycle).
- A summary of what each cycle tried to fix and what falsified.

The user chooses (S06.3.w1): approve another autonomous cycle, revise the requirements, or abandon the work item. Dev-orch does not abandon unilaterally.

### Duplicate-evidence rejection

If the brief repeats a falsification claim from a prior cycle without citing new evidence, dev-orch rejects the brief as duplicate (S06.3.e2). The counter does not advance, no design-orch spawn fires, and impl-orch is asked to either produce a stronger case or patch forward. This closes the failure mode where an impl-orch looping on a single issue burns through the redesign budget without surfacing new information.

### Heuristic threshold, not hard cap

K = 2 is a confidence heuristic, not a mechanical gate (S06.3.s3). Dev-orch may escalate sooner if it judges earlier cycles to have already revealed a framing problem — for example, if the first cycle's brief shows that the user intent is itself ambiguous, dev-orch can escalate after cycle 1 instead of routing to design-orch. The threshold says "confidence in autonomous routing should drop past this point," not "never route past this point."

The underlying logic: one cycle is a normal mid-course correction; two cycles is a scoping issue worth noticing; three or more cycles means the framing of the redesign itself is probably wrong and dev-orch should not trust its own routing.

## Interfaces

- **`meridian spawn wait <impl-orch-spawn-id>`** — dev-orch reads impl-orch's terminal report.
- **`meridian spawn -a design-orchestrator -f design/... -f redesign-brief.md -f plan/preservation-hint.md`** — dev-orch spawns design-orch on design-problem paths.
- **`meridian spawn -a impl-orchestrator -f design/... -f redesign-brief.md`** — dev-orch spawns a fresh planning impl-orch on scope-problem paths.
- **`plan/preservation-hint.md`** — dev-orch writes the hint on design-problem paths.
- **`decisions.md`** — append-only log of every counter advance, classification, and routing decision.

## Dependencies

- `./planning-and-review-loop.md` — produces structural-blocking and planning-blocked reports that enter this loop.
- `./execution-loop.md` — produces execution-time falsification reports that enter this loop.
- `./design-phase.md` — design-orch's cycle, re-run on design-problem paths.
- `../artifact-contracts/preservation-and-brief.md` — the brief and hint shapes this loop consumes and produces.

## Open questions

None at the architecture level.
