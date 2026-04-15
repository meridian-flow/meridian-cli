# Review — v3 Decomposition Sanity

You are reviewing the **v3 orchestrator-restructure design package** for decomposition coherence: can the planner actually do its job given the inputs this design produces, and will the downstream execution loop be sane? Your focus is **decomposition sanity** — does the design describe a system the planner can decompose into parallelizable phases that testers can verify?

## What to read

1. `$MERIDIAN_WORK_DIR/design/overview.md`
2. `$MERIDIAN_WORK_DIR/design/planner.md` — the central frame is parallelism-first
3. `$MERIDIAN_WORK_DIR/design/impl-orchestrator.md` — planner consumer, runs pre-planning
4. `$MERIDIAN_WORK_DIR/design/design-orchestrator.md` — produces the spec tree, architecture tree, refactors.md, feasibility.md
5. `$MERIDIAN_WORK_DIR/design/feasibility-questions.md` — shared four-question frame
6. `$MERIDIAN_WORK_DIR/design/terrain-contract.md` — refactors and feasibility contract
7. `$MERIDIAN_WORK_DIR/design/preservation-hint.md` — redesign cycle preservation
8. `$MERIDIAN_WORK_DIR/decisions.md` D3, D7, D10, D12, D15, D19, D20, D22

## Questions to answer

1. **Input completeness.** The planner consumes spec tree + architecture tree + refactors.md + feasibility.md + pre-planning-notes + (optionally) preservation-hint. Given these, can the planner write a complete plan without gaps? Walk through a hypothetical work item and identify any missing input the planner would need to reach for.
2. **Dual parallelism condition.** `planner.md` says parallelism requires both disjoint architecture subtrees AND disjoint spec-leaf coverage. Is this condition enforceable? Test: take two hypothetical phases that touch disjoint files but claim overlapping spec leaves — does the planner's framework catch that they can't actually run in parallel? Does the `plan/leaf-ownership.md` file make double-claims visible?
3. **Planner cycle cap K=3 vs the planning-blocked escape hatch.** D12 caps planner re-spawns at 3. D5's planning-time arm fires `planning-blocked` after K=3. Is this cap realistic for a spec-tree with 20+ leaves? Walk through: can a planner converge in 3 spawns when impl-orch has to feed it back gaps each time? Flag any case where K=3 is likely to trigger a redesign loop for reasons that don't need one.
4. **Pre-planning scope.** `impl-orchestrator.md` says pre-planning scopes to `impl-orch must resolve during pre-planning` tags plus runtime constraints design could not anticipate. Is this scope bounded tightly enough that impl-orch won't re-do feasibility analysis design-orch already completed? Flag any place where impl-orch's pre-planning could bloat into a full feasibility re-run.
5. **Preservation hint mechanics across redesigns.** `preservation-hint.md` says redesigns preserve work by default and rescope pre-planning to the replan-from-phase onward. Walk through a cycle: work has committed Phase 1, Phase 2, Phase 3; redesign cycle invalidates Phase 4's assumption. How does the new plan fit Phase 4 (replanned) alongside new spec leaves (S07.3.e1) and preserved leaf ownership? Is there a gap where the new plan could accidentally unclaim a preserved leaf or double-claim it?
6. **Structural-blocking vs planning-blocked signal distinction.** D5's planning-time arm has two causes: `structural-blocking` (planner returns sequential with `Cause: structural coupling preserved by design`) and `planning-blocked` (K=3 exhausted). Can impl-orch actually tell these apart from the planner's terminal report? Flag any case where the two signals could confuse dev-orch into routing the wrong redesign.
7. **Refactor-to-feature phase sequencing.** Round 1 refactors land first, Round 2 feature phases fan out. Can the planner always achieve this order, or are there work items where refactors depend on feature-derived information that only exists after Round 2 starts? Walk through a work item that adds a feature *and* refactors a module the feature touches. Flag if Round 1/Round 2 sequencing breaks.
8. **Leaf-ownership double-claim detection.** `plan/leaf-ownership.md` says every leaf is claimed by exactly one phase. What's the check mechanism? Is there a specific reviewer or tester step that verifies no double-claims? Flag if the check is implicit (e.g. "impl-orch catches it during verification") rather than explicit.
9. **EARS-to-test parsing feasibility.** D21 says smoke-testers parse EARS leaves into trigger/precondition/response. Is this parsing actually mechanical? Walk through the five EARS patterns (Ubiquitous, State-driven, Event-driven, Optional-feature, Complex) and check that each decomposes cleanly into the triple. Flag any pattern where the decomposition is ambiguous or would require interpretation.
10. **Light-path decomposition.** D23 says small work can use a degenerate single-file tree. If design is a single `spec/overview.md` + single `architecture/overview.md` with no subtrees, can the planner still produce a parallelism-rich plan? Or does the light path effectively force sequential decomposition?

## Output shape

- **Status**: converged / needs-revision / needs-redesign
- **Input completeness verdict**: can the planner actually write a complete plan from the v3 inputs
- **Sequencing hazards**: concrete cases where Round 1/Round 2 sequencing would break
- **Signal clarity**: can impl-orch and dev-orch actually distinguish the escape hatches
- **Double-claim protection**: is there a real check for leaf ownership
- **Recommendation**: what design-orch should revise before handing off to planner

Submit the report as your terminal report. Do not edit any design files.
