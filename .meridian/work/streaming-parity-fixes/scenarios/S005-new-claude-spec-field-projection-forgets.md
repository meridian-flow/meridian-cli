# S005: New field on `ClaudeLaunchSpec`, projection forgets it

- **Source:** design/edge-cases.md E5 + p1411 H4
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A new field is added to `ClaudeLaunchSpec`, but `project_claude.py` accounting is not updated.

## When
Projection drift helper runs at import.

## Then
- `_check_projection_drift(...)` raises `ImportError` with missing/stale sets.
- Failure occurs at import time before any spawn runs.
- Guard behavior remains active under optimized Python mode.

## Verification
- Unit tests call `_check_projection_drift` directly with synthetic spec classes.
- Assert happy path, missing-field, and stale-field cases.
- No monkey-patching of `model_fields`.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified with extra coverage
- **Tests:** `tests/harness/test_launch_spec_parity.py::test_claude_projection_drift_guard_happy_path` ([line 142](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:142)), `tests/harness/test_launch_spec_parity.py::test_claude_projection_drift_guard_missing_field` ([line 150](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:150)), `tests/harness/test_launch_spec_parity.py::test_claude_projection_drift_guard_stale_field` ([line 159](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:159)), `tests/harness/test_launch_spec_parity.py::test_claude_projection_import_fails_when_new_model_field_is_unaccounted` ([line 167](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:167))
- **Commands:**
  - `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k claude -v` -> `21 passed, 16 deselected`
- **Evidence:**
  - `project_claude.py` still calls `_check_projection_drift(ClaudeLaunchSpec, _PROJECTED_FIELDS, _DELEGATED_FIELDS)` at import time, so missing/stale field accounting fails before any spawn runs.
  - Added a real import-path smoke test that mutates `ClaudeLaunchSpec.model_fields` in a subprocess, re-imports `meridian.lib.harness.projections.project_claude`, and observes `ImportError: ... missing=['future_field']`.
