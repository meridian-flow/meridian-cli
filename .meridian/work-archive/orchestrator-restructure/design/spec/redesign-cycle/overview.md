# S06: Redesign Cycle — Subsystem Overview

## Purpose

This subsystem covers dev-orch's autonomous redesign loop — the flow dev-orch runs when an impl-orch terminal report cites a redesign brief. There are three entry signals (execution-time falsification, structural-blocking, planning-blocked), all routed through the same loop. Dev-orch decides whether the brief is a design problem (needs design-orch re-engagement) or a scope problem (next impl-orch cycle can resolve with a narrower plan or additional probes), produces a preservation hint after every design-orch revision cycle, and tracks a redesign cycle counter (K=2) that escalates to the user on the third bail-out. The loop runs without user input by default because the user is a bottleneck on response time, not on judgment — dev-orch has the original requirements, the full design context, and the brief, so routing the redesign does not require human-unique information. Autonomy with visibility, though: every bail-out triggers a user notification and every cycle is logged to decisions.md. This overview is a strict TOC; substantive EARS requirements live in the leaf files.

## TOC

- **S06.1** — Autonomous loop and routing ([autonomous-loop.md](autonomous-loop.md)): the three entry signals (execution-time, structural-blocking, planning-blocked), the design-vs-scope routing decision, the scoped design-orch spawn with redesign brief context, and the autonomy-with-visibility discipline (user notification + decision log).
- **S06.2** — Preservation hint production ([preservation-hint-production.md](preservation-hint-production.md)): the six-step production sequence (read brief preservation section, read revised design, decide replan-from-phase anchor, replay constraints-that-still-hold, list new/revised spec leaves, write plan/preservation-hint.md), the revised-leaf annotation, and the overwrite-on-cycle rule.
- **S06.3** — Loop guards ([loop-guards.md](loop-guards.md)): the K=2 redesign cycle counter, escalation to user on the third bail-out with all prior briefs/decisions/hints attached, the new-evidence requirement for each bail-out, and the distinction from the planning cycle cap on impl-orch's side.

## Reading order

Read S06.1 first — the autonomous loop shape sets up every downstream decision. Then S06.2 for the preservation hint production that scopes the next cycle's work. Then S06.3 for the loop guards that cap autonomous routing at two cycles before the user is brought back in. The corresponding architecture content lives in `../../architecture/orchestrator-topology/redesign-loop.md` (A04.3) and `../../architecture/artifact-contracts/preservation-and-brief.md` (A02.3).
