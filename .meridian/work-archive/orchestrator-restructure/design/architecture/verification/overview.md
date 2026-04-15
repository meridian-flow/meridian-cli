# A03: Verification — Subsystem Overview

## Purpose

This subsystem describes how phase verification is wired to spec leaves. Every phase closes when its claimed EARS statements verify against the code the phase lands; the verification contract is owned by spec leaves, not by any sidecar scenario file. This overview is a strict TOC; substantive content lives in the leaves.

## TOC

- **A03.1** — Orchestrator verification contract ([orchestrator-verification-contract.md](orchestrator-verification-contract.md)): how dev-orch, design-orch, impl-orch, @planner, and testers share one verification contract anchored in spec leaves, with the v2 `scenarios/` folder retired. Contains the R04 anchor target.
- **A03.2** — Leaf ownership and tester flow ([leaf-ownership-and-tester-flow.md](leaf-ownership-and-tester-flow.md)): per-row shape of `plan/leaf-ownership.md` at EARS-statement granularity, tester handoff for claimed statements, evidence-pointer conventions, revised-annotation propagation. Contains the R05 anchor target.
- **A03.3** — EARS per-pattern parsing ([ears-parsing.md](ears-parsing.md)): the mechanical parsing rule testers apply to turn EARS statements into test setup + fixture + assertion, covering Ubiquitous, State-driven, Event-driven, Optional-feature, and Complex patterns, plus the "cannot mechanically parse" escape valve.

## Reading order

Read A03.1 first for the shared contract that motivates the other two leaves. Then A03.2 for the on-disk ownership artifact every tester consumes. Then A03.3 for the per-pattern parsing table that turns an EARS statement into a concrete test. Cross-links point back to the spec-side rules in S00.u3, S00.u4, S00.u6, S05.1, S05.2, S05.3.
