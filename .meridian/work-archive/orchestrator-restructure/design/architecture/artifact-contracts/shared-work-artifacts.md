# A02.2: Shared work artifacts (`plan/` layout after `scenarios/` retirement)

## Summary

`$MERIDIAN_WORK_DIR/plan/` is the shared execution-time artifact directory every orchestrator, planner, coder, and tester reads or writes. In v3 it carries `overview.md`, per-phase blueprint files, `leaf-ownership.md` (replacing v2's `scenario-ownership.md`), `status.md`, `pre-planning-notes.md`, and optionally `preservation-hint.md` on redesign cycles. The `scenarios/` folder is retired; every behavioral acceptance claim is a spec-leaf EARS statement owned through `leaf-ownership.md`. This leaf defines the per-file shape so agents consuming `plan/*.md` via `-f` know what to expect without cross-reading any other doc.

## Realizes

- `../../spec/root-invariants.md` — S00.u3 (spec leaves as acceptance contract), S00.u4 (scenarios convention retired).
- `../../spec/planning-cycle/planner-spawn.md` — S04.2.e2 (four artifact files planner writes), S04.2.e5 (EARS-statement granularity in leaf-ownership).
- `../../spec/execution-cycle/phase-loop.md` — S05.1.u1 (execution impl-orch consumes these files), S05.1.e1 (per-phase sequence reads blueprint + leaf-ownership).
- `../../spec/design-production/refactors-and-feasibility.md` — S02.3.u1 (siblings live alongside `plan/`, not inside it).

## Current state

- The v2 `$MERIDIAN_WORK_DIR` layout ships a parallel `scenarios/` directory with S001-style scenario files and a `plan/scenario-ownership.md` counterpart. Phase verification is gated on scenario-file execution rather than on spec-leaf EARS-statement parsing.
- `dev-artifacts` skill in `meridian-dev-workflow/skills/dev-artifacts/SKILL.md` still hard-codes `scenarios/` as a first-class directory with lifecycle ownership, so every agent that loads the skill inherits the v2 convention.
- `plan/` in v2 has `overview.md`, `phase-N-*.md` blueprints, `status.md`, and `scenario-ownership.md`. Pre-planning output and preservation hints are not first-class files — they live inside the orchestrator's conversation until impl-orch writes them down.

## Target state

**Anchor target for R03.** `design/refactors.md` entry R03 (publish the v3 artifact convention through `dev-artifacts`) names this section as its `Architecture anchor`. The R03 migration is done when the `dev-artifacts` skill body describes the layout below, the `scenarios/` directory is no longer named as a first-class artifact anywhere in the workflow package, and every agent profile that loads `/dev-artifacts` inherits the new layout on the next `meridian mars sync`.

### Canonical work-item layout after scenario retirement

```
$MERIDIAN_WORK_DIR/
  requirements.md              # user intent capture, dev-orch authored
  design/                      # design package — see A01.1 for full shape
    spec/
    architecture/
    refactors.md
    feasibility.md
  decisions.md                 # append-only decision log, written live
  plan/
    overview.md                # root plan index — Parallelism Posture + rounds + per-round justifications + refactor-handling table + Mermaid fanout
    phase-N-<slug>.md          # per-phase blueprints, authored by @planner
    leaf-ownership.md          # EARS-statement-granularity claims (replaces scenario-ownership.md)
    status.md                  # phase status values, seeded by @planner, updated by execution impl-orch
    pre-planning-notes.md      # impl-orch runtime observations, authored during planning impl-orch's pre-planning step
    preservation-hint.md       # dev-orch authored, overwritten per redesign cycle, absent on first cycle
  redesign-brief.md            # impl-orch authored, overwritten per cycle, absent on first cycle
```

- **No `scenarios/` folder anywhere.** Every behavioral acceptance claim is a spec-leaf EARS statement with a stable ID (`S<subsystem>.<section>.<letter><number>`). Tester reports cite EARS statement IDs directly, not scenario files.
- **`plan/leaf-ownership.md` replaces `scenarios/overview.md` + `plan/scenario-ownership.md`.** See A03.2 for the per-claim shape.
- **Siblings live at `design/` altitude, not inside `plan/`.** `design/refactors.md` and `design/feasibility.md` are siblings of `design/spec/` and `design/architecture/`, not children of `plan/`, because they are design-phase outputs not execution-phase outputs. See A01.1 for the full two-tree layout.

### `plan/overview.md` — shape

The planner-authored root of `plan/`. Contents:

1. **Parallelism Posture** — exactly one of `parallel`, `limited`, or `sequential`, with a one-line `Cause: ...` annotation naming the driver (`inherent constraint` / `structural coupling preserved by design` / `runtime constraint` / `feature work too small to fan out`). Only `sequential + structural coupling preserved by design` fires the structural-blocking gate (S04.4).
2. **Rounds** — a numbered list of parallel rounds, each naming the phase blueprints that belong to the round.
3. **Per-round justifications** — for each round, the specific constraint that forced the parallelism decision. Generic "for safety" is a convergence failure; the justification must cite a real dependency, a real file-level overlap, or a real integration boundary.
4. **Refactor-handling table** — one row per entry in `design/refactors.md`, mapping `R0N` to the phase that executes it (or the note `inline in phase-M` if bundled into feature work).
5. **Mermaid fanout diagram** — a Mermaid graph showing round-to-phase edges. This is the single visual aid the dev-orch plan-review checkpoint consumes.

### `plan/phase-N-<slug>.md` — shape

One file per phase blueprint. Contents (all mandatory):

1. **Phase ID + title** — `Phase 3: <slug>`.
2. **Round** — which parallel round this phase belongs to.
3. **Scope** — what the phase changes and what it does not.
4. **Claimed EARS statements** — explicit list of spec-leaf EARS statement IDs this phase implements (e.g. `S03.1.u1, S03.1.e1, S04.2.c2`). Granularity is statement-level, not leaf-file-level (S04.2.e5).
5. **Touched refactors** — list of `R0N` refactor IDs this phase lands. Empty if no refactor lands in this phase.
6. **Architecture leaves touched** — the architecture leaves this phase modifies or adds. Architecture leaves are observational; a phase may deviate from them if decisions.md records the reason (S05.1.s3).
7. **Tester lane** — which tester role executes verification (`verifier`, `smoke`, `browser`, `unit`, or a combination).
8. **Known edge cases** — the edge cases the phase must handle. Additional edge cases may be discovered during execution and appended to decisions.md.
9. **Dependencies** — the phases (by ID) that must complete before this phase starts.
10. **Exit criteria** — explicit statement of what must be true for the phase to close (`every claimed EARS statement verifies; tester reports green; decisions.md has no unresolved entries for this phase`).

### `plan/leaf-ownership.md` — shape

See A03.2 for the full specification. Shape at a glance: one row per EARS statement ID, with columns `EARS statement ID | Phase claiming it | Status | Tester | Evidence pointer`. Every spec-leaf EARS statement must appear in exactly one row (complete and exclusive per S03.2.e4).

### `plan/status.md` — shape

Phase-status ledger. One row per phase, seeded by @planner with status `planned`, updated by execution impl-orch as phases progress (`planned` → `in-progress` → `verifying` → `done` or `blocked`). `blocked` status requires a `plan/status.md` note or decisions.md entry naming the blocker.

### `plan/pre-planning-notes.md` — shape

Written by the planning impl-orch before spawning @planner. Six required sections (S04.1.e2):

1. **Feasibility answers** — answers to `feasibility.md §Open questions` items tagged `impl-orch must resolve during pre-planning`.
2. **Probe results** — results of any runtime probes impl-orch ran (versions checked, commands executed, fixture scans).
3. **Architecture re-interpretation** — how impl-orch reads the architecture tree given runtime constraints, with any deviations from design-orch's observational shape flagged.
4. **Module-scoped constraints** — file-level, module-level, or concurrency constraints that the planner must respect (e.g. "these two phases cannot run in parallel because they both touch `src/meridian/lib/state/paths.py`").
5. **Spec-leaf coverage hypothesis** — impl-orch's first-pass mapping of spec leaves to tentative phase clusters, as a seed for @planner's final decomposition.
6. **Probe gaps** — known unknowns that pre-planning could not close and that @planner will need to treat as open (potentially triggering a probe-request if they block decomposition).

The word "phase" must not appear in `pre-planning-notes.md` — pre-planning runs before @planner assigns phase identities, so using the word commits impl-orch to a decomposition it does not own (S04.1.s1).

### `plan/preservation-hint.md` — shape

See A02.3 for the full specification. Absent on first cycle; present only on redesign cycles where dev-orch authored a hint before re-spawning design-orch.

## Interfaces

- **`-f $MERIDIAN_WORK_DIR/plan/overview.md`** — attached by every phase-level spawn (coder, tester, reviewer) so the phase agent sees the parallelism posture and where its phase fits.
- **`-f $MERIDIAN_WORK_DIR/plan/phase-N-<slug>.md`** — attached by the coder and tester spawns for a specific phase.
- **`-f $MERIDIAN_WORK_DIR/plan/leaf-ownership.md`** — attached by testers (to see which EARS statements their phase claims) and by dev-orch (plan-review checkpoint).
- **`$MERIDIAN_WORK_DIR/plan/status.md`** — updated by execution impl-orch as phases progress; read by dev-orch for completion signal.

## Dependencies

- `./terrain-analysis.md` — the sibling files (`refactors.md`, `feasibility.md`) that inform `plan/overview.md`'s refactor-handling table.
- `../verification/leaf-ownership-and-tester-flow.md` — the per-row shape of `leaf-ownership.md` and how testers consume it.
- `../design-package/two-tree-shape.md` — the directory layout this file slots into.

## Open questions

None at the architecture level.
