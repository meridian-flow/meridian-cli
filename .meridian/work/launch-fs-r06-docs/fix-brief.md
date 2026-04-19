# Fix reviewer findings in fs launch mirror

Target files only:

- `.meridian/fs/launch/overview.md`
- `.meridian/fs/launch/process.md`
- `.meridian/fs/overview.md`

Address these reviewer findings exactly:

1. Split `src/meridian/cli/streaming_serve.py` from REST app path.
   - REST app path in `src/meridian/lib/app/server.py` starts streaming connections through `spawn_manager.start_spawn(...)`.
   - `src/meridian/cli/streaming_serve.py` instead calls `run_streaming_spawn(...)` and finalizes inline.
   - Do not say both paths avoid `streaming_runner.py`.

2. Tighten work-item attachment claims.
   - Current code still resolves preserved/resumed work attachment inside `run_harness_process()` after `session_scope()` yields the managed chat.
   - Avoid saying work attachment is fully resolved before entering `process.py` or that `process.py` is pure mechanism in a way that erases this responsibility.

3. Fix `LaunchArgvIntent` claim for spawn prepare.
   - `ops/spawn/prepare.py:build_create_payload()` still uses `LaunchArgvIntent.REQUIRED` for preview argv / `cli_command`.
   - `SPEC_ONLY` applies to execution paths, not prepare.

4. Refresh stale signal/timeout sections.
   - `timeout.py` no longer exists.
   - Timeout helpers live in `src/meridian/lib/launch/runner_helpers.py`.
   - Streaming executor uses local signal handling plus `signal_coordinator().mask_sigterm()` in `streaming_runner.py`.
   - `process.py` does not use `SignalForwarder`.

5. Split artifact expectations by executor.
   - Primary path does not generally create `stderr.log` or `tokens.json`.
   - `output.jsonl` on primary path is tied to capture path; richer artifacts belong to streaming path.

6. Correct CLI/MCP create/continue wording in `.meridian/fs/overview.md`.
   - CLI still exposes create via bare `meridian spawn` and continue via `meridian spawn --continue ...`.
   - Do not call create/continue MCP-only.

Keep docs observational. No source edits.

Read against:

- `.meridian/invariants/launch-composition-invariant.md`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/plan.py`
- `src/meridian/lib/ops/spawn/prepare.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/app/server.py`
- `src/meridian/cli/streaming_serve.py`
- `src/meridian/lib/launch/streaming_runner.py`
- `src/meridian/lib/launch/runner_helpers.py`
- `src/meridian/cli/spawn.py`
