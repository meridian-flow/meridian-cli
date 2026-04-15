# S044: New `SpawnParams` field unclaimed by any adapter fails at import

- **Source:** design/edge-cases.md E42 + decisions.md K9 (revision round 3)
- **Added by:** @design-orchestrator (revision round 3)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A developer adds a new `SpawnParams` field (e.g., `telemetry_id: str | None = None`) and updates the global `_SPEC_HANDLED_FIELDS` set in `harness/launch_spec.py` — but forgets to add it to any adapter's `handled_fields: frozenset[str]` property.

## When
`harness/__init__.py` runs `_enforce_spawn_params_accounting()` at the tail of the eager import sequence.

## Then
- `ImportError` is raised with a message like:
  `"SpawnParams cross-adapter accounting drift. Missing: ['telemetry_id']. Stale: []."`
- The package fails to import. The error is surfaced at first import, not after a dispatch attempt.

## Verification
- Unit test: register a fixture `HarnessBundle` whose adapter declares `handled_fields` missing a known `SpawnParams` field, call `_enforce_spawn_params_accounting(registry=fixture_registry)`, assert `ImportError`.
- Regression test: temporarily remove `mcp_tools` from `_CODEX_HANDLED_FIELDS`, run the accounting function, assert the error message mentions `mcp_tools`. Restore after.
- Cross-check: the union of every registered adapter's `handled_fields` equals `SpawnParams.model_fields`.

## Result (filled by tester)
verified 2026-04-11

- Evidence:
  - `tests/harness/test_spec_field_guards.py:48` — `test_enforce_spawn_params_accounting_reports_missing_field`
  - `tests/harness/test_spec_field_guards.py:66` — `test_enforce_spawn_params_accounting_reports_missing_real_field_name`
  - `tests/harness/test_spec_field_guards.py:81` — `test_registered_bundle_handled_fields_union_matches_spawn_params`
- Notes:
  - The accounting guard reports synthetic drift and real missing `mcp_tools`, and the registered adapter union now matches `SpawnParams.model_fields`.
