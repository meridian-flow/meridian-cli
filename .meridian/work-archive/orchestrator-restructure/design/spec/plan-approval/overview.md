# S03: Plan Approval — Subsystem Overview

## Purpose

This subsystem covers @dev-orchestrator's user-facing approval walk over a converged design package and the plan-review checkpoint that sits between the planning impl-orch run and the execution impl-orch run. S03 leaves encode the altitude-based review contract (root overviews + refactor agenda, drill-down on demand) and the six concrete criteria dev-orch applies to every materialized plan before spawning a fresh execution impl-orch. This overview is a strict TOC; substantive EARS requirements live in the leaf files.

## TOC

- **S03.1** — Two-tree approval walk ([two-tree-walk.md](two-tree-walk.md)): dev-orch walks `design/spec/overview.md` + `design/architecture/overview.md` + `design/refactors.md` with the user, with `design/feasibility.md` available on demand and leaf drill-down routed back through design-orch for pushback.
- **S03.2** — Plan review checkpoint ([plan-review.md](plan-review.md)): the six plan-review criteria (Parallelism Posture named and justified, per-round justifications cite real constraints, refactors agenda fully accounted, spec-leaf coverage complete and exclusive at EARS-statement granularity, Mermaid fanout matches textual rounds, plan does not contradict user intent) and the terminated-spawn pushback protocol.

## Reading order

Read S03.1 first — the approval walk shape scopes what "approving a design" means and sets up which artifacts feed the plan review. Then S03.2 for the plan-review checkpoint that runs after the planning impl-orch terminates and before a fresh execution impl-orch is spawned. The corresponding architecture content lives in `../../architecture/orchestrator-topology/planning-and-review-loop.md` (A04.1) and `../../architecture/orchestrator-topology/design-phase.md` (A04.4).
