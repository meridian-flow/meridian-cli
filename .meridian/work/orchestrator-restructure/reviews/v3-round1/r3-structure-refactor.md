# Review — v3 Structure, Modularity, Refactor Discipline

You are reviewing the **v3 orchestrator-restructure design package** for structural health of the design itself and of the target system the design describes. Your focus is **modularity, refactor discipline, and structural navigability** — the same concerns the `refactor-reviewer` agent carries at design time.

## What you're reviewing

Two structural axes:

1. **Structural health of the design package.** Is every doc doing one thing? Are concerns distributed cleanly? Is there duplication across docs that would erode over time? Is the navigation order obvious to an agent reading the package fresh?
2. **Structural posture the design commits to.** Does `design/architecture/` describe a target that is actually more modular than the current state? Does `design/refactors.md` name the specific rearrangements needed to reach that target? Is the refactor agenda honest (driven by coupling evidence) or aspirational (driven by vibes)?

## What to read

In this order:

1. `$MERIDIAN_WORK_DIR/design/overview.md` — entry-point narrative
2. `$MERIDIAN_WORK_DIR/design/design-orchestrator.md` — how refactors are produced
3. `$MERIDIAN_WORK_DIR/design/terrain-contract.md` — the contract for `refactors.md` and `feasibility.md`
4. `$MERIDIAN_WORK_DIR/design/planner.md` — how refactors are consumed
5. `$MERIDIAN_WORK_DIR/design/impl-orchestrator.md` — pre-execution structural gate
6. `$MERIDIAN_WORK_DIR/decisions.md` D10, D11, D13, D19, D20 — the decisions that carry structural intent

## Questions to answer

1. **Design-package navigability.** Is the doc order obvious to a resuming agent? Does `design/overview.md` actually serve as a root index with one-line summaries of every other doc, or is it a second-tier overview that requires reading sibling docs to understand? Flag any doc that has no clear entry point from overview.md.
2. **Concern separation.** Each doc should cover one concept fully. Flag any doc that mixes concerns — e.g. a doc that describes both "how the agent works" and "what artifact format it produces" should probably be two docs. Flag any doc that duplicates substance from another (as opposed to legitimately referencing it).
3. **Refactor discipline in the contract.** Read `terrain-contract.md` §"`design/refactors.md` — required shape" and check that the per-entry fields (target, affected callers, coupling removed, must-land-before, architecture anchor, behavior-preservation flag, evidence) actually prevent vibes-based refactor entries. Is there any field that could be filled with hand-waving? Any field missing that would let a refactor slip through without evidence?
4. **Refactors vs foundational prep distinction.** D19/D20 and `terrain-contract.md` §"Refactors vs foundational prep" distinguish rearrangement (lives in `refactors.md`) from creation (lives in `feasibility.md`). Is the distinction clean in prose? Test: take five hypothetical changes ("split a module", "add a new shared helper", "rename an interface", "introduce a new type contract", "extract a duplicated function") and classify each. Does the contract give an unambiguous answer for each?
5. **Planner's no-refactor-invention rule.** `planner.md` §"The planner does not invent refactors" says the planner must escalate when it detects a missing refactor rather than silently adding one. Is this rule actually enforceable given the planner's inputs? Specifically: can the planner tell "this refactor is missing from `design/refactors.md`" from "this refactor is captured but scoped differently than I would"? Flag any ambiguity that would let the planner escalate when it should just sequence what's there.
6. **Parallelism Posture structural gate.** `planner.md` §"Parallelism Posture as a structural gate" says `Cause: structural coupling preserved by design` is the signal for a structural escalation. Is this gate sharp enough? Could the planner emit this cause when the real issue is that the planner gave up? Is there a way to distinguish "design is structurally non-decomposable" from "planner could not find a decomposition"?
7. **Design-as-product structural debt.** Does the v3 package itself carry structural debt that will hurt future revisions? For example: is `terrain-contract.md` pulling double duty as both contract doc and tutorial? Does `planner.md` repeat content that lives in `terrain-contract.md`? Does `overview.md` re-state decisions that live in `decisions.md`? Flag any duplication that will drift.
8. **Module boundary anti-patterns.** Are there places where the v3 package adopts an anti-pattern it flags elsewhere? For example: does any doc exceed 500 lines (per dev-principles §"Structural Health Signals")? Does any doc have more than three responsibilities? Is there any "settings" or "utils" doc that has become a catch-all?
9. **Refactor-first sequencing honesty.** The v3 topology assumes refactors land before feature phases to unlock parallelism. Is this sequencing assumption realistic, or does it hide work that would be sequential anyway? Flag any case where the refactor-first sequencing would force all refactors into Round 1 even when Round 1 cannot actually run them all in parallel.

## Output shape

- **Status**: converged / needs-revision / needs-redesign
- **Top 3 structural findings**: the highest-leverage issues, each with file + section references
- **Refactor-contract integrity**: honest assessment of whether the per-entry fields prevent vibes
- **Cross-doc duplication**: concrete findings with file:section pairs
- **Recommendation**: what design-orch should revise before handing off to planner

Submit the report as your terminal report. Do not edit any design files.
