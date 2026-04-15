# Phase 5: Collapse `streaming_serve.py` Onto the Canonical Path

**Risk:** Low  
**Design docs:** [overview.md](../design/overview.md), [streaming-runner.md](../design/streaming-runner.md)

## Scope

Remove the independent execution logic from `streaming_serve.py` and make it a thin wrapper over the canonical streaming runner/helper. After this phase, there should be only two execution paths left:

- PTY primary path
- streaming-backed child/app path

## Files to Modify

- `src/meridian/cli/streaming_serve.py`
  Replace the bespoke run loop with a thin adapter around the shared streaming execution code.
- `src/meridian/lib/launch/streaming_runner.py`
  Expose or factor the minimum helper surface needed by the CLI wrapper without forking the policy logic.
- `src/meridian/cli/main.py`
  Keep the CLI entrypoint pointed at the slim wrapper; change only if the helper signature requires it.
- `tests/test_streaming_serve.py`
  Update tests to assert shared-runner delegation and finalize-once semantics.
- `tests/smoke/`
  Update any streaming-serve smoke docs to reference the canonical path.

## Dependencies

- Requires: Phase 1, Phase 4
- Produces: one canonical streaming execution path instead of two divergent ones
- Independent of: extraction and config refactors once Phase 4 has landed

## Interface Contract

`streaming_serve.py` should remain a user-facing command, but not an execution-policy owner. It may call a shared helper that internally uses the same manager/runner flow as `meridian spawn`.

## Patterns to Follow

- Keep command-line validation in the CLI layer.
- Keep execution policy in the runner layer.

## Constraints and Boundaries

- Do not change the PTY primary path.
- Do not reintroduce manager-owned finalization through the CLI wrapper.
- Avoid creating a second shared helper that drifts from `execute_with_streaming()`.

## Verification Criteria

- `uv run pytest tests/test_streaming_serve.py` passes.
- `uv run pyright` passes.
- Smoke test: `meridian streaming serve --harness <id> --prompt "<prompt>"` still starts, streams, and finalizes correctly while going through the canonical path.

## Staffing

- Builder: `@coder`
- Testers: `@verifier`, `@smoke-tester`

## Completion Signal

This phase is done when `streaming_serve.py` is only a thin wrapper and can no longer drift as an independent execution path.
