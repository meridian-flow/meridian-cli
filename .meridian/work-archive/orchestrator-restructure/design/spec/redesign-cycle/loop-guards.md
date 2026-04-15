# S06.3: Redesign loop guards

## Context

Dev-orch tracks redesign cycles per work item. The counter advances on every autonomous design-orch re-spawn regardless of which signal triggered it (execution-time, structural-blocking, or planning-blocked). If a work item goes through two autonomous redesign cycles without converging, dev-orch escalates to the user on the third bail-out rather than initiating another autonomous cycle. The escalation carries all prior briefs, all prior decisions, the preservation hints from each cycle, and a summary of what each cycle tried to fix — the user is not starting cold, but dev-orch is declining to route again without human input. Each bail-out must also cite new evidence not present in prior briefs; a duplicate brief does not advance the counter and does not trigger a new design-orch spawn. The redesign cycle counter is distinct from the planning cycle cap on the impl-orch side — planning caps count planner re-spawns within a single impl-orch cycle, redesign caps count design-orch re-spawns across the whole work item.

**Realized by:** `../../architecture/orchestrator-topology/redesign-loop.md` (A04.3).

## EARS requirements

### S06.3.u1 — Redesign cycle counter K=2 per work item

`The dev-orch redesign cycle counter shall be capped at K=2 per work item, and the third bail-out within one work item shall escalate to the user rather than initiate another autonomous cycle.`

### S06.3.u2 — Counter advances on autonomous design-orch re-spawns only

`The redesign cycle counter shall advance once per autonomous design-orch re-spawn, regardless of which entry signal triggered the cycle (execution-time falsification, structural-blocking, or planning-blocked), and shall not advance on scope-problem paths that skip design-orch per S06.1.s4 or on plan-review pushback cycles that skip design-orch per S03.2.s2.`

### S06.3.e1 — Escalation packages all prior cycle artifacts

`When dev-orch escalates to the user on the third bail-out, the escalation shall carry every prior brief, every prior decisions.md entry for the work item, every prior preservation hint, and a summary of what each cycle tried to fix, so that the user is not starting cold.`

### S06.3.e2 — Duplicate-evidence brief does not advance counter

`When dev-orch reads a brief that repeats the same falsification claim from a previous cycle without citing new evidence, dev-orch shall reject the brief as a duplicate, shall not advance the redesign cycle counter, and shall not trigger a new design-orch spawn; impl-orch shall be asked to either produce a stronger case or patch forward.`

**Reasoning.** A brief that repeats a prior cycle's claim without new evidence is looping on a failure it cannot describe in new terms. Letting duplicates advance the counter would burn redesign-cycle budget on content that design-orch already evaluated.

### S06.3.s1 — Counter is per work item, not global

`While dev-orch is tracking redesign cycles, the counter shall be scoped to the current work item and shall reset on work-item completion, and shall not span multiple work items or sum across concurrent work items.`

### S06.3.s2 — Planning cycle cap is distinct and independent

`While both dev-orch and impl-orch are counting cycles, the redesign cycle counter (K=2 at dev-orch altitude) shall be distinct from the planning cycle cap (K_fail=3 + K_probe=2 at impl-orch altitude per S04.3), and the two counters shall advance on separate events: redesign counts design-orch re-spawns, planning counts @planner re-spawns.`

**Reasoning.** Sharing a counter would conflate two different failure modes. A work item that burns planner slots on pre-planning gap discovery should not also spend a design-revision slot. See D12 for the split-counter rationale.

### S06.3.s3 — Heuristic threshold, not hard cap

`While dev-orch is applying the K=2 threshold, the threshold shall function as a heuristic for when dev-orch's confidence in autonomous routing should drop rather than as a hard cap that cannot be overridden, and dev-orch may escalate sooner if it judges earlier cycles to have already revealed a framing problem.`

**Reasoning.** A single cycle is a normal mid-course correction, two cycles is a scoping issue worth noticing, three or more cycles means the framing of the redesign itself is probably wrong and dev-orch should not trust its own routing. The threshold is a heuristic for confidence, not a mechanical gate. See D7 for the rationale.

### S06.3.w1 — User escalation is not work-item abandonment

`Where dev-orch escalates to the user on the third bail-out, the user shall have the option to approve another autonomous cycle, revise the requirements, or abandon the work item, and dev-orch shall not abandon the work item unilaterally without user input.`

### S06.3.s4 — Decision log records every counter advance

`While dev-orch is running the redesign loop, every counter advance shall be recorded in decisions.md with the triggering signal, the brief reference, the classification decision, and the routing outcome, so that a post-hoc reader can reconstruct the loop state from decisions.md alone.`

## Non-requirement edge cases

- **K=1 threshold (escalate on second bail-out).** An alternative would cap autonomous routing at one cycle. Rejected because a single cycle is normal mid-course correction, and escalating to the user after one cycle would wake the user for problems that are reliably autonomous. Flagged non-requirement to document the rejected lower bound.
- **K=∞ (never escalate).** An alternative would never cap autonomous routing and let dev-orch loop indefinitely. Rejected because three or more cycles usually means the framing of the redesign itself is wrong, and dev-orch should not trust its own routing past that point. Flagged non-requirement because the K=2 heuristic is the confidence floor.
- **Shared counter between planning and redesign caps.** An alternative would share a single counter across impl-orch planner re-spawns and dev-orch design-orch re-spawns. Rejected because the two events have different semantics — planner re-spawns count input-unchanged failures, design-orch re-spawns count design-change cycles. Sharing the counter would let one cycle consume slots meant for the other and would confuse audit. Flagged non-requirement because the split-counter rule is load-bearing for loop accountability.
