# Phase 2 — State and Schema Cleanup

## Scope and Boundaries

Remove the remaining dead state/runtime ballast after the auth surface is gone:
unused PID/schema fields, finalize-origin compatibility shims, ignored
compatibility parameters, stale parent-spawn context drift, stale work-path
exports, launch-spec test scaffolding, and the stale `missing_worker_pid`
terminology.

This phase does not revisit auth removal, module/orphan cleanup, or smoke
retesting.

## Touched Files / Modules

- `src/meridian/lib/streaming/signal_canceller.py`
- `src/meridian/lib/state/spawn_store.py`
- `src/meridian/lib/state/event_store.py`
- `src/meridian/lib/state/session_store.py`
- `src/meridian/lib/state/reaper.py`
- `src/meridian/lib/core/context.py`
- `src/meridian/lib/launch/command.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/state/paths.py`
- `src/meridian/lib/state/__init__.py`
- `src/meridian/lib/harness/launch_spec.py`
- state/runtime tests under `tests/`

## Claimed EARS Statement IDs

- `S-DEL-005`
- `S-DEL-006`
- `S-DEL-007`
- `S-DEL-010`
- `S-DEL-011`
- `S-DEL-012`
- `S-DEL-013`
- `S-DEL-015`

## Touched Refactor IDs

- `R-04`
- `R-06`

## Dependencies

- `Phase 1 — auth-lifecycle-surface`

## Tester Lanes

- `@verifier`
- `@smoke-tester`
- `@unit-tester`

## Exit Criteria

- `background.pid` fallback code is deleted and no test still treats it as live.
- `wrapper_pid` is removed from the schema, write sites, and tests.
- `LEGACY_RECONCILER_ERRORS` and `resolve_finalize_origin()` are deleted along
  with the legacy tests that only protect old rows.
- `append_event(..., store_name=...)` loses the ignored parameter and all call
  sites are updated.
- `parent_spawn_id`, `child_context()`, and `MERIDIAN_PARENT_SPAWN_ID` are
  removed along with any stale command-env plumbing that only supported them.
- `resolve_work_items_dir()` and `resolve_work_archive_scratch_dir()` are
  removed from exports and tests.
- `_SPEC_HANDLED_FIELDS` and `_REGISTRY` are removed from launch-spec
  scaffolding and tests no longer pin them.
- Reaper-facing error labeling says `missing_runner_pid` everywhere the live
  path still exists.
- Verification covers both mechanical cleanup and runtime state projections so
  the rename/deletion set does not silently skew CLI or state behavior.
