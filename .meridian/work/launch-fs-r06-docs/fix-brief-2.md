# Final fix pass for fs launch mirror

Target files only:

- `.meridian/fs/launch/overview.md`
- `.meridian/fs/launch/process.md`
- `.meridian/fs/overview.md`

Address these exact reviewer findings:

1. `streaming_serve.py` path is documented wrong.
   - `src/meridian/cli/streaming_serve.py:114` calls `run_streaming_spawn()` directly.
   - `run_streaming_spawn()` in `src/meridian/lib/launch/streaming_runner.py:387` does **not** call `execute_with_streaming()`, `enrich_finalize()`, or `mark_finalizing()`.
   - But `run_streaming_spawn()` **does** create/use `SpawnManager`.
   - Rewrite that section to describe actual ownership without borrowing claims from `execute_with_streaming()`.

2. Remove stale stdin-feed claim from `process.md`.
   - `ResolvedRunInputs` has no `stdin_prompt`.
   - `execute_with_streaming()` builds `ConnectionConfig` from `launch_context`; do not mention deleted stdin-feed behavior.

3. Fix heartbeat ownership wording in `process.md`.
   - No `_run_heartbeat_task()` in current `streaming_runner.py`.
   - Heartbeat starts through `SpawnManager._start_heartbeat()` and underlying `heartbeat_loop()`.

4. Tighten signal wording in `process.md`.
   - Streaming path uses local signal handlers in `execute_with_streaming()`.
   - `signal_coordinator().mask_sigterm()` is used only for final write window.
   - Do not imply `SignalForwarder` / `SignalCoordinator` drive ordinary streaming execution.

5. Fix stale file reference in `fs/overview.md`.
   - Policy resolution stage ownership is `policies.py`, not `resolve.py`.
   - `resolve.py` is compatibility/helper surface, not stage owner.

Keep docs observational and source-accurate. No source edits.

Read against:

- `src/meridian/cli/streaming_serve.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/streaming/spawn_manager.py`
- `src/meridian/lib/launch/run_inputs.py`
- `src/meridian/lib/launch/signals.py`
- `src/meridian/lib/launch/policies.py`
- `src/meridian/lib/launch/context.py`
