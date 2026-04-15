# S019: Codex `report_output_path` on streaming path

- **Source:** design/edge-cases.md E19 + p1411 M5
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
Codex spec sets `report_output_path`.

## When
Subprocess and streaming Codex projections run.

## Then
- Subprocess emits `-o <path>`.
- Streaming emits no wire flag for the field.
- Streaming logs:
  `Codex streaming ignores report_output_path; reports extracted from artifacts`.

## Verification
- Unit assertions for subprocess `-o` output.
- Caplog assertion for streaming debug message.
- No debug message when field is `None`.

## Result (filled by tester)
Verified 2026-04-10 with extra coverage.

- `tests/harness/test_launch_spec_parity.py:683` (`test_codex_build_command_parity_cases`) proves subprocess Codex still emits `-o report.md`.
- `tests/harness/test_codex_ws.py:276` proves streaming emits no report-output wire arg and logs `Codex streaming ignores report_output_path; reports extracted from artifacts`.
- `tests/harness/test_codex_ws.py:334` proves the ignore log is absent when `report_output_path` is unset.
- `tests/harness/test_launch_spec.py:68` confirms `report_output_path` remains Codex-only on the launch spec and was not reintroduced as a transport-neutral field.

### Smoke-tester re-verification (p1463, 2026-04-10)
- **Subprocess side real binary**: projected `codex exec --json --sandbox read-only ... -o /tmp/phase4-smoke/last-message.txt -` with a spec carrying `report_output_path="/tmp/phase4-smoke/last-message.txt"`. Ran the real binary end-to-end — `rc=0`, and the file was written:
  ```
  -rw-rw-r-- 1 jimyao jimyao 2 Apr 10 22:32 /tmp/phase4-smoke/last-message.txt
  $ cat /tmp/phase4-smoke/last-message.txt
  ok
  ```
- **Streaming side**: same spec, `report_output_path="/tmp/phase4-smoke/IGNORED.txt"`. Projection output: `['codex', 'app-server', '--listen', 'ws://127.0.0.1:58231', '-c', 'sandbox_mode="workspace-write"', '-c', 'approval_policy="on-request"']` — confirmed `-o` absent and `IGNORED.txt` literal absent. Debug log emitted: `DEBUG meridian.lib.harness.projections.project_codex_streaming Codex streaming ignores report_output_path; reports extracted from artifacts`.
- **Baseline (no report_output_path)**: verified the debug log is NOT emitted when the field is `None`.
