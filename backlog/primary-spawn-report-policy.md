# Primary Spawn + Report Policy Backlog

Date added: 2026-03-02
Status: `todo`
Priority: `high`

## Scope

Model the primary agent session as a canonical spawn and support different report requirements by spawn kind.

## Problem

- Primary sessions launched by `meridian start` are outside spawn lifecycle/state.
- Primary has no canonical `MERIDIAN_SPAWN_ID` for in-session commands.
- Report requirements cannot cleanly differ between primary and child spawns.

## Target Behavior

- `meridian start` creates a root primary spawn record.
- Primary process receives `MERIDIAN_SPAWN_ID`.
- Primary finalizes via the same spawn finalization/cleanup path on exit/close.
- Spawn records include kind and report policy:
  - `primary`: report optional
  - `child`: report required (with fallback extraction)

## Proposed Slices

1. Add spawn kind metadata (`primary`/`child`) and plumb through start/finalize/query output.
2. Create/finalize a primary spawn in `launch_primary` lifecycle.
3. Inject `MERIDIAN_SPAWN_ID` into primary and child process environments.
4. Implement report policy enforcement by spawn kind in finalization.
5. Update CLI/docs/tests for primary spawn visibility and report semantics.
