# S02: Design Production — Subsystem Overview

## Purpose

This subsystem covers @design-orchestrator's production of the four-artifact v3 design package: `design/spec/` (hierarchical spec tree with EARS leaves), `design/architecture/` (hierarchical architecture tree derived from spec), `design/refactors.md` (refactor agenda for @planner), and `design/feasibility.md` (gap-finding probe record). The subsystem has one actor — @design-orchestrator — and four artifact outputs consumed by @planner, impl-orch, and dev-orch. This overview is a strict TOC; substantive EARS requirements live in the leaf files.

## TOC

- **S02.1** — Spec tree production ([spec-tree.md](spec-tree.md)): hierarchical `design/spec/` with EARS leaves, stable statement IDs, root TOC overview, spec-first ordering, and root-invariants placement in leaves (`S00.*`, never in prose).
- **S02.2** — Architecture tree production ([architecture-tree.md](architecture-tree.md)): hierarchical `design/architecture/` derived from the spec tree, cross-link coverage (every architecture leaf realizes ≥1 spec leaf, every spec leaf is realized by ≥1 architecture leaf), and root-topology placement in leaves (`A00.*`, never in prose).
- **S02.3** — Refactors and feasibility as sibling artifacts ([refactors-and-feasibility.md](refactors-and-feasibility.md)): the canonical per-entry shapes in `refactors.md` and `feasibility.md`, the rearrangement-vs-foundational-prep split, and the design-orch single-author rule.
- **S02.4** — Design convergence ([convergence.md](convergence.md)): reviewer fan-out across diverse models, structural-reviewer PASS requirement, `dev-principles` as a shared lens (not a gate), and the convergence exit criteria that let dev-orch take the design package to approval walk.

## Reading order

Read S02.1 first — the spec-first ordering rule is load-bearing for every downstream leaf in this subsystem. Then S02.2 (architecture derived from spec). Then S02.3 (sibling artifacts), then S02.4 (convergence over all of the above). @planner consumes the outputs of S02.1, S02.2, and S02.3 as `-f` inputs per S04.2. The corresponding architecture content lives in `../../architecture/design-package/` (A01) and `../../architecture/orchestrator-topology/design-phase.md` (A04.4).
