# Review — v3 Design Alignment

You are reviewing the **v3 restructure of the orchestrator-restructure design package**. Your focus is **design alignment with user intent**: does every v3 doc actually serve the user's reframe from v2 to a spec-driven SDD shape? The user rejected the v2 package as too-heavy-without-a-clear-verification-contract and asked for a specific reframe with ten core principles.

## Context

The v2 package was rejected because edge-case scenarios evaporated before reaching testers, the single `design/overview.md` did not offload context well, structural analysis lived in a buried "Terrain section" that was hard to consume, and the distinction between user intent / behavioral commitment / technical design was collapsed. The user reframed v3 around:

1. Spec-driven development (Fowler's three levels, target: spec-anchored)
2. Kiro-shaped flow (requirements → design → tasks) — **not** spec-kit's constitution-first flow
3. Two-tree structure: `design/spec/` (business) + `design/architecture/` (technical)
4. EARS notation mandated for every spec leaf (five patterns)
5. Root-level TOC index in each tree for context offloading
6. `design/refactors.md` as first-class artifact consumed by planner
7. `design/feasibility.md` as first-class gap-finding artifact
8. `dev-principles` as convergence gate (lightweight constitutional gate)
9. Problem-size scaling (light path for small work)
10. Smoke tests against spec leaves; spec leaves subsume v2 scenarios (D9 reversal)

## What to review

Read the v3 package in this order:

1. `$MERIDIAN_WORK_DIR/design/overview.md` — the entry point
2. `$MERIDIAN_WORK_DIR/design/dev-orchestrator.md`
3. `$MERIDIAN_WORK_DIR/design/design-orchestrator.md`
4. `$MERIDIAN_WORK_DIR/design/impl-orchestrator.md`
5. `$MERIDIAN_WORK_DIR/design/planner.md`
6. `$MERIDIAN_WORK_DIR/design/terrain-contract.md`
7. `$MERIDIAN_WORK_DIR/design/feasibility-questions.md`
8. `$MERIDIAN_WORK_DIR/design/redesign-brief.md`
9. `$MERIDIAN_WORK_DIR/design/preservation-hint.md`
10. `$MERIDIAN_WORK_DIR/decisions.md` (D1-D23)

## Questions to answer

1. **Does the package actually implement each of the ten principles?** Cite the doc and section where each principle lives. Flag any principle that is named but not operationalized.
2. **Is the v2 → v3 reframe consistent across docs?** Look for drift — places where one doc uses v3 vocabulary (`spec leaves`, `design/refactors.md`, `feasibility.md`) and another still uses v2 vocabulary (`scenarios`, `Terrain section`, `structural-prep-candidate`). Legitimate v2 references in "what is changed" / "what is deleted" sections are fine; drift in substantive design prose is not.
3. **Are the boundaries between `requirements.md`, `design/spec/`, and `design/architecture/` preserved?** User intent in user terms, observable behaviors in EARS, target technical state — these three altitudes should not leak into each other.
4. **Is EARS enforcement real?** Check that design-orch's body actually mandates EARS (not just "use clear requirement statements"), that the spec-alignment reviewer has a concrete check for EARS shape, and that testers parse EARS into trigger/precondition/response. Check the `decisions.md` D17 reasoning matches what the docs say.
5. **Does the convergence gate actually gate?** D8 in dev-principles is the constitutional gate under v3 — check that design-orch refuses to converge if dev-principles findings are unresolved and that impl-orch has a corresponding check. Flag any doc that mentions dev-principles without wiring it into a convergence check.
6. **Is the light path usable without collapsing into the v2 shape?** D23 says small work can degenerate to single-file trees. Check that the light path is not trivially the same as "go back to v2 overview.md" — the spec-vs-architecture distinction should still hold even when both are one file each.
7. **Does D22's scenarios reversal cascade correctly?** Every mention of scenarios in substantive prose should be replaced with spec leaves. Flag remaining `scenarios/` references that are not in explicit v2-reversal sections.

## Output shape

Write a short report with:

- **Status**: converged / needs-revision / needs-redesign
- **Principle-by-principle check**: one line per principle, verified or flagged with location
- **Drift / inconsistency findings**: concrete issues with file + section references
- **Questions the design does not answer**: the open unknowns you surface
- **Recommendation**: what design-orch should revise before handing off to planner

Submit the report as your terminal report. Do not edit any design files — that is the orchestrator's job based on your findings.
