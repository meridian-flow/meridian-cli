# S03.2: Plan review checkpoint

## Context

When the planning impl-orch terminates with a plan-ready report, dev-orch reads the plan from disk and reviews it against the design package and the user's stated intent. The review is crash-only: dev-orch never holds a suspended impl-orch in memory. If the plan fails review, dev-orch spawns a fresh planning impl-orch with the original design plus the review feedback as additional context — the pushback loop is between dev-orch and successive planning impl-orch spawns, and it does not advance the redesign loop-guard counter because no design change is happening. The judgment about how much review the plan deserves lives in dev-orch because review cost and review value both scale with scope, and the threshold is not knowable in advance.

**Realized by:** `../../architecture/orchestrator-topology/planning-and-review-loop.md` (A04.1).

## EARS requirements

### S03.2.u1 — Plan review is a six-criterion judgment

`The dev-orch plan-review checkpoint shall apply exactly six criteria, in priority order: Parallelism Posture named and justified, per-round parallelism justifications citing real constraints, refactors agenda fully accounted, spec-leaf coverage complete and exclusive at EARS-statement granularity, Mermaid fanout matches textual rounds, and plan does not contradict user-stated intent.`

### S03.2.e1 — Parallelism Posture is named and justified

`When dev-orch reviews a plan, the plan shall fail review if plan/overview.md omits the Parallelism Posture field, leaves the Cause classification unnamed, or names a Cause that does not match the structure of the plan (e.g. claims "parallel" while bundling every phase into one sequential round).`

### S03.2.e2 — Per-round justifications cite real constraints

`When dev-orch reviews a plan, the plan shall fail review if any round description uses a hand-wavy "this depends on the previous phase" justification without naming the specific dependency and what the round unlocks.`

### S03.2.e3 — Refactors agenda is fully accounted

`When dev-orch reviews a plan, every entry in design/refactors.md shall be mapped to a phase, bundled with another entry into a prep phase, or explicitly skipped with a one-sentence reason, and the plan shall fail review if any refactor entry is unaccounted.`

**Reasoning.** Unaccounted refactor entries are a planner bug, not a dev-orch judgment call. The planner has the full refactor agenda in its input; silent omission means the planner failed to reconcile it against the phase structure.

### S03.2.e4 — Spec-leaf coverage is complete and exclusive at EARS-statement granularity

`When dev-orch reviews a plan, plan/leaf-ownership.md shall claim every EARS statement in design/spec/ at S<subsystem>.<section>.<letter><number> ID granularity (not leaf-file granularity) exactly once, and the plan shall fail review if any EARS statement is unclaimed or claimed by more than one phase.`

**Edge cases.**

- **Multiple statements per leaf owned by different phases.** A single leaf file may contain multiple EARS statements ending up owned by different phases — that is legal, because the EARS statement is the ownership unit per D26. Leaf-file-granularity ownership would collapse the inside-a-leaf parallelism impossibility into a false serialization.
- **Spec drift mid-execution.** If a spec leaf is revised in-place mid-execution, its ID is preserved per S02.1.e2 so that prior `leaf-ownership.md` claims survive the revision. New EARS statements added mid-cycle must be claimed in the revised plan per S06.2 preservation-hint production.

### S03.2.e5 — Mermaid fanout matches textual rounds

`When dev-orch reviews a plan, the Mermaid diagram in plan/overview.md shall show the same parallel structure the textual round descriptions claim, and the plan shall fail review if the diagram drifts from the prose description of rounds.`

### S03.2.e6 — Plan must not contradict user-stated intent

`When dev-orch reviews a plan, the plan shall fail review if any phase re-introduces a constraint the user rejected in requirements.md or defers work the user explicitly prioritized.`

### S03.2.c2 — Pushback spawns a fresh planning impl-orch

`While dev-orch is running the plan-review checkpoint, when the plan fails any criterion, dev-orch shall spawn a fresh planning impl-orch with the original design package plus the review feedback attached via -f, and shall not edit the plan file directly.`

**Reasoning.** Crash-only contract. Direct edits by dev-orch collapse the author/reviewer boundary the same way direct leaf edits would, and they bypass the planning-cycle cap's re-spawn counters.

### S03.2.s2 — Pushback does not advance redesign counter

`While dev-orch is running successive plan-review pushback cycles, the redesign cycle counter (K=2 per S06.3) shall not advance on pushback, because no design change is happening; the planning-cycle cap on the impl-orch side (K_fail=3 + K_probe=2 plus structural-blocking short-circuit per S04.3) shall advance on each planner re-spawn instead.`

### S03.2.w1 — Small-tier plan skips user involvement

`Where a plan is obvious and the work item is classified small (per S01.2.s2), dev-orch shall approve the plan without user involvement and shall immediately spawn a fresh execution impl-orch, and shall not block on a user decision that the scope does not warrant.`

**Edge case.** Trivial work items (S01.2.s1) never reach plan review at all — trivial paths skip design-orch, impl-orch, and @planner entirely, so no plan is produced and S03.2 does not fire. Plan review only applies to small/medium/large tiers.

### S03.2.c1 — Approval handoff spawns a fresh execution impl-orch

`While the plan-review checkpoint is complete, when dev-orch approves the plan, dev-orch shall spawn a fresh execution impl-orch with the approved plan attached via -f and an explicit "execute existing plan" prompt, and the execution impl-orch shall skip pre-planning and the @planner spawn entirely and start directly at the execution loop.`

**Reasoning.** Crash-only design: the planning impl-orch terminates, its plan lands on disk, and dev-orch hands it to a fresh execution impl-orch. A suspended impl-orch holding plan state in memory would not survive a crash, a compaction, or a restart. See D15 for the terminated-spawn contract rationale.

## Non-requirement edge cases

- **Rigid "always review" or "never review" rules.** An alternative would hardcode "dev-orch always reviews" or "dev-orch never reviews unless pushback." Rejected because review cost and review value both scale with scope, and the threshold is not knowable in advance. The judgment has to happen at the altitude where scope is visible, which is dev-orch. Flagged non-requirement to document the rejection.
- **Suspended planning impl-orch across review.** An alternative would keep the planning impl-orch suspended across the review checkpoint and resume it for pushback. Rejected per D15 because meridian is crash-only — state on disk, not in conversation context. A suspended spawn holding plan state in memory cannot survive a crash, compaction, or restart. Flagged non-requirement to document the rejected alternative.
- **Dev-orch edits plan files directly.** An alternative would let dev-orch hand-edit plan files for small pushback deltas. Rejected because it bypasses the planning-cycle cap's re-spawn counters and collapses the author/reviewer boundary. Flagged non-requirement because the invariant "dev-orch never writes plan artifacts" is load-bearing for plan auditability.
