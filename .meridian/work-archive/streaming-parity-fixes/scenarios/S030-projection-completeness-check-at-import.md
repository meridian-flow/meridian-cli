# S030: Projection completeness check runs at import

- **Source:** design/edge-cases.md E30 + p1411 H4
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
Projection modules use `_check_projection_drift(...)` at module import:

- `project_claude.py`
- `project_codex_subprocess.py`
- `project_codex_streaming.py`
- `project_opencode_subprocess.py`
- `project_opencode_streaming.py`

## When
Modules are imported.

## Then
- Drift raises `ImportError` immediately.
- Missing and stale directions are both reported.
- Guard behavior survives optimized runtime.

## Verification
- Unit tests exercise `_check_projection_drift` helper with synthetic spec classes.
- Import smoke confirms real modules execute guard on import.
- Meta assertion: `rg "_PROJECTED_FIELDS" src/meridian/lib/harness/projections/` returns exactly 5 matches (one per projection module listed above).

## Result (filled by tester)
verified 2026-04-11

- Evidence:
  - `tests/harness/test_launch_spec_parity.py:287` — `test_claude_projection_import_fails_when_new_model_field_is_unaccounted`
  - `tests/harness/test_launch_spec_parity.py:622` — `test_projection_package_exposes_projected_fields_for_each_projection_module`
  - `tests/harness/test_spec_field_guards.py:119` — `test_harness_package_import_is_clean_in_unmodified_tree`
- Notes:
  - Import-time drift failure is exercised directly, the projection package now exposes `_PROJECTED_FIELDS` in all five projection modules, and optimized-package import stayed clean.
