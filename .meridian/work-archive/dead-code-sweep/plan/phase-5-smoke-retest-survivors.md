# Phase 5 — Smoke Retest and Survivor Capture

## Scope and Boundaries

Re-run the same two smoke lanes cited in the requirements:

- cancel/interrupt scenarios from `p1821`
- AF_UNIX/auth/liveness scenarios from `p1822`

The job of this phase is evidence and scoping, not bug-fixing. Deletion-caused
wins should be recorded, and surviving blockers should be packaged as the scope
for the next work item.

## Touched Files / Modules

- smoke artifacts and reports under `.meridian/spawns/`
- work-item notes only if needed to record survivor scope

## Claimed EARS Statement IDs

- `S-SMOKE-001`
- `S-SMOKE-002`
- `S-SMOKE-003`

## Touched Refactor IDs

- `R-08`

## Dependencies

- `Phase 4 — install-baseline-verification`

## Tester Lanes

- `@verifier`
- `@smoke-tester` (cancel/interrupt lane)
- `@smoke-tester` (AF_UNIX/liveness lane)

## Exit Criteria

- Both smoke lanes are rerun against the refreshed global `meridian` binary.
- The report states which previously observed blockers folded away after Parts A
  and B, including the expected collapse of the legacy cancel/auth cases.
- Any blockers that still reproduce are named concretely with enough detail to
  seed a follow-up bug-fix work item.
- No opportunistic fixes are mixed into this phase; it closes on evidence and
  scope capture.
