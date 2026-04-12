# Phase 1: Event Schema and psutil Liveness

## Round

1

## Scope

Add the new lifecycle foundation without changing runtime behavior yet: add `psutil` to the project, create `src/meridian/lib/state/liveness.py`, and extend `spawn_store.py` so the event stream can represent `runner_pid` and `exited` without changing terminal semantics. This phase owns the schema and projection contract that later phases consume.

## Boundaries

- Modify only dependency, state-schema, and projection code required to model `exited` and `runner_pid`.
- Do not change launch flows in `runner.py`, `process.py`, `streaming_runner.py`, or `execute.py`; they still emit the old runtime signals until Phase 2.
- Do not rewrite the reaper or CLI display behavior yet; those phases depend on this schema but own their own behavior changes.

## Touched Files and Modules

- `pyproject.toml`
- `uv.lock`
- `src/meridian/lib/state/liveness.py`
- `src/meridian/lib/state/spawn_store.py`
- `tests/test_state/test_spawn_store.py`

## Claimed EARS Statement IDs

- SLR-2
- SLR-3
- SLR-4
- SLR-5
- SLR-11
- SLR-12
- SLR-13
- SLR-14
- SLR-22

## Touched Refactor IDs

- RF-1
- RF-2

## Dependencies

- None

## Tester Lanes

- `@verifier`: run focused lint, type, and regression checks for the new dependency and state-layer changes.
- `@unit-tester`: add or update event-store tests for `SpawnExitedEvent`, first-terminal-event invariants, and `psutil` liveness edge cases such as `NoSuchProcess`, `AccessDenied`, and PID reuse guards.

## Exit Criteria

- `psutil` is a declared project dependency and `src/meridian/lib/state/liveness.py` exposes one authoritative cross-platform liveness helper.
- `SpawnStartEvent` can carry `runner_pid`, and `SpawnRecord` projects `runner_pid`, `exited_at`, and `process_exit_code`.
- `SpawnExitedEvent` exists, parses from JSONL, and `record_spawn_exited()` appends it through the same locked event-store path as other spawn events.
- Projection keeps `status` unchanged when `exited` lands without `finalize`, and `finalize` remains the sole terminal event.
- No launch-path, reaper, or CLI behavior changes are bundled into this phase.

## Verification Commands

- `uv run ruff check src/meridian/lib/state/spawn_store.py src/meridian/lib/state/liveness.py tests/test_state/test_spawn_store.py`
- `uv run pyright`
- `uv run pytest-llm tests/test_state/test_spawn_store.py`

## Risks to Watch

- Letting `exited` accidentally become terminal in projection.
- Adding `runner_pid` only to `start` or only to `update` paths and leaving field ownership ambiguous.
- Encoding `psutil` create-time semantics in a way that diverges from the stated `started_at` tolerance rule.
