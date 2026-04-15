# Spec Tree — Overview

## Purpose

This tree is the authoritative behavioral contract for the v3 dev-workflow orchestration topology. Leaves carry EARS-format acceptance criteria for every observable behavior the restructured dev-orchestrator, design-orchestrator, impl-orchestrator, and @planner must exhibit. Verification under v3 runs against these leaves — smoke testers parse each EARS statement into a trigger/precondition/response triple and execute against committed behavior. This overview is a strict TOC index: it lists every leaf with its ID and one-line summary, and contains no authoritative prose of its own. Root-level invariants that apply across every subsystem live in `root-invariants.md` (`S00.*`), not in this overview. See `../architecture/overview.md` for the companion technical tree that realizes these leaves.

## TOC

### `S00` — Root invariants (apply across every subsystem)

Location: [root-invariants.md](root-invariants.md). Leaves here carry the universal ubiquitous requirements every subsystem inherits.

- **S00.u1** — State on disk as authority: every orchestrator decision rests on on-disk artifacts, never conversation-context memory.
- **S00.u2** — One agent per role: exactly one active instance of dev-orch, design-orch, planning impl-orch, or execution impl-orch per work item at any time.
- **S00.u3** — Spec leaves authoritative: the spec tree is the only source of truth for acceptance criteria; no parallel scenario ledger exists.
- **S00.u4** — Scenarios retired: no `scenarios/` folder is produced or consumed anywhere in the v3 topology.
- **S00.s1** — Crash-only lifecycle: every orchestrator hand-off terminates a spawn and resumes in a fresh spawn reading state from disk.
- **S00.u6** — EARS shape mandated: every acceptance criterion in every spec leaf is one of the five EARS patterns with a stable statement ID.
- **S00.w1** — `dev-principles` universal: every agent whose work is shaped by structural, refactoring, abstraction, or correctness concerns loads `dev-principles` as shared operating guidance, not as a pass/fail gate.

### `S01` — Requirements and scoping (dev-orch captures intent)

Subsystem overview: [requirements-and-scoping/overview.md](requirements-and-scoping/overview.md).

- **S01.1** — User intent capture ([user-intent-capture.md](requirements-and-scoping/user-intent-capture.md)): conversational intent gathering and `requirements.md` production.
- **S01.2** — Problem-size scaling ([problem-size-scaling.md](requirements-and-scoping/problem-size-scaling.md)): the trivial/small/medium/large selector that chooses design depth.

### `S02` — Design production (design-orch produces the two-tree package)

Subsystem overview: [design-production/overview.md](design-production/overview.md).

- **S02.1** — Spec tree production ([spec-tree.md](design-production/spec-tree.md)): hierarchical `design/spec/` with EARS leaves, stable IDs, and root TOC, written spec-first from `requirements.md`.
- **S02.2** — Architecture tree production ([architecture-tree.md](design-production/architecture-tree.md)): hierarchical `design/architecture/` derived from the spec tree, with cross-links from every architecture leaf back to the spec leaves it realizes.
- **S02.3** — Refactors and feasibility as sibling artifacts ([refactors-and-feasibility.md](design-production/refactors-and-feasibility.md)): `design/refactors.md` rearrangement agenda and `design/feasibility.md` probe record, both first-class design outputs.
- **S02.4** — Design convergence ([convergence.md](design-production/convergence.md)): reviewer fan-out, structural-reviewer PASS requirement, `dev-principles` as a shared lens, and the convergence exit criteria.

### `S03` — Plan approval (dev-orch walks the user through the design and the plan)

Subsystem overview: [plan-approval/overview.md](plan-approval/overview.md).

- **S03.1** — Two-tree approval walk ([two-tree-walk.md](plan-approval/two-tree-walk.md)): walking `spec/overview.md` + `architecture/overview.md` + `refactors.md` with drill-down on demand.
- **S03.2** — Plan review checkpoint ([plan-review.md](plan-approval/plan-review.md)): the six-criterion plan review dev-orch applies after the planning impl-orch terminates.

### `S04` — Planning cycle (impl-orch owns pre-planning and the planner spawn)

Subsystem overview: [planning-cycle/overview.md](planning-cycle/overview.md).

- **S04.1** — Pre-planning step ([pre-planning.md](planning-cycle/pre-planning.md)): the six-step sequence that reads the design package, answers feasibility questions against runtime, and writes module-scoped constraints to `plan/pre-planning-notes.md`.
- **S04.2** — Planner spawn contract ([planner-spawn.md](planning-cycle/planner-spawn.md)): inputs, outputs, leaf-ownership-at-EARS-statement-granularity, Parallelism Posture, no-refactor-invention rule.
- **S04.3** — Planning cycle cap ([cycle-cap.md](planning-cycle/cycle-cap.md)): `K_fail=3` failed plans + `K_probe=2` probe-requests with structural-blocking short-circuit.
- **S04.4** — Pre-execution structural gate ([structural-gate.md](planning-cycle/structural-gate.md)): `Parallelism Posture: sequential` + `Cause: structural coupling preserved by design` fires a structural-blocking redesign brief before execution.

### `S05` — Execution cycle (execution impl-orch runs phases against the approved plan)

Subsystem overview: [execution-cycle/overview.md](execution-cycle/overview.md).

- **S05.1** — Phase loop ([phase-loop.md](execution-cycle/phase-loop.md)): the per-phase coder → tester → commit loop against the approved plan.
- **S05.2** — Spec-leaf verification framing ([spec-leaf-verification.md](execution-cycle/spec-leaf-verification.md)): phases claim EARS statement IDs and are verified by parsing each statement's triple.
- **S05.3** — Spec drift enforcement ([spec-drift.md](execution-cycle/spec-drift.md)): code may not land that satisfies behavior the spec does not describe; discovered drift routes through scoped revision or bail-out.
- **S05.4** — Escape hatch ([escape-hatch.md](execution-cycle/escape-hatch.md)): spec-leaf falsification at execution time fires a `redesign-brief.md`.
- **S05.5** — Preserved-phase re-verification ([preserved-reverification.md](execution-cycle/preserved-reverification.md)): preserved phases whose leaves were revised in place get a tester-only re-verification pass with three outcomes (D26).

### `S06` — Redesign cycle (dev-orch routes bail-outs autonomously)

Subsystem overview: [redesign-cycle/overview.md](redesign-cycle/overview.md).

- **S06.1** — Autonomous redesign loop ([autonomous-loop.md](redesign-cycle/autonomous-loop.md)): entry signals (execution falsification, structural-blocking, planning-blocked) route back to design-orch without user input.
- **S06.2** — Preservation hint production ([preservation-hint-production.md](redesign-cycle/preservation-hint-production.md)): dev-orch writes `plan/preservation-hint.md` between the revised design and the next planning impl-orch spawn.
- **S06.3** — Loop guards ([loop-guards.md](redesign-cycle/loop-guards.md)): `K=2` redesign cycle cap, new-evidence requirement, user-escalation on threshold.

## Reading order

- **@dev-orchestrator** reads `S00` → `S01` → `S03` → `S06` first. These are the subsystems dev-orch directly owns or participates in. `S02`, `S04`, and `S05` are loaded on demand when presenting to the user or routing a bail-out.
- **@design-orchestrator** reads `S00` → `S02` in full. `S01` frames what it consumes from dev-orch. The rest of the tree is context but not authoritative input.
- **@impl-orchestrator (planning role)** reads `S00` → `S04` in full. `S02` is consumed as input via the design package; `S03` explains how the plan it produces will be reviewed; `S06` explains how a redesign brief it emits will be routed.
- **@impl-orchestrator (execution role)** reads `S00` → `S05` in full. `S04` was run by a prior spawn; `S06` explains the redesign routing it escalates into.
- **@planner** reads `S00` → `S04.2` as its own contract; consults `S02.1`, `S02.2`, and `S02.3` to understand the design package inputs; and reads the rest on demand.
- **testers** read only the specific leaves their phase blueprint cites via EARS statement IDs; parsing rules are in `../architecture/verification/ears-parsing.md`.
