# A04: Orchestrator Topology — Subsystem Overview

## Purpose

This subsystem describes the three-orchestrator topology observationally — who spawns whom, which handoffs terminate a spawn and respawn a fresh one, and how the design, planning, execution, and redesign loops connect. This overview is a strict TOC; substantive content lives in the leaves.

## TOC

- **A04.1** — Planning and review loop ([planning-and-review-loop.md](planning-and-review-loop.md)): planning impl-orch ownership, six-step pre-planning sequence, @planner spawn, structural gate, terminated-spawn plan-review handoff to dev-orch, fresh execution impl-orch spawn on approval. Contains the R06 anchor target.
- **A04.2** — Execution loop ([execution-loop.md](execution-loop.md)): fresh execution impl-orch lifecycle, per-phase coder-then-tester sequence, parallel-round fanout, per-phase commit, live decision log, escape-hatch routing on falsification, final end-to-end review loop.
- **A04.3** — Redesign loop ([redesign-loop.md](redesign-loop.md)): dev-orch autonomous routing of bail-outs, design-problem vs scope-problem classification, K=2 cycle counter with user escalation on the third bail-out, duplicate-evidence rejection, preservation hint production handoff.
- **A04.4** — Design phase ([design-phase.md](design-phase.md)): design-orch spawn lifecycle, spec-first ordering within the design cycle, architecture tree derivation, refactors.md + feasibility.md authoring, structural reviewer requirement, @internet-researcher and @architect delegation patterns, convergence through scoped @reviewer fan-out.

## Reading order

Read A04.1 first because it owns the terminated-spawn handoff that every other loop depends on. Then A04.2 for the execution-time flow. Then A04.3 for how falsifications route back to design. Then A04.4 for how design-orch fills its cycle. Cross-links point back at the spec leaves in S01, S02.4, S03, S04, S05, and S06 that each loop realizes.
