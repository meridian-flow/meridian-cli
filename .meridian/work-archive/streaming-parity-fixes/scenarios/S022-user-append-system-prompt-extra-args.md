# S022: User passes `--append-system-prompt` in `extra_args`

- **Source:** design/edge-cases.md E22 + p1411 M3
- **Added by:** @design-orchestrator (design phase)
- **Tester:** @unit-tester
- **Status:** verified

## Given
`ClaudeLaunchSpec` includes both Meridian-managed and user passthrough `--append-system-prompt` values.

## When
Claude projection runs.

## Then
- Both flags appear in output.
- Meridian-managed flag appears in canonical position.
- User passthrough copy appears later and wins by last-wins semantics.
- Warning log records known managed-flag collision.

## Verification
- Positional assertions for both flags.
- Caplog assertion for warning entry.
- Parity assertion across subprocess/streaming projections.

## Result (filled by tester)
- **Date:** 2026-04-10
- **Status:** verified with extra coverage
- **Tests:** `tests/harness/test_launch_spec_parity.py::test_claude_projection_append_system_prompt_collision_logs_and_last_wins` ([line 392](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:392)), `tests/harness/test_launch_spec_parity.py::test_claude_projection_keeps_user_tail_when_resolver_emits_no_flags` ([line 414](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:414)), `tests/harness/test_launch_spec_parity.py::test_claude_cross_transport_parity_on_semantic_fields` ([line 810](/home/jimyao/gitrepos/meridian-channel/tests/harness/test_launch_spec_parity.py:810))
- **Commands:**
  - `uv run pytest-llm tests/harness/test_launch_spec_parity.py -k claude -v` -> `21 passed, 16 deselected`
- **Evidence:**
  - Projection emits managed `--append-system-prompt` in canonical section and preserves user passthrough copy in tail, so user value is last.
  - Collision is surfaced via projection log message (`known managed flag --append-system-prompt also present in extra_args`).
  - Added an empty-resolver/non-empty-tail case to confirm user passthrough stays verbatim even when the managed section contributes nothing.
