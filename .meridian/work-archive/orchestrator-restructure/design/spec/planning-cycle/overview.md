# S04: Planning Cycle — Subsystem Overview

## Purpose

This subsystem covers the planning impl-orchestrator's cycle from startup through @planner spawn to plan-ready terminal report. It encodes the pre-planning step impl-orch runs against runtime context, the planner-spawn handoff with materialized `-f` inputs, the two-counter planning cycle cap (K_fail for failed plans + K_probe for probe-requests) with the structural-blocking short-circuit, and the pre-execution structural gate driven by the planner's `Parallelism Posture` field. The cycle ends with a terminal report routed to dev-orch — plan-ready, structural-blocking, or planning-blocked. This overview is a strict TOC; substantive EARS requirements live in the leaf files.

## TOC

- **S04.1** — Pre-planning step ([pre-planning.md](pre-planning.md)): the six-step read/probe sequence, module-scoped constraint enumeration (never pre-binding a decomposition), `plan/pre-planning-notes.md` materialization, and the mandatory cluster-hypothesis front-loading rule for work items with more than ten spec leaves.
- **S04.2** — Planner spawn ([planner-spawn.md](planner-spawn.md)): the `-f` input set (spec tree + architecture tree + refactors.md + feasibility.md + pre-planning notes + decision log + preservation hint on redesign cycles), the no-refactor-invention rule, the probe-request channel, and the terminal-shape contract (plan vs probe-request vs structural-blocking).
- **S04.3** — Planning cycle cap ([cycle-cap.md](cycle-cap.md)): K_fail=3 failed-plan counter semantics, K_probe=2 probe-request counter semantics, structural-blocking short-circuit bypassing both counters, exits (convergent plan, short-circuit, K_fail exhausted, K_probe exhausted) and the `planning-blocked` signal shape.
- **S04.4** — Pre-execution structural gate ([structural-gate.md](structural-gate.md)): the `Parallelism Posture: sequential` + `Cause: structural coupling preserved by design` trigger, the planning-time redesign brief contents, and the `structural-blocking` terminal report signal routing back to dev-orch.

## Reading order

Read S04.1 first — pre-planning sets up every input the planner depends on. Then S04.2 for the handoff contract, then S04.3 for the cycle cap mechanics that bound planner re-spawns, then S04.4 for the structural gate that inspects the returned plan. The corresponding architecture content lives in `../../architecture/orchestrator-topology/planning-and-review-loop.md` (A04.1).
