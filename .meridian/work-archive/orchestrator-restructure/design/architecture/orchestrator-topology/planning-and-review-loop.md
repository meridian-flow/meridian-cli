# A04.1: Planning and review loop

## Summary

Planning impl-orch is the sole caller of @planner. It runs pre-planning in its own context, writes `plan/pre-planning-notes.md`, spawns @planner, enforces the pre-execution structural gate, terminates with a plan-ready report, and hands off to dev-orch for the plan-review checkpoint. On approval, dev-orch spawns a fresh execution impl-orch that reads the committed plan from disk without inheriting any conversation state from the planning cycle. This terminated-spawn model is load-bearing for Meridian's crash-only posture — a suspended impl-orch holding plan state in conversation would violate the state-on-disk axiom.

## Realizes

- `../../spec/planning-cycle/pre-planning.md` — S04.1.u1 (pre-planning in own context), S04.1.u2 (notes materialize to disk), S04.1.e1 (six-step sequence), S04.1.e2 (six required note sections), S04.1.s1 (no "phase" word), S04.1.s2 (preservation-hint scoping on redesign cycles), S04.1.s3 (no re-running of probes `feasibility.md` already answered), S04.1.w1 (cluster hypothesis above the leaf-count threshold), S04.1.c1 (must answer impl-orch-tagged known unknowns).
- `../../spec/planning-cycle/planner-spawn.md` — S04.2.u1 (impl-orch is sole @planner caller), S04.2.u2 (single-shot planner), S04.2.e1 (full `-f` input set), S04.2.e2 (four artifact files), S04.2.e3 (no-refactor-invention rule — @planner may not author new refactor entries), S04.2.e4 (every refactor entry accounted in the plan), S04.2.s1 (three terminal shapes), S04.2.s3 (pre-planning-notes as projection, not runtime ground truth), S04.2.c1 (planner may not silently guess on missing runtime context), S04.2.c2 (probe-request routes through impl-orch), S04.2.w1 (preservation hint is an additional `-f` on redesign cycles).
- `../../spec/planning-cycle/cycle-cap.md` — S04.3.u1 (two counters plus short-circuit), S04.3.e1 (K_fail advances on failed-plan terminations), S04.3.e2 (K_probe advances on probe-request terminations), S04.3.e3 (structural-blocking short-circuit advances neither counter), S04.3.e4 (conflicting signals — structural-blocking wins), S04.3.s1 (exits from the planning loop are exactly four shapes), S04.3.s2 (counters are independent, not a shared budget), S04.3.s3 (cap exhaustion emits `planning-blocked` terminal report), S04.3.s4 (probe-request loop reports Cause `probe-request loop`), S04.3.w1 (planning cap is distinct from redesign cap).
- `../../spec/planning-cycle/structural-gate.md` — S04.4.u1 (fires on `sequential + structural coupling preserved by design`), S04.4.e1 (halts before execution and plan-review), S04.4.e2 (planning-time redesign brief contents), S04.4.e3 (terminal report carries the brief reference), S04.4.s1 (gate distinguishes design problem from planner failure), S04.4.c1 (plan without Parallelism Posture fails the gate indirectly), S04.4.w1 (foundational-prep variant).
- `../../spec/plan-approval/two-tree-walk.md` — S03.1.u1 (walk artifacts are the two root overviews plus refactors.md), S03.1.u2 (`feasibility.md` is on-demand, not default), S03.1.e1 (walk sequence is behavior then structure then cost), S03.1.s1 (drill-down is on demand, not exhaustive), S03.1.s3 (small work item collapses walk to single-file shape), S03.1.c2 (pushback on a leaf routes through design-orch, not inline edit), S03.1.w1 (approval is a dev-orch → execution handoff).
- `../../spec/plan-approval/plan-review.md` — S03.2.u1 (six-criterion judgment), S03.2.e1 (Parallelism Posture named and justified), S03.2.e2 (per-round justifications cite real constraints), S03.2.e3 (refactors agenda fully accounted), S03.2.e5 (Mermaid fanout matches textual rounds), S03.2.e6 (plan must not contradict user-stated intent), S03.2.s2 (pushback does not advance redesign counter), S03.2.c1 (approval handoff spawns fresh execution impl-orch), S03.2.c2 (pushback spawns fresh planning impl-orch), S03.2.w1 (small-tier plan skips user involvement).

## Current state

- v2 topology routes planning through dev-orch directly. `meridian-dev-workflow/agents/dev-orchestrator.md` has a dedicated Planning Phase that spawns @planner as a dev-orch child; `meridian-dev-workflow/agents/impl-orchestrator.md` begins with the per-phase execution loop and has no pre-planning artifact or planner spawn; `meridian-dev-workflow/agents/planner.md` describes itself as a direct dev-orch → execution bridge.
- Impl-orch has no runtime-observation phase before plan decomposition; runtime constraints and fixture races surface only after execution starts, which is the stale-plan coupling D1, D3, D12, and D15 were written to break.
- Plan-review is conflated with the spawn that produced the plan — the same impl-orch conversation holds both the plan draft and the review feedback, which makes it impossible to terminate between draft and review without losing context.

## Target state

**Anchor target for R06.** `design/refactors.md` entry R06 (rewire planning so impl-orch owns pre-planning and the planner spawn) names this section as its `Architecture anchor`. The R06 migration is done when the v2 dev-orch → planner → impl-orch chain is replaced with the v3 chain described below, no agent body still instructs dev-orch to spawn @planner directly, and the planning impl-orch → dev-orch → fresh execution impl-orch handoff terminates the planning spawn explicitly.

### Impl-orch-owned planning boundary

The v3 planning chain is:

1. **dev-orch spawns planning impl-orch.** The planning impl-orch receives the design package (`design/spec/`, `design/architecture/`, `design/refactors.md`, `design/feasibility.md`), `requirements.md`, and (on redesign cycles only) `plan/preservation-hint.md`. The spawn is tagged as planning-only in its prompt so the impl-orch knows not to attempt execution.
2. **Planning impl-orch runs pre-planning in its own context.** Six-step sequence per S04.1.e1:
   1. Read `design/spec/overview.md` (root TOC) to map every spec leaf in the design.
   2. Read `design/architecture/overview.md` (root TOC) to map every architecture leaf.
   3. Read `design/refactors.md` end-to-end (every R0N entry, all nine fields).
   4. Read `design/feasibility.md` end-to-end (Probe records, Fix-or-preserve, Assumption validations, Open questions, optional Foundational prep, optional Parallel-cluster hypothesis).
   5. Read `plan/preservation-hint.md` on redesign cycles — the replan-from-phase anchor, the preserved leaf claims, the constraints-that-still-hold.
   6. Apply `feasibility-questions` against the design, answering tagged known unknowns and noting any gaps the design did not cover.
3. **Planning impl-orch writes `plan/pre-planning-notes.md`.** Six required sections per S04.1.e2: Feasibility answers, Probe results, Architecture re-interpretation, Module-scoped constraints, Spec-leaf coverage hypothesis, Probe gaps. The word "phase" is forbidden in these notes because pre-planning runs before @planner assigns phase identities.
4. **Planning impl-orch spawns @planner.** Single-shot spawn with `-f` attachments: the design package root overviews, refactors.md, feasibility.md, pre-planning-notes.md, preservation-hint.md (on redesign cycles), and the blueprint template from the `planning` skill. @planner returns one of three terminal shapes (S04.2.s1): plan-ready (four artifact files written), probe-request (specific runtime question requiring impl-orch resolution), or structural-blocking (design cannot decompose as given, escalate to design-orch).
5. **Planning impl-orch handles @planner outcomes.**
   - **plan-ready:** impl-orch enforces the pre-execution structural gate (S04.4). If `plan/overview.md` carries `Parallelism Posture: sequential` with `Cause: structural coupling preserved by design`, the gate fires and impl-orch emits a structural-blocking terminal report pointing at the brief — neither the K_fail nor K_probe counter advances (S04.4.s1). Otherwise the structural gate does not fire and impl-orch proceeds to step 6.
   - **probe-request:** impl-orch runs the requested probes, appends results to `plan/pre-planning-notes.md`, increments K_probe (S04.3.e2), and re-spawns @planner. If K_probe is exhausted, impl-orch emits an exhaustion terminal report (S04.3.s3) and terminates without executing.
   - **structural-blocking from @planner:** impl-orch emits a structural-blocking terminal report that short-circuits both counters (S04.3.e3) and routes to dev-orch for redesign.
6. **Planning impl-orch terminates with plan-ready report.** The report names the plan artifact paths (`plan/overview.md`, `plan/phase-N-*.md`, `plan/leaf-ownership.md`, `plan/status.md`) and terminates the planning impl-orch spawn. No part of the plan lives in conversation after this point; everything is on disk.
7. **dev-orch runs plan-review checkpoint.** Reads the design-tree TOC walk (`design/spec/overview.md` + `design/architecture/overview.md` + `design/refactors.md`), then `plan/overview.md` for the Parallelism Posture + rounds + justifications + refactor-handling table + Mermaid fanout. Drill-down into individual phase blueprints is on demand. Six-criterion judgment per S03.2.u1: (1) Parallelism Posture is named, (2) per-round justifications cite real constraints, (3) refactors agenda is fully accounted, (4) spec-leaf coverage is complete and exclusive at EARS-statement granularity, (5) Mermaid fanout matches the round list, (6) plan does not contradict user intent.
8. **On pushback**, dev-orch spawns a fresh planning impl-orch with the pushback notes attached. This does not advance the redesign cycle counter per S06.3.u2 (plan pushback is a mid-design-cycle correction, not a redesign signal). The fresh planning impl-orch loads the same design package, reads the pushback notes, re-runs pre-planning (or just the delta if the pushback is scoped), and re-spawns @planner.
9. **On approval**, dev-orch spawns a fresh execution impl-orch per S03.2.c1. The execution impl-orch reads `plan/overview.md`, `plan/phase-N-*.md`, `plan/leaf-ownership.md`, `plan/status.md`, and `plan/pre-planning-notes.md` from disk — it does not inherit conversation state from the planning impl-orch, and it does not re-run pre-planning.

### Terminated-spawn contract

The termination boundary between planning impl-orch and execution impl-orch is the load-bearing element of this loop. It is not a stylistic choice:

- **Crash-only discipline.** Meridian's state-on-disk axiom means any agent holding load-bearing state in conversation is one crash away from silent data loss. A suspended planning impl-orch waiting on plan-review would violate this rule: its runtime context (pre-planning observations, probe answers, @planner interaction history) would live only in conversation until plan-review resumed it.
- **Cache-miss mitigation.** A suspended spawn waiting on user review can live outside the 5-minute cache TTL, forcing a full context re-read on resume. Terminated spawns have no such cost — the fresh spawn reads only the on-disk artifacts it needs.
- **Review isolation.** dev-orch's plan-review is a fresh read of committed artifacts, not a conversation handoff. This prevents plan-review bias from conversation state ("but we already discussed this in planning!") and forces every decision to exist in writing on disk.
- **Re-spawn cheapness.** If plan-review rejects the plan, the fresh planning impl-orch pays only the cost of re-reading the design package and pre-planning notes, not the cost of resuming a stale conversation. Because the planning notes are on disk, the re-spawn can skip steps 1-5 and re-start at step 4 (re-spawning @planner with updated notes), as long as the pushback does not invalidate any pre-planning observations.

### Cycle caps at the planning boundary

Two counters guard the planning loop against infinite iteration (S04.3):

- **K_fail = 3** advances on every @planner spawn that returns a rejected plan (either plan-review rejects it or the plan itself is malformed). Exhausted K_fail means the planning impl-orch emits a planning-blocked terminal report and routes to dev-orch for a redesign cycle.
- **K_probe = 2** advances on every @planner probe-request. Exhausted K_probe means the planning impl-orch emits a probe-request-loop terminal report with `Cause: probe-request loop` and routes to dev-orch.
- **Structural-blocking short-circuit** bypasses both counters. A structural-blocking signal — either from @planner (step 5) or from the pre-execution gate (step 6) — terminates the planning loop immediately and routes to dev-orch for a redesign cycle without consuming a cap slot.

Conflicting signals resolve to structural-blocking (S04.3.e4): if @planner returns a plan that passes K_fail-check but fires the structural gate, the gate wins.

## Interfaces

- **`meridian spawn -a impl-orchestrator -f design/... -f requirements.md`** — dev-orch spawns planning impl-orch with the design package attached.
- **`meridian spawn -a planner -f design/... -f plan/pre-planning-notes.md`** — planning impl-orch spawns @planner with the full input set.
- **`meridian spawn report create --stdin`** — planning impl-orch emits plan-ready / probe-request / structural-blocking / planning-blocked terminal report.
- **`plan/pre-planning-notes.md`** — impl-orch's on-disk record of runtime observations, consumed by @planner and by the fresh execution impl-orch.
- **`plan/overview.md`** — @planner's on-disk plan index, consumed by dev-orch at plan-review and by execution impl-orch.

## Dependencies

- `./execution-loop.md` — the fresh execution impl-orch that runs after plan approval.
- `./redesign-loop.md` — the dev-orch loop that receives planning-blocked and structural-blocking reports.
- `../artifact-contracts/shared-work-artifacts.md` — the `plan/` layout this loop writes and reads.
- `../verification/leaf-ownership-and-tester-flow.md` — the `leaf-ownership.md` claims @planner emits.

## Open questions

None at the architecture level.
