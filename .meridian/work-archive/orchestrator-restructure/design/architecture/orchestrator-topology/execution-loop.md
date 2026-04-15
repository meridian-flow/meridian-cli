# A04.2: Execution loop

## Summary

Execution impl-orch is a fresh spawn that reads the approved plan from disk, runs each phase through a coder-then-tester sequence, fans out parallel rounds per `plan/overview.md`, commits after each phase, logs live decisions in `decisions.md`, routes falsifications through the escape hatch, and runs one end-to-end review loop across all phases at the tail. It inherits no conversation state from the planning impl-orch; every runtime artifact it needs lives on disk.

## Realizes

- `../../spec/execution-cycle/phase-loop.md` — S05.1.u1 (fresh spawn), S05.1.u2 (skips pre-planning), S05.1.e1 (per-phase sequence), S05.1.e2 (parallel-round fanout), S05.1.e3 (per-phase commit), S05.1.c2 (live decision log), S05.1.s2 (adaptation allowed, spec deviation forbidden), S05.1.s3 (architecture deviation with decision log), S05.1.s4 (`dev-principles` across final review fan-out), S05.1.w1 (final review loop).
- `../../spec/execution-cycle/spec-leaf-verification.md` — S05.2.u1 (spec leaves verification contract), S05.2.s1 (tester may execute additional edge-case tests beyond the claimed leaves), S05.2.s2 (phase passes when every claimed statement verifies), S05.2.s3 (no TDD — coders do not write tests before implementing), S05.2.w1 (tester-generated edge cases mandatory).
- `../../spec/execution-cycle/spec-drift.md` — S05.3.u1 (spec leaves authoritative), S05.3.e1 (coder silent workarounds forbidden), S05.3.e2 (discovered edge cases route through channel), S05.3.s2 ("code does not yet satisfy" is not falsification), S05.3.s3 (epistemic trigger), S05.3.c2 (spec revision precedes code workaround), S05.3.w1 (revised spec leaf triggers re-verification, not re-implementation by default).
- `../../spec/execution-cycle/escape-hatch.md` — S05.4.u1 (two arms), S05.4.e1 (execution-time bail-out), S05.4.s1 (justification burden), S05.4.s2 (bail-out categories that are NOT warranted), S05.4.s4 (final review interaction rare), S05.4.c2 (duplicate briefs are rejected), S05.4.w1 (planning-time brief uses the Parallelism-blocking section).
- `../../spec/execution-cycle/preserved-reverification.md` — S05.5.u1 (zero revised leaves skips pass), S05.5.s1 (re-verification runs before replanned/new phases), S05.5.s2 (one spawn per phase), S05.5.e2 (outcome 1: all revised leaves still verify → stay preserved), S05.5.e3 (outcome 2: some revised leaves falsify → promote to partially-invalidated), S05.5.e4 (outcome 3: re-verification cannot execute → promote to replanned), S05.5.w1 (leaf IDs are stable across in-place revision).

## Current state

- v2 impl-orch opens each phase with a "scenario review → coder → testers" loop (`meridian-dev-workflow/agents/impl-orchestrator.md`), gates phase closure on scenario-file results, and holds all run-time context in a single impl-orch conversation for the entire work item.
- v2 has no explicit terminated-spawn boundary between planning and execution — the same impl-orch conversation runs both. That makes the execution loop reliant on conversation state that the crash-only axiom says should live on disk.
- v2 has no preservation hint consumption step because the v2 redesign-cycle contract is implicit.

## Target state

### Fresh execution impl-orch spawn

dev-orch spawns execution impl-orch after plan-review approves the plan (S03.2.c1). The spawn is a completely fresh conversation — no `--from` link to the planning impl-orch, no inherited conversation state. The execution impl-orch reads:

- `requirements.md`
- `design/spec/` tree + `design/architecture/` tree + `design/refactors.md` + `design/feasibility.md`
- `plan/overview.md`, `plan/phase-N-*.md` blueprints, `plan/leaf-ownership.md`, `plan/status.md`
- `plan/pre-planning-notes.md` (for runtime constraints the planning impl-orch discovered)
- `plan/preservation-hint.md` (on redesign cycles only)
- `decisions.md` (to pick up any decisions carried from design or prior cycles)

Execution impl-orch does not re-run pre-planning (S05.1.u2). Pre-planning work was already done and committed to disk by the planning impl-orch; re-running it would waste a full context window and would risk divergence from the plan dev-orch already approved.

### Preserved-phase re-verification pass (redesign cycles only)

If `plan/preservation-hint.md` exists and at least one preserved phase has a `Revised leaves?` column naming an EARS statement ID, execution impl-orch runs a tester-only re-verification pass before starting any replanned or new phase (S05.5.s1). For each such phase, impl-orch:

1. Spawns a tester (one spawn per phase per S05.5.s2) with the phase's commit SHA, the revised EARS statement IDs, and the spec leaves hosting those statements.
2. Tester parses each revised statement per A03.3 and executes against the already-committed code.
3. Three outcomes per S05.5.e2/e3/e4:
   - **All revised statements verify** → phase promotes to `preserved` (no further work).
   - **At least one revised statement falsifies** → phase promotes to `partially-invalidated`, execution impl-orch respawns the coder for that phase with the partial-invalidation scope.
   - **Tester reports unparseable** → phase promotes to `replanned`, execution impl-orch routes to design-orch via the spec-drift channel (S05.3.s3).

Preserved phases with zero revised leaves skip the pass entirely (S05.5.u1).

### Per-phase coder-then-tester sequence

For each phase in the current parallel round, execution impl-orch runs the following sequence (S05.1.e1):

1. **Spawn coder.** Attach the phase blueprint, relevant source files, relevant spec leaves for claimed EARS statements, `decisions.md`, `plan/leaf-ownership.md`, `design/architecture/` leaves the phase touches. The coder implements the phase.
2. **Spawn testers.** Determined by the phase blueprint's tester lane (`verifier`, `smoke-tester`, `unit-tester`, `browser-tester`, or combinations). Each tester receives the spec leaves for claimed EARS statements, the phase blueprint, and `plan/leaf-ownership.md`. Testers run in parallel when lanes are independent.
3. **Tester report processing.** For each claimed EARS statement ID, the tester returns `verified`, `falsified`, `unparseable`, or `blocked`. Execution impl-orch updates `plan/leaf-ownership.md` rows accordingly.
4. **Phase closure.** Phase passes when every claimed EARS statement verifies (S05.2.s2). If any falsify, route through the spec-drift/escape-hatch channel. If any unparseable, route to design-orch for clarification.
5. **Commit.** On pass, impl-orch commits the phase's changes in a single commit per S05.1.e3. Commit message names the phase ID, the claimed EARS statements, and the tester evidence pointer.

### Parallel-round fanout

`plan/overview.md` defines rounds and round-to-phase membership. Execution impl-orch runs each round's phases in parallel when the round is `parallel` or `limited`, and sequentially within a `sequential` round (S05.1.e2). Rounds themselves run sequentially — a `Round 2` phase does not start until every `Round 1` phase has committed.

Parallel fanout uses native background spawns: each phase is a separate coder spawn, each spawn runs independently, and impl-orch waits for the round to fully converge before advancing. If any phase in the round fails, the round is not complete and impl-orch routes through the escape hatch for the failing phase before deciding whether the remaining phases need re-execution.

### Adaptation vs spec deviation

Execution impl-orch is allowed to adapt the plan mid-execution for runtime reasons — a missing import that requires a scoped fix, a refactor that lands in a slightly different shape than the blueprint described, a fixture dependency the planner did not anticipate. These adaptations are recorded in `decisions.md` (S05.1.c2) and do not block the phase.

Execution impl-orch is **not** allowed to deviate from a spec leaf's EARS statement (S05.1.s2). If the code cannot satisfy a claimed statement, the statement is falsified, not adapted-around. Falsification routes through the escape hatch:

- **Spec revision precedes code workaround.** If the code cannot satisfy the statement and the statement is wrong, the correct action is to route to design-orch to revise the statement. Silent workarounds that leave the code passing a test the spec did not ask for are forbidden (S05.3.e1).
- **Epistemic trigger.** Falsification fires on any evidence contradicting any part of the statement, not just severe or high-impact contradictions (S05.3.s3). A tester-generated edge case that reveals a false assumption is a falsification, even if the happy-path test passed.

Architecture leaves are observational and may be deviated from with a decision-log entry naming the reason (S05.1.s3). This is the load-bearing altitude asymmetry from A00.3 — spec is contract, architecture is observation.

### Escape hatch (execution-time arm)

When execution impl-orch bails out of the current work, it writes `redesign-brief.md` per S05.4.e1 and terminates with a bail-out terminal report. The brief names:

- Cycle number and entry signal (`execution-time`).
- Falsified spec leaves with evidence.
- Preservation section (impl-orch's first-pass phase classification).
- Constraints that still hold.
- Requested action (`design-revision` by default; `scope-fix` when impl-orch is confident the existing design is correct and only the scope changed).
- Parallelism-blocking section (conditional, present only when the entry signal is structural-blocking per S05.4.w1).

Bail-out terminates the execution impl-orch spawn; dev-orch reads the brief and routes per A04.3.

### Final end-to-end review loop

After every phase in every round has passed phase-level testing and committed (S05.1.w1), execution impl-orch runs one end-to-end review loop before terminating with a completion terminal report:

1. Spawn @reviewer fan-out across diverse model families, each with a different focus area: design alignment, cross-phase drift, refactor-reviewer for structural debt, integration-boundary coverage where applicable.
2. Reviewers read the full work item's committed state plus `design/` and `decisions.md`. `dev-principles` is loaded universally as shared context; reviewers apply the principles as judgment context, not as a binary gate (S05.1.s4, A05 revised D24).
3. Coders address review findings; testers re-run where needed; reviewers re-run until convergence.
4. On convergence, execution impl-orch emits a completion terminal report naming the final commit SHA, the fully verified `plan/leaf-ownership.md`, and any open decisions that need user attention.

Escape-hatch interaction with the final review loop is rare (S05.4.s4): the final review loop usually surfaces findings that can be addressed by coders with small scoped changes, not by redesign. If a final-review finding reveals a structural-blocking gap the design did not cover, impl-orch may bail to design-orch, but this should be unusual — the plan-review checkpoint was supposed to catch structural issues earlier.

### Live decision log

Every non-trivial execution-time decision lands in `decisions.md` as it happens (S05.1.c2), not retroactively:

- Adaptations to the plan that affect future phases.
- Rejected review findings with reasoning.
- Architecture-leaf deviations with the observed runtime reason.
- Coder judgment calls on ambiguous blueprint instructions.
- Refactor sizing or ordering changes.

The live log exists because conversation state evaporates on compaction — the reasoning for a mid-execution call is freshest at the moment of the call, and retroactive logs flatten into post-hoc justification.

## Interfaces

- **`meridian spawn -a impl-orchestrator -f plan/... -f design/...`** — dev-orch spawns fresh execution impl-orch.
- **`meridian spawn -a coder`, `-a verifier`, `-a smoke-tester`, `-a reviewer`** — per-phase spawns that execution impl-orch fans out.
- **`plan/status.md`** — execution impl-orch updates phase status as rounds progress.
- **`plan/leaf-ownership.md`** — updated per EARS statement as testers report.
- **`decisions.md`** — live decision log, append-only.
- **`redesign-brief.md`** — written on bail-out per S05.4.e1.

## Dependencies

- `./planning-and-review-loop.md` — produces the plan that this loop consumes.
- `./redesign-loop.md` — the dev-orch loop that receives bail-out briefs.
- `../verification/leaf-ownership-and-tester-flow.md` — the ledger this loop updates.
- `../verification/ears-parsing.md` — the parsing rule testers apply.
- `../principles/dev-principles-application.md` — shared context loaded by every agent in the fan-out.

## Open questions

None at the architecture level.
