# S00: Root Invariants

Topology-wide requirements every v3 subsystem inherits. These are the axioms every other spec leaf is allowed to assume. Leaves elsewhere in the tree may refine or specialize these invariants but may not contradict them. Reserved namespace: `S00.*` — no other leaf file may claim an ID in this range.

## Context

These invariants encode the v3 topology's non-negotiables: state on disk as authority, one orchestrator per role, spec leaves as the sole verification contract, scenarios retired, crash-only lifecycle, EARS shape mandated, and `dev-principles` as universal shared guidance. Most root invariants are authored as Ubiquitous EARS (no trigger, no precondition) because they hold in every operating mode. Two are not: `S00.s1` is State-driven because the crash-only lifecycle fires specifically on role transitions, and `S00.w1` is Optional-feature because `dev-principles` applies where an agent's work is shaped by structural/refactoring/correctness concerns. Per D27 the letter in each ID encodes the EARS pattern, so the mix at root scope is explicit rather than hidden. See `../decisions.md` D15, D17, D18, D22, D24, D25, and D27 for the rationale chain.

**Realized by:** `../architecture/root-topology.md` (A00.*), plus targeted realizations in every architecture subtree where the invariant is enforced mechanically.

## EARS requirements

### S00.u1 — State on disk as authority

`The dev-workflow orchestration topology shall treat on-disk artifacts under $MERIDIAN_WORK_DIR and $MERIDIAN_FS_DIR as the authoritative source of every orchestrator decision, and shall not resume any orchestrator hand-off from conversation-context memory alone.`

**Edge cases.**

- **Mid-session compaction mid-handoff.** Compaction truncates the in-context conversation but does not touch `$MERIDIAN_WORK_DIR`. The resuming orchestrator rehydrates from disk; no partial state is retained in memory.
- **Non-requirement: ephemeral reasoning.** An orchestrator's in-context reasoning between spawn boundaries may be held in conversation memory as long as every decision that outlives the spawn lands on disk before termination. Reasoning that never becomes an artifact is not a decision.

### S00.u2 — One active agent per role

`The dev-workflow orchestration topology shall at any time have at most one active instance per work item of dev-orch, design-orch, planning impl-orch, execution impl-orch, and @planner.`

**Edge cases.**

- **Planning → execution transition.** The planning impl-orch terminates before the execution impl-orch is spawned. There is never an interval where both are active against the same work item.
- **Redesign mid-cycle.** If dev-orch routes a redesign brief while a prior execution impl-orch has already terminated, design-orch is spawned fresh. The prior execution impl-orch does not resume; a later fresh spawn consumes the revised design.
- **Non-requirement: cross-work-item isolation.** Two different work items may each have their own dev-orch active simultaneously. The invariant is scoped per work item, not globally.

### S00.u3 — Spec leaves as sole acceptance contract

`The dev-workflow orchestration topology shall accept spec leaves under design/spec/ as the only authoritative record of acceptance criteria, and shall not consult any parallel verification ledger (including the retired scenarios/ convention) for phase or work-item closure.`

**Edge cases.**

- **Small work items.** A degenerate root-only spec tree (`spec/overview.md` + `root-invariants.md` only, no subtrees) is still the authoritative contract. The absence of depth does not demote the spec.
- **Trivial work items.** Trivial work (one-line fix, rename, doc typo) may skip the spec tree entirely per `S01.2` — in that case no spec leaves exist and nothing other than smoke-test evidence is consulted. "No spec" is legal; "spec plus sidecar scenarios" is not.

### S00.u4 — Scenarios convention retired

`The dev-workflow orchestration topology shall not produce, consume, reference, or gate any work-item artifact on a scenarios/ folder or scenario-ID nomenclature.`

**Edge cases.**

- **Legacy skill body.** Until the `dev-artifacts` skill body is updated per the coordinated skill-edit follow-up, agents may encounter stale scenarios language in skill load. The skill load is not authoritative against this invariant; agent body prompts under v3 route around the stale section.
- **Non-requirement: audit trails.** Historical `scenarios/` folders in prior work items remain in git history. This invariant governs new work; it is not a repo-wide deletion mandate.

### S00.s1 — Crash-only lifecycle across hand-offs

`While a work item transitions between orchestrator roles, the dev-workflow orchestration topology shall terminate the outgoing spawn, commit all relevant artifacts to disk, and resume in a fresh spawn that reads its inputs from disk.`

This invariant is State-driven: the precondition is "work item is transitioning between orchestrator roles," the response is the terminate-commit-resume sequence. It is the execution-time enforcement of S00.u1.

**Edge cases.**

- **Suspended-spawn is forbidden.** No orchestrator may "pause and resume" in a single long-lived spawn across a review checkpoint. D15 rejects this explicitly.
- **Within-role continuation.** A single execution impl-orch may run many phases within one spawn without terminating between them. The invariant fires on role transitions (planning → execution, execution → redesign, etc.), not on phase boundaries inside one role.

### S00.u6 — EARS shape mandated for all acceptance criteria

`The dev-workflow orchestration topology shall author every acceptance criterion in every spec leaf as one of the five EARS patterns (Ubiquitous, State-driven, Event-driven, Optional-feature, Complex) with a stable statement ID in the S<subsystem>.<section>.<letter><number> namespace.`

**Edge cases.**

- **Non-requirements are explicitly non-EARS.** A spec leaf may flag edge cases as "non-requirement with reasoning" instead of writing an EARS statement, per D17 + design-orch convergence rules. The reasoning must be explicit and falsifiable; bare "out of scope" is a convergence blocker (spec-reviewer enforcement).
- **Mechanical-parse escape valve.** A leaf that cannot be parsed into a trigger/precondition/response triple under its pattern is rejected back to design-orch with the note `cannot mechanically parse — requires design clarification`. The escape valve keeps EARS honest without fabricating interpretations. See D25 and `../architecture/verification/ears-parsing.md`.

### S00.w1 — `dev-principles` as universal shared guidance

`Where an agent's work is shaped by structural, refactoring, abstraction, or correctness concerns, the dev-workflow orchestration topology shall load the dev-principles skill for that agent as shared operating guidance rather than as a pass/fail checkpoint.`

This invariant is Optional-feature: the `where` fixture is "agent's work is shaped by structural/refactoring/abstraction/correctness concerns" — which matches @dev-orchestrator, @design-orchestrator, @impl-orchestrator, @planner, @coder, @reviewer, @refactor-reviewer, and @architect. Agents outside this set (e.g. @internet-researcher, @explorer, and documenter lanes that are pure content) are not covered and do not load the skill on this invariant.

**Edge cases.**

- **No binary gate.** No agent runs a `dev-principles` PASS/FAIL checkpoint. Findings route through normal reviewer loops. Design-orch convergence judges whether findings (including principle violations) are addressed, not whether a separate gate fires. See D24 (revised) for the rationale and `../architecture/principles/dev-principles-application.md` for the per-agent application shape.
- **Non-requirement: separate reviewer lane.** Final implementation review does not require a dedicated `dev-principles` reviewer lane. All reviewers already apply the principles as part of their rubric.
