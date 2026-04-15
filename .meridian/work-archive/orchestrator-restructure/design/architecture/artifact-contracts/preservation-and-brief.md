# A02.3: Preservation hint and redesign brief

## Summary

`preservation-hint.md` and `redesign-brief.md` are the two redesign-cycle handoff artifacts. `redesign-brief.md` is authored by impl-orch when execution or planning falsifies a spec leaf; dev-orch reads it to classify the signal and route to design-orch or scope-fix. `preservation-hint.md` is authored by dev-orch after the design-orch revision returns, and it carries the phase-preservation map into the next impl-orch cycle. Both files are overwritten per cycle (not appended), live at `$MERIDIAN_WORK_DIR/plan/preservation-hint.md` and `$MERIDIAN_WORK_DIR/redesign-brief.md` respectively, and are absent on first-cycle work.

## Realizes

- `../../spec/execution-cycle/escape-hatch.md` — S05.4.u2 (brief is the load-bearing record of bail-out), S05.4.e1 (execution-time brief contents), S05.4.e2 (planning-time brief contents), S05.4.e3 (exhaustion brief), S05.4.e4 (structural-blocking brief).
- `../../spec/redesign-cycle/preservation-hint-production.md` — S06.2.u1 (dev-orch sole author), S06.2.u2 (overwrite per cycle), S06.2.e1 (six-step production sequence), S06.2.e2 (revised-annotation preserves stable ID).
- `../../spec/execution-cycle/preserved-reverification.md` — S05.5.u1 (zero-revised-leaves skips pass), S05.5.e1 (tester-only re-verification).

## Current state

- `design/redesign-brief.md` (v2 flat doc) describes the brief shape as narrative prose with a sample structure; the runtime artifact has not yet been exercised on this work item.
- `design/preservation-hint.md` (v2 flat doc) describes the hint shape including the two-sub-category preserved split (`preserved` vs `preserved-requires-reverification`) and the six-step dev-orch production sequence. The runtime artifact is likewise not yet exercised.
- v2 does not have a formal escape-hatch planning-time arm; the brief shape currently assumes execution-time bail-out as the default.

## Target state

### `redesign-brief.md` — shape

One file per redesign cycle, overwritten on each new cycle. Authored by impl-orch when falsification fires (execution-time, planning-time, or exhaustion). Contents:

1. **Cycle number and entry signal** — `Cycle: N`, `Entry signal: execution-time | planning-time | exhaustion (K_fail) | exhaustion (K_probe) | structural-blocking`.
2. **Falsified spec leaves** — the spec-leaf EARS statement IDs whose acceptance contract the runtime or pre-planning evidence contradicts. Each entry cites the evidence (tester report, probe result, module scan, etc.). The list is keyed on falsification, not severity: a minor edge case that contradicts a leaf is still a falsification (S05.3.s3).
3. **Evidence** — the concrete runtime or planning-time observations that caused the bail-out. Tester report excerpts, probe output, file-level scan results — enough for dev-orch to judge the classification (design-problem vs scope-problem) without re-running the observation.
4. **Preservation section** — impl-orch's first-pass classification of phases into preserved / partially-invalidated / fully-invalidated, plus the `replan-from-phase` anchor. This is impl-orch's proposal; dev-orch may revise it when producing the hint (S06.2.c2).
5. **Constraints that still hold** — the parts of the original intent that the falsification does not invalidate. Dev-orch copies this into the preservation hint (S06.2.s3) so the next impl-orch cycle has it in direct context.
6. **Requested action** — `design-revision` (the default — route to design-orch for a revised design cycle) or `scope-fix` (route to impl-orch for a fix inside the existing design). Impl-orch suggests; dev-orch decides.
7. **Parallelism-blocking section** *(conditional — present only when the entry signal is structural-blocking per S05.4.w1)* — names the specific parallelism claim the design made and the runtime evidence that contradicts it, so design-orch can target the refactor agenda at the blocker.

**Duplicate-evidence briefs are rejected.** If the brief repeats a falsification claim from a prior cycle without citing new evidence, dev-orch rejects it per S06.3.e2 — the redesign cycle counter does not advance, and impl-orch must produce new evidence or patch forward.

### `preservation-hint.md` — shape

One file per redesign cycle, overwritten on each new cycle. Authored by dev-orch after design-orch's revision returns. Contents:

1. **Source** — `Derived from redesign-brief.md cycle N. Design revision: decisions.md D<m> (revised design docs: <list>)`.
2. **Preserved phases table** — columns `Phase | Commit SHA | Spec leaves satisfied (EARS statement IDs) | Revised leaves? | Reason preserved`. The `Spec leaves satisfied` column lists EARS statement IDs at `S<subsystem>.<section>.<letter><number>` granularity, not leaf-file paths (S04.2.e5 propagates). The `Revised leaves?` column names the sub-category:
   - `none` → **preserved, no re-verification.** The next impl-orch cycle skips the phase entirely (no coder, no tester).
   - `<leaf ID list>` → **preserved but requires re-verification.** Impl-orch runs a tester-only re-verification pass for the revised leaves against existing commits before executing any replanned or new phases (S05.5.e1).
3. **Partially-invalidated phases table** — columns `Phase | Commit SHA | Spec leaves | What is invalid | What is salvaged`. Commits stay in git history; the next impl-orch cycle respawns the coder with partial-invalidation scope.
4. **Fully-invalidated phases table** — columns `Phase | Commit SHA | Spec leaves | Reason fully invalidated`. Commits stay in git history but the next cycle treats the phases as not-yet-done.
5. **Replan-from-here anchor** — `replan-from-phase: N`. Everything before `N` is preserved or partially-invalidated; everything from `N` forward is replanned by @planner. The planner must honor this anchor (S06.2.s2).
6. **New or revised spec leaves from the redesign** — the spec leaves added or revised in `design/spec/` during this redesign cycle. Revised-in-place leaves keep their stable ID and carry a `revised: <reason>` annotation; newly introduced leaves get fresh IDs (S06.2.e2, S06.2.e3). The planner claims every entry in the new `plan/leaf-ownership.md`.
7. **Constraints from the original intent** — replay of the redesign brief's `Constraints that still hold` section, copied into the hint so impl-orch and the planner have it in direct context without loading the brief separately.

### Status field propagation

The hint seeds `plan/status.md` with the following phase status values:

| Status | Meaning |
|---|---|
| `preserved` | Phase from a previous cycle, complete, skipped entirely this cycle. No coder, no tester. Applies when `Revised leaves? = none`. |
| `preserved-requires-reverification` | Phase from a previous cycle with commits intact, but at least one claimed spec leaf was revised in place. Impl-orch runs tester-only re-verification against existing code before execution (S05.5.e1). Outcome branches back into `preserved` or `partially-invalidated` per S05.5.e2 / S05.5.e3. |
| `partially-invalidated` | Phase from a previous cycle needing revision. Coder respawned with partial-invalidation scope. |
| `replanned` | Phase from a previous cycle fully invalidated; the new plan replaces it. |
| `new` | Phase added in this cycle that did not exist before. |
| `not-started` | Phase exists in the current plan and has not yet been touched. Default seed when no hint is present. |

### Revised-in-place rule (stable IDs)

When design-orch revises the text of an EARS statement in place during a redesign cycle, the statement ID stays stable. The revision is recorded as `revised: <reason>` in the preservation hint's "New or revised spec leaves" section. The planner copies the `revised:` annotation verbatim into `plan/leaf-ownership.md`, and the tester executing re-verification parses the *current* EARS text against the existing code (S05.5.w1).

This rule is load-bearing because it closes the silent-drift failure mode: without stable IDs, a preserved phase could quietly satisfy old EARS text while the spec says something different. With stable IDs plus the revised annotation, the silent-drift window shrinks to a single tester-only pass per cycle (S05.5.e2/e3/e4).

## Interfaces

- **`-f $MERIDIAN_WORK_DIR/redesign-brief.md`** — attached by dev-orch when reading the bail-out, attached to design-orch re-spawn, attached to any @reviewer asked to judge whether the brief is design-problem or scope-problem.
- **`-f $MERIDIAN_WORK_DIR/plan/preservation-hint.md`** — attached to the next impl-orch cycle's planning spawn as the first `-f`, and attached to the @planner spawn inside that planning impl-orch.
- **`$MERIDIAN_WORK_DIR/plan/status.md`** — seeded by @planner from the hint when a hint is present; seeded with all-`not-started` when absent.

## Dependencies

- `./shared-work-artifacts.md` — the `plan/` layout that hosts `preservation-hint.md` and `status.md`.
- `../../spec/execution-cycle/escape-hatch.md` — the spec-side rules that define when a brief must be produced.
- `../../spec/redesign-cycle/preservation-hint-production.md` — the spec-side rules for dev-orch's hint production.

## Open questions

None at the architecture level.
