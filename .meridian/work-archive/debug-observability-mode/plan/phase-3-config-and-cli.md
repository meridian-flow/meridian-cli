# Phase 3: Debug Propagation and Tracer Lifecycle

## Round: 2 (after Phase 1)

## Scope

Thread `--debug` through every bidirectional spawn entry point, add `ConnectionConfig.debug_tracer`, persist the flag across the background-worker boundary, and make `SpawnManager` own tracer lifecycle. This phase does not add trace events. It only makes the tracer reachable and correctly cleaned up.

## Intent

The v2 design correction matters here: `meridian spawn` does not build `ConnectionConfig` in the CLI layer. Foreground and background spawns go through `SpawnCreateInput` and the ops layer into `execute_with_streaming()`, which builds `ConnectionConfig` internally. This phase fixes the plan around that real path.

## Files to Modify

### `src/meridian/lib/harness/connections/base.py`

Add `debug_tracer: DebugTracer | None = None` to `ConnectionConfig` behind a `TYPE_CHECKING` import.

### `src/meridian/lib/ops/spawn/models.py`

Add `debug: bool = False` to `SpawnCreateInput`.

### `src/meridian/cli/spawn.py`

Add a hidden `--debug` flag to the `meridian spawn` create command and thread it into every `SpawnCreateInput(...)` construction in this file, including the `--fork` path.

### `src/meridian/lib/ops/spawn/execute.py`

This file owns the foreground/background execution boundary. Update all of the following:

- `BackgroundWorkerParams`: add `debug: bool = False`
- `execute_spawn_background()`: persist `payload.debug` to the background params JSON
- `_background_worker_main()`: reload the flag and pass it to `_execute_existing_spawn()`
- `_execute_existing_spawn()`: accept `debug: bool = False` and forward it to `execute_with_streaming()`
- `execute_spawn_blocking()`: forward `payload.debug` to `execute_with_streaming()`

### `src/meridian/lib/launch/streaming_runner.py`

Update `execute_with_streaming()` to accept `debug: bool = False` and create exactly one tracer before the retry loop. Requirements:

- attach the tracer to the locally built `ConnectionConfig`
- set `echo_stderr` from `stream_stdout_to_terminal`
- reuse the same tracer object across retries
- rely on `SpawnManager` cleanup to close it after each attempt

### `src/meridian/cli/main.py`

Add visible `--debug` flags to:

- `app_command(...)`
- `streaming_serve_cmd(...)`

Pass them through to `run_app()` and `streaming_serve()`.

### `src/meridian/cli/streaming_serve.py`

Add `debug: bool = False` to `streaming_serve()`. This path still constructs `ConnectionConfig` directly in the CLI layer, so it should create a `DebugTracer` locally and attach it to the config object.

### `src/meridian/cli/app_cmd.py`

Add `debug: bool = False` to `run_app()` and construct `SpawnManager(..., debug=debug)`.

### `src/meridian/lib/streaming/spawn_manager.py`

Add tracer ownership and lifecycle hooks:

- `SpawnManager.__init__(..., *, debug: bool = False)`
- `SpawnSession.debug_tracer: DebugTracer | None`
- `get_tracer(spawn_id) -> DebugTracer | None`
- in `start_spawn()`, if `config.debug_tracer is None and self._debug`, create `{spawn_dir}/debug.jsonl`
- on startup failure before session registration, close any tracer created by the manager
- in `_cleanup_completed_session()` and `stop_spawn()`, close the tracer before dropping the session

### Tests to Update or Add

- `tests/test_cli_spawn.py`
- `tests/test_cli_main.py`
- `tests/test_streaming_serve.py`
- `tests/test_app_server.py`
- `tests/test_spawn_manager.py`

## Interface Contract

- `ConnectionConfig.debug_tracer: DebugTracer | None = None`
- `SpawnCreateInput.debug: bool = False`
- `BackgroundWorkerParams.debug: bool = False`
- `async def execute_with_streaming(..., debug: bool = False, ...) -> int`
- `async def streaming_serve(..., debug: bool = False) -> None`
- `def run_app(..., debug: bool = False) -> None`
- `class SpawnManager(..., *, debug: bool = False)`
- `def get_tracer(self, spawn_id: SpawnId) -> DebugTracer | None`

## Dependencies

- **Requires:** Phase 1.
- **Produces:** `ConnectionConfig.debug_tracer`, `debug` flags on all relevant entry points, persisted background-worker propagation, and manager-owned tracer lifecycle hooks.
- **Independent of:** Phase 2.

## Patterns to Follow

- Match the existing `TYPE_CHECKING` import pattern for optional cross-package annotations.
- Follow the current foreground/background split in `execute.py` rather than inventing a new launch abstraction.
- Keep cleanup ownership in `SpawnManager`; runner and CLI layers should only construct or pass tracers.

## Constraints

- No trace emission yet.
- `meridian spawn --debug` stays hidden from help text.
- Background spawns must preserve the flag across the worker boundary.
- Do not move tracer creation for the `meridian spawn` path into the CLI layer.

## Verification Criteria

- [ ] `uv run pyright` passes with 0 errors
- [ ] `uv run ruff check .` passes
- [ ] `uv run pytest-llm tests/test_cli_spawn.py tests/test_cli_main.py tests/test_streaming_serve.py tests/test_app_server.py tests/test_spawn_manager.py` passes
- [ ] `meridian spawn -h` accepts `--debug` but keeps it hidden from help output
- [ ] `meridian streaming serve --help` shows `--debug`
- [ ] `meridian app --help` shows `--debug`
- [ ] `bg-worker-params.json` round-trips the `debug` flag
- [ ] `execute_with_streaming(debug=True)` constructs one tracer before the retry loop and reuses it across retries
