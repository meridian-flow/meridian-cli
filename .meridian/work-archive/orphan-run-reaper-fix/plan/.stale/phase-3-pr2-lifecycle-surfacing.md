# Phase 3 — PR2 Lifecycle Surfacing

## Scope and boundaries

- Widen the lifecycle/status surface to make `finalizing` a first-class status.
- Centralize active/terminal membership and remove consumer-side duplicated
  literals where this phase owns the surface.
- Keep origin/plumbing out of scope here so this phase can run in parallel with
  Phase 4.

## Touched files/modules

- `src/meridian/lib/core/domain.py`
- `src/meridian/lib/core/spawn_lifecycle.py`
- `src/meridian/cli/spawn.py`
- `src/meridian/lib/ops/spawn/models.py`
- targeted lifecycle/CLI unit and smoke coverage

## Claimed EARS statement IDs

- `S-LC-001`
- `S-LC-002`
- `S-LC-003`
- `S-CF-001`
- `S-CF-002`
- `S-CF-004`

## Touched refactor IDs

- `R-01` (lifecycle/CLI/model slice)
- `R-09` (renderer/lifecycle slice)

## Dependencies

- `phase-2-pr1-runner-heartbeat`

## Tester lanes

- `@verifier`
- `@unit-tester`
- `@smoke-tester`

## Exit criteria

- `SpawnStatus`, `ACTIVE_SPAWN_STATUSES`, and `_ALLOWED_TRANSITIONS` all admit
  `finalizing`.
- `cli/spawn.py` derives the active view and status validation from the shared
  lifecycle/domain sources.
- `ops/spawn/models.py` renders literal `finalizing` and deletes the
  "awaiting finalization" heuristic.
- CLI smoke coverage proves `--status finalizing` and active-list surfaces work
  without origin/projection work landing yet.
