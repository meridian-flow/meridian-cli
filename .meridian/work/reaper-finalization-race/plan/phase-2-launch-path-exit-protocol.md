# Phase 2: Launch-Path Exit Protocol

## Round

2

## Scope

Move every launch path onto the new lifecycle protocol: record `runner_pid`, emit `exited` at the correct post-drain/pre-finalize point, and stop writing runtime coordination files. This phase owns foreground, background, primary, and streaming parity.

## Boundaries

- Modify launch and execution flows only: `runner.py`, `streaming_runner.py`, `process.py`, `execute.py`, and the deleted heartbeat module.
- Reuse the Phase 1 event schema; do not add more spawn-store schema churn here except what is strictly needed to call the new API.
- Do not rewrite read-path display or the reaper yet; they should observe the new events only after this phase lands.

## Touched Files and Modules

- `src/meridian/lib/launch/runner.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/launch/heartbeat.py`
- `tests/lib/test_spawn_lifecycle.py`
- `tests/test_launch_process.py`
- `tests/exec/test_streaming_runner.py`
- `tests/smoke/spawn/lifecycle.md`
- `tests/smoke/streaming-adapter-parity.md`

## Claimed EARS Statement IDs

- SLR-1
- SLR-15
- SLR-16
- SLR-17
- SLR-21
- SLR-29
- SLR-30
- SLR-32
- SLR-33

## Touched Refactor IDs

- RF-3
- RF-4

## Dependencies

- Phase 1

## Tester Lanes

- `@verifier`: run targeted lint/type checks plus the launch-path unit suites touched by the protocol shift.
- `@unit-tester`: extend launch tests to assert `runner_pid` and `exited` timing for foreground, background, primary, and streaming flows.
- `@smoke-tester`: run the real CLI lifecycle guides so the new protocol is exercised through actual spawn creation, wait, and completion paths.

## Exit Criteria

- Foreground runner records `runner_pid`, writes `exited` immediately after `spawn_and_stream` returns, and no longer writes `harness.pid` or heartbeat files.
- Primary process launch records `runner_pid`, writes `exited` after process wait returns, and no longer writes `harness.pid` or heartbeat files.
- Streaming launch records `runner_pid`, writes `exited` when drain/subprocess completion is known, and no longer writes `harness.pid` or heartbeat files.
- Background launch records wrapper and worker PIDs only in the event stream, writes `exited` from the wrapper/finalizer process, and no longer writes `background.pid`.
- `src/meridian/lib/launch/heartbeat.py` is deleted because no launch path imports or uses it anymore.

## Verification Commands

- `uv run ruff check src/meridian/lib/launch src/meridian/lib/ops/spawn/execute.py tests/lib/test_spawn_lifecycle.py tests/test_launch_process.py tests/exec/test_streaming_runner.py`
- `uv run pyright`
- `uv run pytest-llm tests/lib/test_spawn_lifecycle.py tests/test_launch_process.py tests/exec/test_streaming_runner.py`
- `uv run meridian spawn --help`
- Follow `tests/smoke/spawn/lifecycle.md`
- Follow `tests/smoke/streaming-adapter-parity.md`

## Risks to Watch

- Emitting `exited` too early, before drain completion, or too late, after report extraction already started.
- Recording the wrong `runner_pid` on background or primary paths and breaking post-exit ownership.
- Leaving one launch path still writing PID or heartbeat files and creating parity drift.
