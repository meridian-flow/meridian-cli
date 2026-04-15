# Phase 4: Streaming Runner and `meridian spawn` Routing

**Risk:** Medium  
**Design docs:** [overview.md](../design/overview.md), [streaming-runner.md](../design/streaming-runner.md)

## Scope

Build the canonical streaming execution policy layer and route streaming-capable child spawns through it. This is the convergence point: foreground, background, and existing-spawn execution paths in `execute.py` must choose the streaming runner when the harness advertises `supports_bidirectional`.

## Files to Modify

- `src/meridian/lib/launch/streaming_runner.py`
  New module implementing `execute_with_streaming()` with retry, report watchdog, guardrails, budget handling, heartbeat, signal handling, and the single authoritative finalize write.
- `src/meridian/lib/ops/spawn/execute.py`
  Route blocking, background, and resume/re-execution paths to `execute_with_streaming()` for bidirectional harnesses and keep `runner.py` for direct/non-bidirectional harnesses.
- `src/meridian/lib/launch/extract.py`
  Wire in streaming-backed extraction if `StreamingExtractor` was deferred from Phase 2.
- `src/meridian/lib/streaming/spawn_manager.py`
  Add any small helper needed by the runner, but keep policy out of the manager.
- `tests/`
  Add focused tests for routing decisions and finalize-once behavior if current coverage does not already pin them down.
- `tests/smoke/spawn/`
  Add or update a smoke-test guide for streaming-backed child spawns and `inject`.

## Dependencies

- Requires: Phase 1, Phase 2, Phase 3
- Produces: the canonical streaming-backed child-spawn path
- Independent of: `streaming_serve.py` cleanup

## Interface Contract

The new runner should mirror the current finalization entry point closely:

```python
async def execute_with_streaming(
    run: Spawn,
    *,
    plan: PreparedSpawnPlan,
    repo_root: Path,
    state_root: Path,
    artifacts: ArtifactStore,
    registry: HarnessRegistry,
    cwd: Path | None = None,
    env_overrides: dict[str, str] | None = None,
    budget: Budget | None = None,
    space_spent_usd: float = 0.0,
    guardrails: tuple[Path, ...] = (),
    guardrail_timeout_seconds: float = DEFAULT_GUARDRAIL_TIMEOUT_SECONDS,
    secrets: tuple[SecretSpec, ...] = (),
    harness_session_id_observer: Callable[[str], None] | None = None,
    event_observer: Callable[[StreamEvent], None] | None = None,
    stream_stdout_to_terminal: bool = False,
    stream_stderr_to_terminal: bool = False,
) -> int: ...
```

Routing rule in `execute.py`:

- If `registry.get_subprocess_harness(harness_id).capabilities.supports_bidirectional` is true, use `execute_with_streaming()`.
- Otherwise keep using `execute_with_finalization()`.

## Patterns to Follow

- Mirror `src/meridian/lib/launch/runner.py` for retry, guardrails, budget, and signal ownership.
- Reuse the subscriber/completion pattern from `src/meridian/cli/streaming_serve.py`, but keep terminal-state ownership in the runner, not the manager.

## Constraints and Boundaries

- Primary sessions (`meridian` with no subcommand) remain on the PTY path.
- The `direct` harness remains on the old subprocess runner.
- Do not leave two different finalization policies for child spawns.

## Verification Criteria

- `uv run pyright` passes.
- Focused pytest coverage for routing/finalize-once behavior passes.
- Smoke test with the installed CLI:
  - `meridian spawn --foreground --stream -m <bidirectional-model> -p "<prompt>"`
  - confirm structured events are written to `output.jsonl`
  - confirm `meridian spawn inject <spawn_id> "<message>"` works during the run
  - confirm final report/session id/token extraction still land in spawn state

## Staffing

- Builder: `@coder`
- Testers: `@verifier`, `@smoke-tester`

## Completion Signal

This phase is done when `meridian spawn` uses the streaming pipeline for bidirectional harnesses without changing the PTY primary path or the `direct` harness path.
