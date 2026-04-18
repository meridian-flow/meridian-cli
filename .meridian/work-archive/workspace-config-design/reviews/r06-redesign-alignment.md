# R06 Redesign — Design-Alignment Convergence Review

## Verdict
block

## Critical findings

### Blocker — A04's workspace-projection seam is not reachable inside the A06/R06 stage ordering
- Pointer: `design/architecture/harness-integration.md:231-246`, `design/architecture/launch-core.md:165-168`, `design/architecture/launch-core.md:418-423`, `design/refactors.md:323-331`
- What's wrong: A04 says `project_workspace()` runs after `resolve_launch_spec(...)` and before env construction, and that `projection.extra_args` appends to `spec.extra_args`. But A06/R06 define `project_launch_command()` as the sole `resolve_launch_spec` + `build_command` callsite that already returns final `argv`, then place the A04 insertion point between that stage and `build_env_plan()`. Once `argv` is already built, there is no coherent place left to append `projection.extra_args` without either rebuilding the command a second time or mutating argv outside the declared sole owner.
- Why it matters: This is the load-bearing seam that makes A04 depend on A06. As written, the two leaves cannot both be true. Implementers will either reintroduce composition leakage or silently violate the single-owner table to make workspace projection work.
- Fix sketch: Re-cut the stage boundary so the workspace projection seam exists before final argv construction. Either split `project_launch_command()` into `resolve_launch_spec` and a later argv-build stage, or redefine `project_launch_command()` so it owns workspace projection internally and A04 references that exact contract.

## Major findings

### Major — The replacement drift gate is promised, but the invariant prompt artifact does not exist in the design package
- Pointer: `design/refactors.md:479-520`, `design/refactors.md:562-564`, `design/architecture/launch-core.md:397-406`
- What's wrong: The redesign makes `.meridian/invariants/launch-composition-invariant.md` a first-class verification artifact, but that file is absent. The design package therefore never actually shows the prompt a CI reviewer would read.
- Why it matters: The verification triad is one of D19's five committed redesign changes. Without the artifact, there is no concrete drift-gate contract to assess for ambiguity, maintain in version control, or hand to a future reviewer.
- Fix sketch: Add the invariant prompt file now as part of the design package, not as an implied future implementation detail. It should enumerate protected files, explicit fail conditions, and how the reviewer should treat renamed helpers, indirect adapter calls, and new stage modules.

### Major — The session-id observation contract diverges between A04/D17 and A06
- Pointer: `decisions.md:550-557`, `design/architecture/harness-integration.md:146-155`, `design/architecture/launch-core.md:253-256`
- What's wrong: D17 and A04 define `observe_session_id()` as a getter over adapter-held state, not a parser of `launch_outcome`. A06 then says the Claude adapter will scrape PTY-captured stdout from `launch_outcome`.
- Why it matters: `observe_session_id()` is one of the redesign's named single-owner seams. This contradiction leaves the seam underspecified right where prior reviews demanded a single observation path. A future implementation could split logic between executor-output parsing and adapter-owned state and still claim compliance.
- Fix sketch: Choose one contract and make all three documents match. If Claude genuinely needs `launch_outcome.captured_stdout`, describe that as the canonical contract everywhere and remove the "not a parser" language. If the intent is adapter-owned per-launch state, move the Claude wording to match that model.

### Major — The verification triad does not actually pin the D7 child-cwd-before-row regression
- Pointer: `design/architecture/launch-core.md:343-346`, `design/architecture/launch-core.md:294-297`, `design/refactors.md:394-397`, `design/refactors.md:444-477`, `design/refactors.md:496-514`
- What's wrong: A06 says child cwd creation has one owner and happens only after the spawn row exists, but the 10 behavioral tests do not include a row-before-cwd assertion, and the summarized drift-gate invariants do not name child cwd creation at all.
- Why it matters: D7 was one of the explicit correctness findings driving the redesign. As written, the replacement verification stack can still miss a future refactor that recreates `.meridian/spawns/<id>` before row creation while leaving the current test list green.
- Fix sketch: Add one deterministic behavioral test that proves no child cwd materialization occurs before row creation, and add the same constraint to the invariant prompt/single-owner checklist the reviewer uses.

## Minor findings / nits

None.

## What converges cleanly

The redesign does fix the central problem the retry reviews called out: raw `SpawnRequest` at the factory boundary closes D1-D3 and removes the dead `PreparedSpawnPlan` barrier. The fork-after-row story is also much stronger than the prior R06 shape, with explicit failure semantics and documented out-of-scope follow-ups for issue #34 and issue #32. D19's rationale is complete on the alternatives the prompt asked me to verify: it explicitly rejects rename-only `PreparedSpawnPlan` cleanup, DI-container adoption, and AST-heavier `rg` checking, and the reasoning is coherent.

## Severity count
- blocker: 1
- major: 3
- minor: 0
