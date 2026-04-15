# Architecture Tree — Root Overview

## Purpose

This tree describes how the code realizes the spec tree's behavioral contracts. Every architecture leaf exists because some spec leaf motivates it, and every spec leaf is realized by at least one architecture leaf. The tree is **observational** — it describes the target system state as observations about how the code should be, not as prescriptions for phase ordering (phase ordering belongs to @planner reading `design/refactors.md` + `design/feasibility.md`, per S02.2.u2). This overview is a strict TOC; substantive content lives in the leaf files, including root-scope topology which lives in `root-topology.md` under the reserved `A00.*` namespace (never in this overview's prose per S02.2.s1).

## TOC

- **A00** — Root topology ([root-topology.md](root-topology.md)): import-DAG slice, integration boundaries, current vs target posture that feeds `design/refactors.md`, the state-on-disk axiom, orchestrator count, and the spec-vs-architecture altitude asymmetry.
- **A01** — Design package ([design-package/overview.md](design-package/overview.md)): two-tree shape (spec tree + architecture tree + refactors.md + feasibility.md), overview-TOC discipline, root-scope leaves in reserved namespace. Subtree realizes S02.1, S02.2.
- **A02** — Artifact contracts ([artifact-contracts/overview.md](artifact-contracts/overview.md)): terrain analysis output format (refactors.md shape + feasibility.md shape), shared work artifacts layout (`scenarios/` retirement, spec-leaf ownership files), preservation hint + redesign brief formats. Subtree realizes S00.u4, S02.3, S06.2.
- **A03** — Verification ([verification/overview.md](verification/overview.md)): orchestrator verification contract (spec leaves as acceptance contract, scenarios convention retired), leaf-ownership-and-tester-flow at EARS-statement granularity, EARS per-pattern parsing rules the tester applies mechanically. Subtree realizes S00.u6, S05.1, S05.2, S05.3.
- **A04** — Orchestrator topology ([orchestrator-topology/overview.md](orchestrator-topology/overview.md)): design-phase authoring flow, planning-and-review loop, execution loop with phase-coder + tester flow, autonomous redesign loop with K=2 guard. Subtree realizes S01, S02.4, S03, S04, S05, S06.
- **A05** — Principles ([principles/overview.md](principles/overview.md)): dev-principles as shared context loaded by every agent — design-orch during convergence, @planner during decomposition, execution impl-orch across the final review fan-out — with no per-agent pass/fail gate. Subtree realizes S00.w1, S02.4.w1.

## Reading order

Start at A00 for the root topology and the state-on-disk axiom. Then A01 for the design package shape, A02 for the artifact contracts each agent emits or consumes, A03 for how phase verification is wired to EARS statements, A04 for the full orchestrator flow, and A05 for the principles lens every agent shares. Cross-links from every subtree point back at the spec leaves they realize; cross-links from every spec leaf point at the architecture leaves that realize it, per S02.2.e2 bi-directional cross-link coverage.
