# S05.1: Per-phase execution loop

## Context

The execution impl-orch is a fresh spawn separate from the planning impl-orch per the terminated-spawn contract (S03.2.c1). Its inputs are the approved plan attached via `-f` and an explicit "execute existing plan" prompt that instructs it to skip pre-planning and the @planner spawn entirely. From there it runs a per-phase loop: read the phase blueprint, spawn a coder for the phase, wait for the coder, spawn testers to verify the spec leaves the phase claims, iterate the fix loop until all claimed leaves are verified, commit, move to the next phase. Parallel-eligible rounds run phase coders concurrently. Per-phase commits still isolate rollback. The loop carries over unchanged from the prior topology except for one thing: verification is keyed to spec-leaf IDs at EARS-statement granularity, not to scenario files.

**Realized by:** `../../architecture/orchestrator-topology/execution-loop.md` (A04.2).

## EARS requirements

### S05.1.u1 — Execution impl-orch is a fresh spawn

`The execution impl-orchestrator shall be a fresh spawn distinct from the planning impl-orchestrator, with the approved plan attached via -f, and shall not be a resumed suspended spawn of the planning impl-orchestrator.`

**Reasoning.** Meridian is crash-only. State lives on disk, not in conversation context. A suspended impl-orch holding plan state in memory cannot survive a crash, a compaction, or a restart. See D15.

### S05.1.u2 — Execution impl-orch skips pre-planning and planner spawn

`The execution impl-orchestrator shall not run the pre-planning step per S04.1 and shall not spawn @planner per S04.2, and shall start directly at the execution loop on the first phase named in plan/status.md as not-started or as owed work by the preservation hint.`

### S05.1.e1 — Per-phase loop sequence

`When the execution impl-orchestrator processes a phase, the sequence shall be: read the phase blueprint (plan/phase-N-<slug>.md), spawn the phase coder with the blueprint and relevant source files attached via -f, wait for the coder, spawn testers named in the blueprint to verify each claimed spec-leaf ID, iterate the fix loop until every claimed EARS statement verifies or until the phase cannot converge, commit, and advance to the next phase per plan/status.md.`

### S05.1.e2 — Parallel-round fanout

`When the execution impl-orchestrator encounters a plan round whose phases are marked parallel-eligible by plan/overview.md's Parallelism Posture, impl-orch shall spawn the phase coders concurrently rather than serially, subject to the runtime constraints plan/pre-planning-notes.md flagged (shared test harnesses, global registries, filesystem fixtures, env-var collisions).`

### S05.1.e3 — Per-phase commit

`When a phase's claimed spec leaves have all verified and its testers report pass, the execution impl-orchestrator shall commit the phase's changes to git with a descriptive message, update plan/status.md to mark the phase complete, and advance to the next phase; phases that do not converge shall not commit.`

**Reasoning.** Per-phase commits isolate rollback. A phase that cannot converge leaves no partial commit polluting the working tree, and a phase that does converge can be reverted cleanly if a later phase discovers it must revise upstream work.

### S05.1.c2 — Decision log is live, not retrospective

`While the execution impl-orchestrator is running the per-phase loop, when impl-orch makes a judgment call that is not obvious from the plan (adapting execution order, splitting a phase, narrowing scope in response to runtime findings, overruling a tester dispute), impl-orch shall record the decision in decisions.md at the moment of decision and not retrospectively.`

### S05.1.s2 — Adaptation is allowed, deviation from spec is not

`While the execution impl-orchestrator is running the per-phase loop, impl-orch may adapt execution order, split phases, or adjust scope in response to runtime findings scoped to what impl-orch can resolve; impl-orch shall not deviate from any spec leaf, and spec-leaf disagreements shall route through the escape hatch per S05.4 or through a scoped design revision, not through silent code workarounds.`

### S05.1.s3 — Architecture-tree deviation allowed with decision log entry

`While the execution impl-orchestrator is running the per-phase loop, impl-orch may deviate from the architecture tree's observational shape when runtime evidence supports it, and every deviation shall be logged in decisions.md with rationale per S02.2.s2.`

### S05.1.w1 — Final review loop runs end-to-end after all phases commit

`Where every phase in plan/status.md has committed and passed phase-level verification, the execution impl-orchestrator shall run the final review loop as reviewer fan-out across diverse strong model families with at least one design-alignment reviewer, one structural/refactor reviewer, and focus-area reviewers as the risk surface warrants, iterating until convergence.`

### S05.1.s4 — dev-principles applied across the final review fan-out

`While the final review loop is running, the dev-principles skill shall apply across every reviewer in the fan-out as part of each reviewer's rubric, and the execution impl-orchestrator shall not run dev-principles as a separate pass-fail gate (D24 revised).`

## Non-requirement edge cases

- **Suspended spawn resume across review checkpoint.** An alternative would hold the planning impl-orch spawn suspended across plan review and resume it for execution after approval. Rejected per D15 because meridian is crash-only — state on disk, not in memory. Flagged non-requirement to document the rejected suspended-spawn alternative.
- **Single commit at work-item end instead of per-phase commits.** An alternative would batch all phase changes into a single commit at work-item end. Rejected because per-phase commits isolate rollback and because losing a mid-work crash would lose work that the per-phase shape would preserve. Flagged non-requirement because the per-phase commit discipline is load-bearing for crash tolerance.
- **Strict phase ordering regardless of runtime findings.** An alternative would forbid adaptation and require impl-orch to execute phases exactly in plan order. Rejected because runtime evidence can reveal that an adjacent phase order fits the codebase better, and blocking adaptation would force escape-hatch bail-outs on trivial scope shifts. Flagged non-requirement because the adaptation-allowed rule is load-bearing for execution ergonomics.
