# S033: Debug log for passthrough args on streaming

- **Source:** design/edge-cases.md E33 + p1411 M7
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @verifier (+ @unit-tester)
- **Status:** verified

## Given
Streaming spec has non-empty `extra_args`.

## When
Projection functions run:

- `project_codex_spec_to_appserver_command`
- `project_opencode_spec_to_serve_command`

## Then
- DEBUG log records forwarded passthrough args once per projection call.
- Empty `extra_args` emits no passthrough debug log.

## Verification
- Caplog assertions for both functions.
- Negative case with empty args.

## Result (filled by tester)
verified 2026-04-11

- Evidence:
  - `tests/harness/test_launch_spec_parity.py:1254` — `test_codex_streaming_projection_logs_passthrough_args_once_and_skips_empty_tail`
  - `tests/harness/test_launch_spec_parity.py:1475` — `test_opencode_streaming_projection_logs_passthrough_args_once_and_skips_empty_tail`
- Notes:
  - Both streaming projections log once for non-empty `extra_args` and emit no passthrough log for empty tails.
