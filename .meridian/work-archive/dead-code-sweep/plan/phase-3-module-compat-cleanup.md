# Phase 3 — Module and Compatibility Cleanup

## Scope and Boundaries

Remove retired compatibility shims and the verified orphaned modules after
redirecting the one still-live `claude_preflight` import to its canonical path.

This phase only owns shim/module cleanup. It does not touch auth removal, state
schema cleanup, binary reinstall, or smoke retesting.

## Touched Files / Modules

- `src/meridian/lib/harness/connections/__init__.py`
- `src/meridian/lib/harness/claude.py`
- `src/meridian/lib/launch/claude_preflight.py`
- `src/meridian/lib/app/agui_types.py`
- `src/meridian/lib/launch/stream_capture.py`
- `src/meridian/lib/launch/terminal.py`
- `src/meridian/lib/launch/timeout.py`
- `src/meridian/lib/state/reaper_config.py`
- affected tests under `tests/`

## Claimed EARS Statement IDs

- `S-DEL-008`
- `S-DEL-009`
- `S-DEL-014`

## Touched Refactor IDs

- `R-05`

## Dependencies

- `Phase 1 — auth-lifecycle-surface`

## Tester Lanes

- `@verifier`
- `@unit-tester`

## Exit Criteria

- `register_connection()` is removed from the harness connections surface.
- `harness/claude.py` imports the canonical preflight module directly and the
  legacy re-export wrapper is deleted.
- The verified dead modules (`agui_types.py`, `stream_capture.py`,
  `terminal.py`, `timeout.py`, `reaper_config.py`) are removed together with
  any tests that only keep them alive.
- Entry points and live spawn modules identified in `D-01` remain untouched.
- Verification proves no remaining imports or tests reach the removed shim or
  dead modules.
