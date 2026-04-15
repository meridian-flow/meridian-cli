# A03.2: Leaf ownership and tester flow

## Summary

`plan/leaf-ownership.md` is the authoritative ledger mapping every spec-leaf EARS statement to exactly one phase at `S<subsystem>.<section>.<letter><number>` granularity. The tester flow reads this ledger plus the phase blueprint plus the referenced spec leaves, applies the per-pattern parsing rule (A03.3), executes the tests, and reports per EARS statement. This leaf specifies the ledger shape, the per-row fields, the tester handoff, and the revised-annotation propagation during redesign cycles.

## Realizes

- `../../spec/design-production/spec-tree.md` — S02.1.e2 (spec-leaf ID format includes EARS pattern letter).
- `../../spec/plan-approval/plan-review.md` — S03.2.e4 (spec-leaf coverage complete and exclusive at EARS-statement granularity).
- `../../spec/planning-cycle/planner-spawn.md` — S04.2.e5 (planner claims at EARS-statement granularity).
- `../../spec/execution-cycle/spec-leaf-verification.md` — S05.2.u1 (spec leaves are verification contract), S05.2.e1 (tester parses EARS per A03.3 rule), S05.2.e4 (report per EARS statement).
- `../../spec/execution-cycle/preserved-reverification.md` — S05.5.e1 (tester-only re-verification for revised leaves), S05.5.s3 (revised annotation propagates to leaf-ownership).

## Current state

- v2 `plan/scenario-ownership.md` tracks scenario file IDs per phase (e.g. `Phase 3: S042, S043, S051`). The unit is a scenario file, not a spec-leaf EARS statement.
- v2 phase blueprints contain a `Scenarios to Verify` section listing scenario IDs; testers open the scenario files, execute, and update per-scenario result sections in the scenario files themselves.
- Tester reports cite scenario IDs. Spec leaves do not carry acceptance claims directly; they cross-reference into the scenario folder.

## Target state

**Anchor target for R05.** `design/refactors.md` entry R05 (replace scenario ownership with spec-leaf ownership and EARS-driven tester handoffs) names this section as its `Architecture anchor`. The R05 migration is done when `plan/leaf-ownership.md` replaces `plan/scenario-ownership.md` in every workflow skill and prompt body, phase blueprints emit `Claimed EARS statements` instead of `Scenarios to Verify`, and tester reports cite EARS statement IDs directly.

### EARS statement ownership and tester execution

#### `plan/leaf-ownership.md` per-row shape

One row per EARS statement ID. The file is authored by @planner during the planning cycle and updated by execution impl-orch as phases progress. Columns:

| Column | Meaning |
|---|---|
| **EARS statement ID** | The stable `S<subsystem>.<section>.<letter><number>` ID of the statement. Example: `S05.2.e1`. |
| **Leaf file** | Path to the spec leaf file that hosts the statement, for fast navigation. Example: `design/spec/execution-cycle/spec-leaf-verification.md`. |
| **Phase claiming it** | The phase ID (e.g. `Phase 3`) that implements this statement. Every statement has exactly one claim. |
| **Status** | One of `claimed` (planned, not yet executed), `in-progress` (phase is running), `verified` (tester confirmed), `falsified` (tester confirmed the statement cannot be satisfied by committed code), `preserved` (from a prior cycle, not revised, no re-verification), `preserved-requires-reverification` (from a prior cycle, revised in place, tester-only pass pending), `revised` (in-place revision from redesign cycle, awaiting re-verification). |
| **Tester** | The tester role that executed or will execute verification (`verifier`, `smoke-tester`, `unit-tester`, `browser-tester`). |
| **Evidence pointer** | Link to the tester report, spawn ID, or file+line where evidence lives. Populated after verification. |
| **Revised annotation** | Present only when a statement was revised in place during a redesign cycle. Format: `revised: <reason>`. The annotation travels verbatim from the preservation hint into the new ownership file (S05.5.s3). |

#### Complete and exclusive coverage

Every EARS statement ID in `design/spec/` must appear in exactly one row. This is the plan-review criterion S03.2.e4 — coverage is both complete (no unclaimed statements) and exclusive (no statement claimed by two phases). The planner enforces this during decomposition; dev-orch verifies it at plan-review; the execution impl-orch verifies it at the start of each phase before spawning the coder.

A statement with zero claims is an orphan — a spec contract no phase implements. The planner either claims it in an existing phase, spawns an additional phase, or flags it back to design-orch as a scope mismatch. A statement with two claims is a double-claim — two phases promising the same behavior — which is a planner error the plan-review checkpoint rejects.

#### Tester handoff

When execution impl-orch starts a phase:

1. **Read blueprint.** Load `plan/phase-N-<slug>.md` and extract the `Claimed EARS statements` list.
2. **Load spec leaves.** For each claimed statement ID, load the leaf file hosting the statement. Attach via `-f` to the tester spawn.
3. **Spawn tester.** Pass the list of claimed statement IDs as the tester's acceptance contract. The tester receives: (a) the phase blueprint, (b) the spec leaves for each claimed statement, (c) `plan/leaf-ownership.md` for context, (d) the A03.3 parsing rule via the loaded skill body.
4. **Tester parses each statement.** For each claimed ID, the tester applies the per-pattern parsing rule (A03.3) to derive trigger + fixture + assertion. Unparseable statements are reported as `cannot mechanically parse — requires design clarification` per S05.2.e3.
5. **Tester executes.** Runs smoke tests by default (S05.2.u2); unit tests only for logic that is hard to smoke-test (tricky parsing, state-store algorithms, concurrency).
6. **Tester reports.** Report format: one entry per claimed statement ID, with outcome (`verified` / `falsified` / `unparseable` / `blocked`) plus evidence. Tester-generated edge cases beyond the claimed statements are reported as observations; if an observation reveals a falsification of a different statement, the tester names the statement ID and flags it.
7. **Execution impl-orch updates ledger.** For each report entry, update `plan/leaf-ownership.md` row status and evidence pointer. Falsified statements route through the escape hatch (S05.3, S05.4) rather than quietly failing.

#### Edge cases — how the ledger handles special statuses

- **Preserved, no re-verification** (`Status: preserved`, `Revised annotation: absent`) — the row is copied verbatim from the prior cycle's ledger when the preservation hint says the phase has no revised leaves. The next cycle skips re-verification per S05.5.u1.
- **Preserved, re-verification required** (`Status: preserved-requires-reverification`, `Revised annotation: revised: <reason>`) — the row is copied from the prior cycle with the revised annotation added. Execution impl-orch spawns a tester-only re-verification pass (no coder respawn). Outcome branches to `verified` (promotes back to `preserved`, S05.5.e2) or `falsified` (promotes to `partially-invalidated`, S05.5.e3), or `unparseable` (promotes to `replanned` and routes to design-orch, S05.5.e4).
- **New statement from redesign** (`Status: claimed`, `Revised annotation: absent`, fresh ID) — added to the ledger by the planner on the redesign cycle, claimed by a replanned or new phase.
- **Unparseable statement reported by tester** — row status is `blocked`, evidence pointer names the tester report. The statement routes back to design-orch via the spec-drift channel (S05.3.s3) and the blocking phase is paused until the leaf is clarified.

#### Tester-generated edge cases

Testers are required to generate their own edge cases beyond the claimed statements (S05.2.w1). A tester-generated edge case that passes is recorded as an observation in the tester report but does not create a new EARS statement on its own — if the edge case is a legitimate new behavioral requirement, execution impl-orch routes it to design-orch via the spec-drift channel and the new statement is added during a revision cycle. If the edge case is merely a stronger test of an already-claimed statement, it lands in the tester report as additional confidence on that statement.

A tester-generated edge case that fails and reveals a falsification of a claimed statement is reported as that statement falsifying (even though the claimed-path test may have passed). The epistemic trigger is any evidence contradicting any part of the EARS statement, not just the happy-path slice the coder tested (S05.3.s3).

## Interfaces

- **`-f $MERIDIAN_WORK_DIR/plan/leaf-ownership.md`** — attached to every tester, coder, and phase-level reviewer spawn. Attached to dev-orch for plan-review and completion check.
- **Tester report entry format** — `<EARS statement ID>: <outcome> (<evidence>)`. Outcomes: `verified`, `falsified`, `unparseable`, `blocked`.
- **Row update protocol** — execution impl-orch updates `leaf-ownership.md` atomically after each tester report. Rows are immutable within a cycle except for status and evidence pointer columns.

## Dependencies

- `./orchestrator-verification-contract.md` — the shared contract that motivates this ledger.
- `./ears-parsing.md` — the parsing rule testers apply.
- `../artifact-contracts/shared-work-artifacts.md` — the `plan/` layout that hosts `leaf-ownership.md`.
- `../artifact-contracts/preservation-and-brief.md` — the preservation hint shape that feeds revised annotations into this ledger.

## Open questions

None at the architecture level.
