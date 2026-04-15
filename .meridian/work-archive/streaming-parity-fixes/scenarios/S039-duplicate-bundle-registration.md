# S039: Duplicate harness bundle registration raises `ValueError`

- **Source:** design/edge-cases.md E39 + decisions.md K2 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
Two calls to `register_harness_bundle(...)` with the same `harness_id` (e.g., `HarnessId.CLAUDE`). The adapters may differ; the test does not care which "wins".

## When
The second `register_harness_bundle(...)` call runs.

## Then
- `ValueError` is raised with a message naming the existing adapter class and the incoming adapter class.
- The registry state is unchanged from after the first registration (first-registration-wins, not last-wins).
- Dispatch lookup `get_harness_bundle(HarnessId.CLAUDE)` returns the **first** registered bundle.

## Verification
- Unit test: instantiate two distinct adapter fixtures binding the same `harness_id`, call `register_harness_bundle` on both, assert the second raises `ValueError`.
- Assert the registry still contains the first bundle.
- Assert the error message includes both adapter class names for diagnosability.
- Regression guard: a "double-import" fixture that imports a module twice via `importlib.reload` — the second import must either be a no-op or raise.

## Result (filled by tester)
verified 2026-04-11

- Evidence:
  - `tests/harness/test_launch_spec_parity.py:487` — `test_duplicate_bundle_registration_raises`
- Notes:
  - Second registration raises `ValueError`, preserves first-registration-wins state, and the error names both adapter classes.
