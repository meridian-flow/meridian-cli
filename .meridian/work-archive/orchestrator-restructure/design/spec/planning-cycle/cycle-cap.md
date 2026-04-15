# S04.3: Planning cycle cap

## Context

Planner re-spawns are bounded by two independent counters with distinct semantics, plus a structural-blocking short-circuit that bypasses both. `K_fail=3` caps failed-plan re-spawns (planner returned a plan but the plan was incomplete, incoherent, or contradicted pre-planning notes). `K_probe=2` caps probe-request re-spawns (planner returned a probe-request report rather than a plan, asking for inputs it did not have). The two counters exist separately because D12's "same inputs, same failure" logic applies only to failed plans — a probe-request changes the inputs on the next spawn, so it is not a same-inputs-same-failure scenario and should not compete for slots with genuinely failed plans. Structural-blocking is a design-side signal, not a planner failure, and therefore advances neither counter — re-spawning against the same design cannot resolve a structural-coupling complaint.

**Realized by:** `../../architecture/orchestrator-topology/planning-and-review-loop.md` (A04.1).

## EARS requirements

### S04.3.u1 — Two independent counters, one short-circuit

`The planning impl-orchestrator shall maintain two independent planner-re-spawn counters, K_fail (capped at 3) and K_probe (capped at 2), plus a structural-blocking short-circuit that bypasses both counters when fired.`

### S04.3.e1 — K_fail advances on rejected plans

`When the planning impl-orchestrator rejects a returned plan because it is missing required sections, has unclaimed or double-claimed spec leaves, has unmapped refactors.md entries, contradicts pre-planning notes, or contains hand-wavy parallelism justifications that do not cite real constraints, the planning impl-orchestrator shall advance K_fail by one.`

### S04.3.e2 — K_probe advances on probe-request terminations

`When the @planner spawn terminates with a probe-request report rather than a plan, the planning impl-orchestrator shall advance K_probe by one and shall not advance K_fail, because the planner is asking for inputs it did not have, not failing to converge on inputs it did have.`

### S04.3.e3 — Structural-blocking short-circuit advances neither counter

`When the @planner spawn terminates with Parallelism Posture: sequential and Cause: structural coupling preserved by design (including the foundational-prep variant), the planning impl-orchestrator shall advance neither K_fail nor K_probe, shall skip any remaining re-spawns, and shall route a structural-blocking terminal report to dev-orch immediately.`

### S04.3.e4 — Conflicting signals: structural-blocking wins

`When a returned plan both fails completeness or consistency AND ships with Parallelism Posture: sequential + Cause: structural coupling preserved by design, the planning impl-orchestrator shall treat the structural-blocking signal as dominant, skip the re-spawn regardless of remaining K_fail or K_probe slots, and emit the structural-blocking terminal report.`

**Reasoning.** A planner that can correctly diagnose structural coupling while simultaneously failing to write a clean plan is still diagnosing a real design problem. Treating the completeness failure as the primary signal would waste slots re-spawning against an unchanged structural coupling.

### S04.3.s1 — Exits from the planning loop are exactly four shapes

`While the planning impl-orchestrator is running the planner loop, the loop shall exit via exactly one of four shapes: convergent plan (advances neither counter, proceeds to pre-execution structural gate), structural-blocking short-circuit (advances neither counter, emits structural-blocking terminal report), K_fail exhausted (emits planning-blocked terminal report after three failed plans), or K_probe exhausted (emits planning-blocked terminal report with Cause: probe-request loop after two probe-request re-spawns).`

### S04.3.s2 — Counters are independent, not a shared budget

`While the planning impl-orchestrator is maintaining K_fail and K_probe, the counters shall be independent: a work item that burns one probe-request, then one failed plan, then a convergent plan exits via convergent-plan with neither counter exhausted; a work item that burns three failed plans with no probe-requests exits via K_fail exhausted regardless of unused K_probe slots.`

### S04.3.s3 — Cap exhaustion emits `planning-blocked` terminal report

`While the planning impl-orchestrator is handling a cap exhaustion, the terminal report shall name the exhausted counter, cite the planner's last-attempt artifact, quote the gap reasoning impl-orch provided on each re-spawn, and route to dev-orch as planning-blocked rather than re-spawning a fourth time.`

### S04.3.w1 — Planning cap is distinct from redesign cap

`Where the planning impl-orchestrator is counting planner re-spawns, the counters shall be distinct from the redesign cycle cap (K=2 at dev-orch altitude per S06.3): planning caps count planner re-spawns within a single impl-orch cycle, redesign cap counts design-orch re-spawns across the whole work item.`

**Reasoning.** Sharing a counter between planning and redesign would conflate two different failure modes. A work item that burns planner slots on pre-planning gap discovery should not also spend a design-revision slot. See D12 for the split-counter rationale.

### S04.3.s4 — Probe-request loop reports Cause `probe-request loop`

`While the planning impl-orchestrator is emitting a planning-blocked terminal report after K_probe exhaustion, the terminal report shall carry Cause: probe-request loop, and the runtime data the planner keeps asking for shall be summarized as either unknowable or design-relevant in the report's gap-reasoning section.`

## Non-requirement edge cases

- **Single shared counter (K=5).** An alternative would use one counter covering both failed plans and probe-requests. Rejected because the two failure modes have different semantics — failed plans advance under the "same inputs, same failure" logic (D12), probe-requests change the inputs on each re-spawn. A shared counter would let a work item exhaust five probe-requests without ever seeing a genuine failed-plan attempt, or would exhaust after three failed plans with unused slots that could have absorbed a probe-request. Flagged non-requirement to document the rejection.
- **Structural-blocking advancing K_fail.** An alternative would advance K_fail on structural-blocking and let the loop continue until K_fail exhausted. Rejected because re-spawning the planner against the same design cannot resolve a structural-coupling complaint — the loop would burn three slots for a signal that is already actionable on the first emission. Flagged non-requirement because the short-circuit is load-bearing for planning-cycle cost.
- **Automatic design revision on K_fail exhaustion.** An alternative would auto-route K_fail exhaustion directly to design-orch without going through dev-orch. Rejected because the judgment of whether planning-blocked is a design problem or a scoping problem belongs to dev-orch (per S06.1). Flagged non-requirement because the dev-orch routing altitude is load-bearing for the autonomous redesign loop's accountability.
