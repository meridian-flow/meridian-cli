# Phase 8: Runner, Spawn-Manager, and REST Lifecycle Convergence

## Scope

Close the remaining end-to-end lifecycle gaps: runner signal handling, idempotent cancel/interrupt, exactly-one terminal status, structured missing-binary errors, and threading of caller-supplied permission resolvers through streaming and REST entrypoints.

## Protocol Validation First

- Re-run the real harness probes from phases 3-5 in the integrated runner path
- Exercise `meridian spawn`, streaming control operations, and the REST `/spawns` path against real binaries where available

## Files to Modify

- `src/meridian/lib/launch/runner.py` — shared subprocess lifecycle, missing-binary errors, session/report finalization parity
- `src/meridian/lib/launch/streaming_runner.py` — caller-supplied resolver threading, signal handling, exactly-once cancellation flow, no local spec/env duplication
- `src/meridian/lib/streaming/spawn_manager.py` — idempotent stop/cancel semantics and terminal-status convergence
- `src/meridian/lib/app/server.py` — REST create path uses a real resolver and finalizes background runs cleanly
- `src/meridian/lib/harness/errors.py` — structured `HarnessBinaryNotFound` and related launch failures
- `src/meridian/lib/harness/connections/base.py`, `src/meridian/lib/harness/connections/claude_ws.py`, `src/meridian/lib/harness/connections/codex_ws.py`, `src/meridian/lib/harness/connections/opencode_http.py` — idempotent `send_cancel()` / `send_interrupt()` behavior and exactly-once event emission
- `tests/test_spawn_manager.py`, `tests/test_app_server.py`, `tests/exec/test_signals.py`, `tests/exec/test_streaming_runner.py`, `tests/exec/test_lifecycle.py`, `tests/exec/test_pipe_drain.py` — race, signal, and end-to-end lifecycle coverage

## Dependencies

- Requires: Phase 7
- Produces: fully integrated v3 behavior and the final review candidate
- Independent of: nothing downstream

## Constraints

- First terminal status wins; later terminal writes become no-ops.
- Signal handlers translate to exactly one `send_cancel()` per active connection.
- Missing binary and passthrough-arg failures must surface via structured error paths, not ambiguous crashes.

## Verification Criteria

- `uv run ruff check .`
- `uv run pyright`
- `uv run pytest-llm tests/test_spawn_manager.py tests/test_app_server.py tests/exec/test_signals.py tests/exec/test_streaming_runner.py tests/exec/test_lifecycle.py tests/exec/test_pipe_drain.py`
- Relevant smoke guides under `tests/smoke/`

## Scenarios to Verify

- `S014`
- `S027`
- `S028`
- `S035`
- `S041`
- `S042`
- `S048`

Phase cannot close until every scenario above is marked `verified` in `scenarios/`.

## Agent Staffing

- `@coder` on `gpt-5.3-codex`
- `@verifier` on `gpt-5.4`
- `@unit-tester` on `gpt-5.2`
- `@smoke-tester` on `claude-opus-4-6`
- Escalate to `@reviewer` on `gpt-5.4` for race/cancellation issues or to `@reviewer` on `claude-opus-4-6` for end-to-end harness boundary issues
