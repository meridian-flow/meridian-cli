# S021: Claude subprocess vs streaming byte-equal arg tails

- **Source:** design/edge-cases.md E21 + p1411 finding M3
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
A single canonical `ClaudeLaunchSpec` (same instance), and two base command prefixes:
- `SUBPROCESS_BASE = ("claude",)`
- `STREAMING_BASE = ("claude", "--output-format", "stream-json")` (or equivalent)

## When
`project_claude_spec_to_cli_args(spec, base)` is called with each base.

## Then
- `subprocess_args[:len(SUBPROCESS_BASE)] == SUBPROCESS_BASE`
- `streaming_args[:len(STREAMING_BASE)] == STREAMING_BASE`
- `subprocess_args[len(SUBPROCESS_BASE):] == streaming_args[len(STREAMING_BASE):]`
- The spec-derived tail is byte-equal regardless of base command.
- This property is the parity contract in executable form.

## Verification
- Unit test with the above assertions over the canonical spec.
- Property-based test (hypothesis-style): generate arbitrary valid `ClaudeLaunchSpec` instances and assert the byte-equal tail property holds for every sample.
- Any future change to the projection must maintain this test — it is the single most load-bearing test in the shared-projection promise.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified
- **Tests:** `tests/harness/test_launch_spec_parity.py::test_claude_cross_transport_parity_on_semantic_fields` ([line 810](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:810)), `tests/harness/test_claude_ws.py::test_claude_ws_build_command_includes_resume_and_fork_flags` ([line 32](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_claude_ws.py:32))
- **Commands:**
  - `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k claude -v` -> `21 passed, 16 deselected`
  - `uv run pytest-llm tests/harness/test_claude_ws.py -v` -> `1 passed`
- **Evidence:**
  - Cross-transport parity test now asserts explicit base prefixes and byte-equal tails for the same Claude spec.
  - Claude streaming connection command path is wired to the shared projection function, eliminating local reorder risk.
