# Phase 2: Codex `_transition()` Refactor

## Round: 1 (parallel with Phase 1)

## Scope

Centralize Codex adapter state changes behind a single `_transition()` helper with validation, matching Claude and OpenCode. This is the prerequisite that makes Phase 4 state tracing clean instead of scattered across seven direct assignments.

## Intent

`CodexConnection` currently mutates `self._state` directly. That makes trace insertion error-prone and leaves transition legality implicit. This phase makes Codex follow the same state-machine shape as the other bidirectional adapters.

## Files to Modify

### `src/meridian/lib/harness/connections/codex_ws.py`

Add:

- `_ALLOWED_TRANSITIONS: Final[dict[ConnectionState, set[ConnectionState]]]`
- `_transition(self, next_state: ConnectionState) -> None`

Replace every direct `self._state = ...` site with `_transition(...)`. Current mutation sites are:

- `starting`
- `connected`
- `failed` in startup cleanup
- `stopping` in cancel/stop paths
- `failed` in reader-loop failure handling
- `stopped` in cleanup

Keep the existing precondition check at the top of `start()`. That guard is still useful even after adding `_transition()`.

### `tests/harness/test_codex_ws.py`

Add focused coverage for:

- valid and invalid transitions
- startup failure path
- reader-loop failure path
- cleanup path to `stopped`

## Dependencies

- **Requires:** Nothing.
- **Produces:** A centralized `_transition()` method that Phase 4 will hook for state-change tracing.

## Patterns to Follow

- Mirror Claude's `_set_state()` validation pattern and OpenCode's `_transition()` naming.
- Same-state transitions should remain a no-op.

## Constraints

- Do not change any adapter other than `codex_ws.py`.
- Preserve existing runtime behavior; this is a refactor, not a protocol change.

## Verification Criteria

- [ ] `uv run pyright` passes with 0 errors
- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest-llm tests/harness/test_codex_ws.py` passes
- [ ] `rg -n 'self\\._state\\s*=' src/meridian/lib/harness/connections/codex_ws.py` shows only the assignment inside `_transition()`
- [ ] `stop()` from `"failed"` still works without forcing an invalid `failed -> stopping` transition
