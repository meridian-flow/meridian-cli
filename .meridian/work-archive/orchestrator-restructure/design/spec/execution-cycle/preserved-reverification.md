# S05.5: Preserved-phase re-verification

## Context

The preservation hint uses `preserved` to mean "code committed, do not respawn coder," but some preserved phases own spec leaves whose EARS statement was revised in-place during the current redesign cycle (the ID stays stable per S02.1.e2, the trigger/precondition/response text changed). If impl-orch skips preserved phases entirely, revised leaves ride the old verification and the system silently drifts from the new spec — this is the exact failure mode Fowler's spec-anchored discipline exists to prevent. The mechanism to avoid the drift is a **tester-only re-verification pass**: preserved phases whose hint lists any `revised:` spec leaves get their testers re-spawned (no coder), and three outcomes are possible — all revised leaves still verify (phase stays preserved), some fall (phase promotes to partially-invalidated, coder re-spawns with scoped instruction), or re-verification cannot be executed (phase promotes to replanned, redesign brief emitted).

**Realized by:** `../../architecture/orchestrator-topology/execution-loop.md` (A04.2) and `../../architecture/artifact-contracts/preservation-and-brief.md` (A02.3).

## EARS requirements

### S05.5.u1 — Preserved phases with zero revised leaves skip re-verification

`Every preserved phase whose preservation-hint entry lists zero revised spec leaves shall skip the re-verification pass entirely and run as pure preserved (no coder spawn, no tester spawn), because the phase's committed behavior is still covered by verification against the unchanged EARS statements.`

### S05.5.e1 — Tester-only re-verification on revised leaves

`When the execution impl-orchestrator encounters a preserved phase whose preservation-hint entry lists at least one spec leaf flagged with revised: <reason>, impl-orch shall spawn the testers named in the phase blueprint with a scoped instruction naming the revised leaf IDs, and shall not spawn the phase coder.`

### S05.5.e2 — Outcome 1: all revised leaves still verify → stay preserved

`When the tester-only re-verification pass reports that every revised leaf still verifies against the current committed code, impl-orch shall keep the phase marked as preserved in plan/status.md, shall not re-commit, and shall advance to the next phase.`

**Reasoning.** Revisions that tighten language without changing behavior (common case) leave the existing code legitimately satisfying the new statement. No delta needed.

### S05.5.e3 — Outcome 2: some revised leaves falsify → promote to partially-invalidated

`When the tester-only re-verification pass reports that one or more revised leaves falsify against the current committed code, impl-orch shall promote the phase from preserved to partially-invalidated in plan/status.md, re-spawn the phase coder with a scoped instruction naming the now-failing revised leaves, and run the normal fix loop; impl-orch shall not revert the existing preserved commits.`

**Reasoning.** The existing commits stand as the baseline; the coder lands an additional delta on top of them to satisfy the revised statements. Reverting first would lose committed work the revised statements did not invalidate.

### S05.5.e4 — Outcome 3: re-verification cannot execute → promote to replanned

`When the tester-only re-verification pass cannot be executed (testers cannot run, environment is broken, required fixtures are missing), impl-orch shall promote the phase from preserved to replanned in plan/status.md, emit a redesign brief naming the blockage per S05.4, and route to dev-orch for planning-time resolution.`

### S05.5.s1 — Re-verification runs before replanned/new phases begin

`While the execution impl-orchestrator is processing a redesign-cycle plan, the tester-only re-verification pass for preserved phases shall run before any replanned or new phases begin, because those downstream phases may depend on contracts the revised leaves describe.`

**Reasoning.** Running replanned and new phases against un-re-verified preserved code would stack uncertainty on top of uncertainty. The re-verification pass is the boundary between known-still-valid work and new work.

### S05.5.s2 — One tester spawn per preserved phase with revised leaves

`While the execution impl-orchestrator is running the re-verification pass, the impl-orch shall emit one tester spawn per preserved phase that has at least one revised leaf, with the scoped instruction naming the revised leaf IDs for that phase only, and shall not batch multiple phases into one spawn.`

**Reasoning.** Per-phase tester spawns keep the report shape per-phase and let impl-orch route outcome 2 (partial invalidation) to a per-phase coder re-spawn without cross-phase confusion.

### S05.5.w1 — Leaf IDs are stable across in-place revision

`Where a redesign cycle revises an EARS statement in place (same trigger/response concept, refined language), the leaf ID and the EARS statement ID shall remain stable per S02.1.e2, and plan/leaf-ownership.md entries from the prior cycle shall survive the revision so that preserved phase claims still resolve.`

### S05.5.s3 — Revised annotation propagates to leaf-ownership.md

`While the planning impl-orchestrator is running @planner on a redesign cycle, leaf-ownership.md entries for preserved phases shall be populated from the preservation hint's "Spec leaves satisfied" column, and EARS statements flagged with revised: <reason> in the hint shall carry re-verification notes so testers know the response clause changed even though the ID is stable.`

## Non-requirement edge cases

- **Automatic coder respawn on every revised leaf.** An alternative would respawn the coder for every preserved phase whose hint lists any revised leaf, without running the tester-only pass first. Rejected because the common case (revisions tighten language, behavior unchanged) does not need a coder — re-verification is the cheap check that distinguishes language-only revisions from behavior-changing revisions. Flagged non-requirement because the tester-first pass is load-bearing for redesign-cycle cost.
- **Revert preserved commits before re-spawning coder.** An alternative would revert the preserved commits before running the coder on outcome 2. Rejected because the existing commits are legitimately valid for the unrevised portion of the phase, and reverting would lose work. Flagged non-requirement because the additive-delta rule is load-bearing for preservation efficiency.
- **Batched re-verification across all preserved phases in one spawn.** An alternative would run one tester spawn covering all preserved phases with revised leaves. Rejected because the report shape would make per-phase outcome routing harder and would confuse scoped instruction targeting. Flagged non-requirement because the per-phase spawn shape is load-bearing for routing clarity.
