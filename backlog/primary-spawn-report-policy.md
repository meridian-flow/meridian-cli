# Primary Spawn + Report Policy Backlog

Date added: 2026-03-02
Status: `checkpoint-0-frozen`
Priority: `high`

## Checkpoint 0 Decision Freeze (Locked)

- Concept name: `spawn`
- ID prefix: `p`
- Primary identity: spawn with `kind=primary`
- Child identity: spawn with `kind=child`
- Report policy:
  - Primary: `optional`
  - Child: `required_with_fallback`

These terms and policy rules are fixed and should be treated as non-negotiable inputs for implementation slices.

## Scope

Model the primary agent session as a canonical spawn and enforce report requirements by spawn kind using the frozen terms above.

## Problem

- Primary sessions launched by `meridian start` are outside spawn lifecycle/state.
- Primary has no canonical `MERIDIAN_SPAWN_ID` for in-session commands.
- Report requirements are not enforced through a single spawn-kind policy.

## Target Behavior

- `meridian start` creates a root spawn with `kind=primary` and `spawn_id` prefix `p`.
- Child launches create spawns with `kind=child` and `spawn_id` prefix `p`.
- Primary and child processes receive `MERIDIAN_SPAWN_ID`.
- Primary and child finalize through the same spawn finalization/cleanup path.
- Report policy is evaluated by spawn kind:
  - `kind=primary` -> `optional`
  - `kind=child` -> `required_with_fallback`

## Proposed Slices

1. Add spawn kind metadata (`primary`/`child`) and plumb through start/finalize/query output.
2. Create/finalize a primary spawn in `launch_primary` lifecycle.
3. Inject `MERIDIAN_SPAWN_ID` into primary and child process environments.
4. Implement report policy enforcement by spawn kind in finalization.
5. Update CLI/docs/tests for primary spawn visibility and report semantics.
