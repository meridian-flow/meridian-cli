# Final Spot-Check Review — did the honesty pass introduce new overclaims?

## Context

`workspace-config-design`'s R06 just underwent an honesty pass (p1898) addressing findings from three prior reviewers (p1895 framing, p1896 enforceability, p1897 consistency). The pass applied 9 corrections:

1. Primary executor reframed as 1 executor with 2 capture modes (PTY intended / Popen degraded fallback), not 2 executors.
2. Worker reframed as detached one-shot subprocess (architectural reason: detached lifecycle), not persistent queue.
3. App-streaming softened to "current API shape" keeping manager in-process, not "must be live."
4. Factory relabeled as "pipeline with explicit I/O stages" — `materialize_fork()` absorbed as the sole I/O-performing stage (Option A).
5. "Impossible to drift" dropped — replaced with "structurally difficult" / "heuristic guardrails."
6. CI script `scripts/check-launch-invariants.sh` + workflow job added as R06 scope.
7. Every builder has definition + sole-caller `rg` checks with evasion-mode acknowledgments.
8. Pyright tightened — ban `pyright: ignore` and `cast(Any,` in `launch/` and `ops/spawn/`, require `assert_never` per executor dispatch.
9. Consistency fixes (diagram label, 2 line-number citations).

Plus one substantive addition: **`observe_session_id()` adapter seam** — session ID moves off `LaunchContext` onto a new `LaunchResult`, closing p1891 blocker 2. Implementation swap to filesystem polling is tracked at GitHub issue #34.

## Your task — tight spot-check

Read:
- `.meridian/work/workspace-config-design/design/refactors.md` (R06)
- `.meridian/work/workspace-config-design/decisions.md` (D17)
- `.meridian/work/workspace-config-design/design/architecture/harness-integration.md` (Launch composition + Session-ID observation sections)
- `.meridian/spawns/p1898/report.md` (what the pass claims to have done)
- `.meridian/spawns/p1895/report.md`, `.meridian/spawns/p1896/report.md` (findings that drove the corrections)

Probe live code minimally — only to verify specific claims. Do not re-audit the whole architecture.

### Five questions

1. **Did any prior-round finding survive un-addressed?** Quickly scan p1895 and p1896 findings, mark each as closed or not-closed by the current state of the design. Not-closed findings are the only blocker category for this review.

2. **Did the honesty pass introduce any *new* overclaim?** The pass softened some claims — did it accidentally add new ones? Specifically: is the new `observe_session_id()` seam honestly described, or does it overclaim (e.g., "structural guarantee" language around the new types, or claims about what current implementations do that don't match code)?

3. **Is `LaunchResult`/`LaunchOutcome` coherent with the 2 executors?** Primary executor returns different raw output than async subprocess executor (PTY pipe buffer vs. structured-stream stdout). Does the design acknowledge that `LaunchOutcome.captured_stdout: bytes | None` can mean different things per executor? If it's claimed to be uniform, that's a new overclaim.

4. **Is the CI gate actually buildable?** The script `scripts/check-launch-invariants.sh` is named. Does the design specify enough for a coder to build it? (It doesn't need to be written now, but a planner needs enough info: input format for `rg` patterns, output format, exit-code semantics, which patterns are CI-hard-failing vs. warnings.)

5. **Fork Option A + pure stages — does the "pipeline with explicit I/O" claim hold?** `materialize_fork()` is marked as the sole I/O stage. Verify by inspection: are the other pipeline stages (`resolve_policies`, `resolve_permission_pipeline`, `build_env_plan`, `project_workspace`, `resolve_launch_spec`) actually pure today, or do any of them also touch disk / network / subprocess? If any are impure and the design claims they're pure, that's a new overclaim.

### Report format

- Under 400 words total.
- Structure: findings as **Blocker / Major / Minor / Clean** with file:line references.
- A finding should only be raised if it's a *new* issue from this pass or a prior-round issue still un-addressed. Don't re-litigate resolved items.
- End with a **Verdict**: `ship` / `ship-with-minor-fixes` / `request-changes`.
- If `ship`, the design is ready for planning handoff. If `ship-with-minor-fixes`, list fixes that can be applied by a quick editor pass (not an architect). If `request-changes`, explain what blocks.
