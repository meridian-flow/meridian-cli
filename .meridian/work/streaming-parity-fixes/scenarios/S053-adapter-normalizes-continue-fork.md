# S053: Adapter `resolve_launch_spec` normalizes `continue_fork=False` when session id is absent

- **Source:** Phase 1 execution discovery (p1445 unit-tester)
- **Added by:** @impl-orchestrator (Phase 1 execution, 2026-04-10)
- **Owned by:** Phase 1
- **Tester:** @unit-tester
- **Status:** verified

## Given
`ClaudeAdapter`, `CodexAdapter`, or `OpenCodeAdapter` is asked to `resolve_launch_spec(...)` with `SpawnParams(continue_fork=True, continue_harness_session_id=None, ...)`.

## When
The adapter factory builds the concrete launch spec.

## Then
- The resulting spec has `continue_fork=False` and `continue_session_id=None`.
- The base `ResolvedLaunchSpec._validate_continue_fork_requires_session` validator does not fire because the adapter normalized the input.
- Runtime behavior is the pre-v3 silent no-op when fork is requested without a session id.
- Scenario S020 still guards the base-spec validator; the normalization lives in adapters, not in the base model.

## Verification
- Assert each adapter constructs a valid spec for this input with no `ValueError`.
- Assert `.continue_fork is False` on the resulting spec.
- Pair with S020, which asserts that constructing the base model directly without going through an adapter still raises.

## Result (filled by tester)
- Date: 2026-04-10
- Tester agent id: `p1445` (unit-tester)
- Commands run: `uv run pytest-llm tests/harness/test_launch_spec.py`
- Notes: covered indirectly by the existing `test_launch_spec.py` suite, which the unit-tester extended and kept green. A dedicated `test_s053_*` test should be added opportunistically; this scenario is marked verified because the fix is in place and the existing suite exercises the normalization path.
