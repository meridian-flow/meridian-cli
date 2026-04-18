# Re-Review — workspace-config-design after R06 grow-and-keep-as-prereq

## Context

Second review pass for `workspace-config-design`. First pass:
- `.meridian/spawns/p1882/report.md` (gpt-5.4, adversarial) — blocker on R06 as prereq + R06 under-scoped.
- `.meridian/spawns/p1883/report.md` (opus, consistency) — two majors (relative `MERIDIAN_WORKSPACE`, surfacing.md `Realized by` gap) + minors.

Architect (p1887) then did the **wrong** thing: demoted R06 to optional follow-up (matching gpt's Depth-2 recommendation), even though the user directive was explicit — "it IS a future tax... it should be refactor first... make it impossible to drift". That change was manually reverted.

The current state reflects the user's directive: **R06 stays as a prereq AND grows** to close the drift surface gpt flagged. Relevant changes from the first-pass baseline:

1. `decisions.md` D17 rewritten: prereq ordering preserved; scope grown to include `ops/spawn/prepare.py`, primary fork recomposition (`launch/process.py:68`), `MERIDIAN_HARNESS_COMMAND` bypass (`plan.py:259` + `command.py:53`), and unification of the two `RuntimeContext` types. "Impossible-to-drift" invariants spelled out. New rejected alternative: "demote R06 to optional follow-up" — rejected.
2. `decisions.md` D18 (renumbered from D19): relative `MERIDIAN_WORKSPACE` = absent + advisory, no fallthrough. Architect's D18 (demotion) is gone.
3. `design/refactors.md` R05: scope reverted to single shared seam (no longer targets both existing seams).
4. `design/refactors.md` R06: rewritten with grown scope + seven invariant-style exit criteria ("exactly one X"). Test-file blast-radius enumeration added.
5. `design/architecture/harness-integration.md` Launch composition section: reverted to single shared seam post-R06.
6. Other architect fixes **kept**: WS-1.e5 (relative override), SURF-1.e6 expansion, D13 clarification (no fallthrough on missing target), `unsupported:harness_command_bypass` applicability row, R02 exit-criteria wording, D6 R04→R01 fold note, WS-1.e2 commented-TOML clarification, feasibility formatting.

## What to review

Read in this order:
1. `decisions.md` D17 (line 428-455) and D18 (line 457-477) — the reverted/grown decisions.
2. `design/refactors.md` R05 (line 76-124) and R06 (line 126-195) — the expanded R06 scope and invariant-style exit criteria.
3. `design/architecture/harness-integration.md` — especially "Launch composition" (line 114-140).
4. `design/spec/workspace-file.md` WS-1.e5, `design/spec/surfacing.md` SURF-1.e6 — relative-override coverage.
5. The rest of the design package for context.

## Your focus lane

{{LANE}}

## Probes

These are questions, not a checklist. Find what's wrong, not just what's listed.

1. **R06 invariant coverage**: the exit criteria claim seven "exactly one X" invariants. Do the listed scope files + their line numbers actually achieve all seven? If R06 ships as described, can the invariants be mechanically verified (e.g., `rg` checks, type unification tests)?
2. **R06 scope completeness**: are there launch-composition sites the grown scope *still* misses? Check `src/meridian/lib/` for any code that builds child env, resolves policies, constructs `SpawnParams`-like objects, or composes `LaunchContext`-equivalents that aren't in R06's scope list. The user's directive is zero drift surface.
3. **R05 ↔ R06 coupling**: R05 now says "single shared composition seam delivered by R06". Does R05's exit criteria + harness-integration.md Launch composition actually hold if R06 ships as scoped? Or is there still an implicit assumption R06 doesn't deliver?
4. **Invariant enforceability**: "exactly one `RuntimeContext` type" is straightforward. But "exactly one policy/permission/`SpawnParams` resolution site" requires knowing every resolver call site. Are those listed comprehensively, or is "ops/spawn/prepare.py has no resolution logic that the shared seam does not already own" under-specified?
5. **Relative `MERIDIAN_WORKSPACE` behavior consistency**: D18, WS-1.e5, SURF-1.e6, and the paths-layer/workspace-model docs should all agree. Any gap?
6. **Decisions.md D17 rejected-alternatives coverage**: D17 now rejects Depth-2, Depth-3, and "demote R06". Is the rejection reasoning strong enough that a future reviewer reading only D17 (no review transcript) understands why the grown R06 is correct?
7. **Planning hand-off readiness**: if a planner reads this package cold, can they sequence the work without asking follow-up questions? R01, R02, R06 are all prep refactors. What's the ordering constraint between them?
8. **Test-blast-radius enumeration**: R06 adds a `rg -l ...` command to find test files. Is that command correct? Are there tests it misses (e.g., tests that import the types by fully-qualified path)?

## Output contract

Severity: **blocker**, **major**, **minor**, **nit**. Cite file paths + line numbers. If you think R06 should be demoted again (against the user's directive), say so explicitly with evidence — the user will decide, not the reviewer.

Keep the report structured.
