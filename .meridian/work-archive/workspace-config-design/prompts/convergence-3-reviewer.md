# Convergence-3 Confirmation Review — R06 Redesign

## Your focus

The design-orch R06 redesign cycle (p1936) ran two rounds of convergence. Convergence-2 surfaced findings from two parallel reviewers; design-orch addressed those through four substantive structural changes recorded as D20.1-D20.4 in `decisions.md`.

Your job: verify those four closures actually land and no new issues have crept in through the fixes themselves.

## Read in this order

1. `.meridian/work/workspace-config-design/decisions.md` — specifically the D20 entries (D20.1-D20.4) and the preserved-findings list
2. `.meridian/work/workspace-config-design/reviews/r06-redesign-alignment.md` — the convergence-2 alignment reviewer's findings
3. `.meridian/work/workspace-config-design/reviews/r06-redesign-dto-shape.md` — the convergence-2 dto-shape reviewer's findings
4. `.meridian/work/workspace-config-design/design/refactors.md` — R06 section (updated)
5. `.meridian/work/workspace-config-design/design/architecture/launch-core.md` — A06 (new)
6. `.meridian/work/workspace-config-design/design/launch-composition-invariant.md` — the drift-gate prompt (new)

## What to verify

For each D20 change, confirm both **closure** (the stated reviewer finding is actually addressed in the updated artifacts) and **no-new-issue** (the fix doesn't introduce a new blocker/major):

- **D20.1 — stage split (`resolve_launch_spec_stage` → `apply_workspace_projection` → `build_launch_argv`).** Does R06 / A06 now have these as three named stages with sole-callsite invariants? Is the A04 workspace-projection seam reachable? Are the callsite counts actually enforceable in the invariant prompt?
- **D20.2 — `LaunchRuntime` as 4th user-visible DTO.** Does it have an honest home for the runtime-injected fields? Is the `unsafe_no_permissions` dispatch through `resolve_permission_pipeline` specified, not hand-waved?
- **D20.3 — `LaunchContext.warnings` channel.** Is the `CompositionWarning` type specified (fields, frozen, when emitted)? Is it the single warning sidechannel, or do driver-side warning paths still exist?
- **D20.4 — invariant prompt drafted.** Does `design/launch-composition-invariant.md` cover the 10 invariants, protected file list, "does NOT count as violation" carve-out, and structured JSON output format? Is it concrete enough for a reviewer spawn to produce actionable pass/fail verdicts?

Also do a sanity pass on:
- **Schema completeness sweep** (every field today's drivers carry has a named home in the 4 user-visible types + `CompositionWarning`).
- **`observe_session_id` contract unification.** The D20 report says the contract is "per-launch state legitimate, adapter-singleton state forbidden." Verify that's how R06 / A06 describes it and there's no contradiction with the A04 harness-integration notes.
- **Five new behavioral tests** — child-cwd-after-row, warnings propagation, workspace-projection seam reachable, unsafe-no-permissions dispatch, SessionRequest 8-field completeness. Each specified well enough a tester knows what to assert?

## What to ignore

- Pre-convergence-2 reviewer findings (r06-retry-*.md) — already addressed in convergence-1 (D19).
- Out-of-scope items design-orch flagged (background-worker `disallowed_tools`, issue #34 Popen-fallback) — deliberately deferred.
- Style / caveman voice / document structure — if it's readable and specific, it's fine.

## Output

A markdown report at `$MERIDIAN_WORK_DIR/reviews/r06-redesign-convergence-3.md` with:

1. **Per-D20 verdict** — for each of D20.1-D20.4: `closed-cleanly` / `closed-with-caveats` / `still-open`. Caveats and open items get specific file:line evidence.
2. **New issues introduced** — did any D20 fix create a new problem? Blocker/major/minor with file:line.
3. **Schema completeness + `observe_session_id` + 5-tests sanity**: one-line each, pass/fail + evidence if fail.
4. **Overall verdict**: `ready-for-implementation` / `needs-more-convergence` / `ready-with-minor-followups`.
5. **If ready**: top 3 things the impl-orch Explore phase should specifically verify against code reality first.

## Style

Caveman full. Code pointers exact (file:line where applicable). No prose padding.

## Termination

Report path + overall verdict. That's it.
