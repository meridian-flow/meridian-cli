# S036: Delegated field has no consumer

- **Source:** design/edge-cases.md E36 + design/transport-projections.md completeness-guard contract
- **Added by:** @design-orchestrator (revision pass 1)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A field is marked delegated in one part of a transport path but is not present in any consumer `_ACCOUNTED_FIELDS` union.

## When
Transport-wide accounting guard executes.

## Then
- Import-time `ImportError` identifies unaccounted delegated field.
- Silent delegated-field drops are prevented.

## Verification
- Synthetic test where delegated field is removed from all consumer sets.
- Assert guard failure with field name in message.

## Result (filled by tester)
Verified 2026-04-10 with extra coverage.

- `tests/harness/test_launch_spec_parity.py:289` (`test_codex_streaming_projection_drift_guard_rejects_dropped_delegated_field`) now covers the delegated-field contract directly: the synthetic delegated field passes when accounted as delegated and fails once removed from all accounted sets.
- `tests/harness/test_launch_spec_parity.py:241` and `tests/harness/test_launch_spec_parity.py:265` add real import-reload smoke for the Codex subprocess and streaming projection modules, so the drift guard is exercised at module import time rather than only through the helper.
- The previous evidence cited only generic missing-field helper tests and did not actually prove this delegated-field scenario.

### Smoke-tester re-verification (p1463, 2026-04-10)
- Re-ran `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k codex -v`: 27 passed, 29 deselected (all Codex drift-guard and matrix tests pass).
- Re-ran `uv run pytest-llm tests/harness/test_launch_spec.py -v`: 18 passed (Codex spec round-trip including `report_output_path` field ownership).
- Inspection of `src/meridian/lib/harness/projections/project_codex_streaming.py`: the `_ACCOUNTED_FIELDS` union (`_APP_SERVER_ARG_FIELDS | _JSONRPC_PARAM_FIELDS | _METHOD_SELECTION_FIELDS | _LIFECYCLE_FIELDS`) is computed at import time and passed to `_check_projection_drift(CodexLaunchSpec, ...)`, raising `ImportError` on drift. Same guard runs at the bottom of `project_codex_subprocess.py`. Both import the module at test collection time, so any dropped field or stale entry fails before any test runs.
- Live thread bootstrap round trip confirmed the `continue_session_id` / `continue_fork` branch selection (`thread/start` vs `thread/resume` vs `thread/fork`), which is covered by `_METHOD_SELECTION_FIELDS` in the accounted set.
