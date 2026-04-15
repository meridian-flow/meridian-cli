# A03.1: Orchestrator verification contract

## Summary

Every orchestrator, planner, coder, and tester in v3 shares exactly one verification contract: spec-leaf EARS statements are authoritative, phase closure gates on every claimed EARS statement verifying against committed code, and the `scenarios/` convention that v2 used as a sidecar acceptance surface is retired. This leaf describes how the contract is shared across agents and how the retirement reshapes agent prompt bodies so no part of the package still instructs agents to create or gate on scenario files.

## Realizes

- `../../spec/root-invariants.md` — S00.u3 (spec leaves as the sole acceptance contract), S00.u4 (scenarios convention retired), S00.u6 (EARS shape with stable IDs mandated).
- `../../spec/execution-cycle/spec-leaf-verification.md` — S05.2.u1 (spec leaves are the verification contract), S05.2.u2 (smoke tests default), S05.2.s2 (phase passes when every claimed statement verifies).
- `../../spec/execution-cycle/spec-drift.md` — S05.3.u1 (spec leaves authoritative), S05.3.s3 (epistemic falsification trigger, not severity).

## Current state

- **`dev-artifacts` skill** in `meridian-dev-workflow/skills/dev-artifacts/SKILL.md` defines `scenarios/` as a first-class directory with lifecycle ownership across design, planning, and execution, and names `scenarios/overview.md` as the `@dev-orchestrator` convergence check.
- **`design-orchestrator.md` (v2)** instructs design-orch to seed `scenarios/` during the design cycle and treats "every edge case becomes a scenario" as a convergence gate.
- **`planner.md` (v2)** requires every blueprint to include a `Scenarios to Verify` section and every edge case to become a tester acceptance scenario; the planner emits a `plan/scenario-ownership.md` file tracking scenario IDs per phase.
- **`impl-orchestrator.md` (v2)** begins every phase with a `scenario review → coder → testers` loop and gates phase closure on scenario-file results.
- **`smoke-tester` and `unit-tester` skills** require the tester to open `$MERIDIAN_WORK_DIR/scenarios/` and update per-scenario result sections as the system of record.

## Target state

**Anchor target for R04.** `design/refactors.md` entry R04 (retire the `scenarios/` convention from orchestrator and planner prompt bodies) names this section as its `Architecture anchor`. The R04 migration is done when no prompt body in `.agents/` (design-orch, impl-orch, dev-orch, planner, smoke-tester, unit-tester) still instructs an agent to create, read, or gate on scenario files, and every acceptance claim routes through spec-leaf EARS statements and `plan/leaf-ownership.md`.

### Spec leaves replace scenario files

The v3 verification contract is a single four-part rule shared across every agent:

1. **Spec leaves are the acceptance contract.** Every behavioral requirement lives in `design/spec/` as an EARS statement with a stable ID (`S<subsystem>.<section>.<letter><number>`). No other artifact carries acceptance claims.
2. **`plan/leaf-ownership.md` is the ownership ledger.** Every EARS statement ID is claimed by exactly one phase. See A03.2 for the per-row shape.
3. **Testers parse EARS statements mechanically.** A03.3 defines the per-pattern parsing rule that turns an EARS statement into test setup + fixture + assertion. Testers cite EARS statement IDs in their reports, not scenario IDs.
4. **Phase closure gates on every claimed statement verifying.** A phase closes only when every EARS statement listed under "Claimed EARS statements" in its blueprint has a green tester report. Additional edge cases the tester discovered during execution are reported as observations and, if they reveal falsifications, route through the escape hatch (S05.4) rather than into a scenario file.

### Shared contract across agents

- **design-orch** writes spec leaves with EARS statements and stable IDs. Design-orch does not author a `scenarios/` folder and does not enumerate "acceptance scenarios" as a separate artifact. Edge cases are captured directly inside the relevant spec leaf (as additional EARS statements or as Non-requirement edge-case entries in the leaf's trailing section).
- **@planner** reads spec leaves, claims every EARS statement ID in `plan/leaf-ownership.md`, lists claimed IDs in each phase blueprint, and does not create any `Scenarios to Verify` section or `plan/scenario-ownership.md` file.
- **execution impl-orch** reads each phase blueprint's `Claimed EARS statements` list and passes it to the tester for the phase. Phase closure uses the tester report's EARS statement coverage directly; no intermediate scenario file is consulted.
- **testers (verifier, smoke-tester, unit-tester, browser-tester)** open `$MERIDIAN_WORK_DIR/design/spec/` to read the EARS statements for the claimed IDs, apply the A03.3 parsing rule, execute the tests, and write reports keyed on EARS statement IDs. Testers do not open a `scenarios/` folder (because it does not exist) and do not update scenario files.
- **dev-orch** reviews plan/status.md and leaf-ownership.md at completion to confirm every claimed statement has a verified report. Convergence check is "every EARS statement in `design/spec/` has a claiming phase and a green tester report," not "every scenario file has a green result."

### Edge cases — what happens to the things `scenarios/` used to carry

| v2 scenario-folder role | v3 replacement |
|---|---|
| "Every edge case gets a scenario file" | Every edge case becomes an additional EARS statement inside the relevant spec leaf, or a Non-requirement edge-case entry documenting why it is out of scope. |
| "Tester updates scenario file result section" | Tester report cites EARS statement IDs and outcomes; report is attached to the spawn's terminal report (no scenario file update). |
| "Scenario ID as ownership unit" | EARS statement ID at `S<subsystem>.<section>.<letter><number>` granularity is the ownership unit. |
| "`scenarios/overview.md` as dev-orch convergence check" | `plan/leaf-ownership.md` plus `plan/status.md` plus the spec tree itself become the convergence check — every spec leaf has a claimed phase, every phase has verified testers. |
| "Design-orch seeds scenarios during design" | Design-orch authors EARS statements during design. Edge cases surface as additional EARS statements during convergence review, not as scenario files. |

### Retirement surface — where the convention must not reappear

- `meridian-dev-workflow/skills/dev-artifacts/SKILL.md` — reshaped by R03 to name `plan/leaf-ownership.md` instead of `scenarios/`.
- `meridian-dev-workflow/agents/design-orchestrator.md` — body rewritten to remove the "seed scenarios" instruction and replace with "author EARS statements with stable IDs in design/spec/".
- `meridian-dev-workflow/agents/impl-orchestrator.md` — per-phase loop rewritten to read claimed EARS IDs from blueprint, not scenario files.
- `meridian-dev-workflow/agents/planner.md` — blueprint template updated to emit `Claimed EARS statements` instead of `Scenarios to Verify`; `plan/scenario-ownership.md` renamed to `plan/leaf-ownership.md`.
- `meridian-dev-workflow/skills/smoke-test/SKILL.md`, `skills/unit-test/SKILL.md` — tester contracts rewritten to open `design/spec/` and cite EARS statement IDs.

## Interfaces

- **`-f $MERIDIAN_WORK_DIR/design/spec/<subsystem>/<leaf>.md`** — every tester attaches the relevant spec leaves for the EARS statements the phase claims.
- **`-f $MERIDIAN_WORK_DIR/plan/leaf-ownership.md`** — attached to every phase-level spawn so the agent sees which EARS statements its phase owns.
- **Tester report format** — reports cite EARS statement IDs directly as the verification unit. Example: `S05.2.e1: verified (smoke test run against <command>, observed <output>)`.

## Dependencies

- `./leaf-ownership-and-tester-flow.md` — the ownership ledger shape this contract relies on.
- `./ears-parsing.md` — the per-pattern parsing rule testers apply.
- `../artifact-contracts/shared-work-artifacts.md` — the `plan/` layout that hosts `leaf-ownership.md`.
- `../../spec/execution-cycle/spec-leaf-verification.md` — spec-side rules this contract realizes.

## Open questions

None at the architecture level.
