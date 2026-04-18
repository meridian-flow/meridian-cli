# Phase 7: Deletions — run_streaming_spawn + SpawnManager fallback

## What to delete

### 1. `run_streaming_spawn` in `src/meridian/lib/launch/streaming_runner.py`

Delete the `run_streaming_spawn()` function (should be around line 389+). It's a parallel implementation beside `execute_with_streaming` that independently gets an adapter, calls resolve_launch_spec, and runs its own SpawnManager lifecycle.

Also delete its export/reference at the module level (look for `__all__` and any function-level exports).

Find all imports/references:
```bash
rg "run_streaming_spawn" src/ --type py
```

All references must be removed or replaced with calls to the shared `execute_with_streaming` path.

### 2. `streaming_serve.py` rewire

`src/meridian/cli/streaming_serve.py` currently calls `run_streaming_spawn`. It also hardcodes `TieredPermissionResolver(config=PermissionConfig())` at line ~85.

Change it to route through the shared path. Either:
- Call `execute_with_streaming` directly (preferred)
- Or simplify the CLI to construct appropriate inputs for the standard spawn path

The hardcoded `TieredPermissionResolver(config=PermissionConfig())` should be removed — permissions should go through the factory's permission pipeline.

### 3. `SpawnManager.start_spawn` fallback

In `src/meridian/lib/streaming/spawn_manager.py`, the `start_spawn()` method (around line 180) has an unsafe-resolver fallback at lines ~196-199 that calls `resolve_launch_spec(SpawnParams(prompt=...), UnsafeNoOpPermissionResolver())` when callers omit `spec`.

Post-R06, all callers must hand in a resolved spec (or better, a `LaunchContext`). Make the `spec` parameter required (remove `| None = None` default).

Also remove `UnsafeNoOpPermissionResolver` imports in spawn_manager.py if any.

### 4. `TieredPermissionResolver` cleanup

Check:
```bash
rg "TieredPermissionResolver\(" src/ --type py
```

After the deletions, `TieredPermissionResolver` should only appear in:
- `src/meridian/lib/safety/permissions.py` (definition)
- `src/meridian/lib/launch/permissions.py` (if re-exported)
- `src/meridian/lib/app/server.py` (if still constructing directly — should now be in the factory)
- Tests

It should NOT appear in `cli/streaming_serve.py` anymore.

## Exit criteria

```bash
rg "run_streaming_spawn" src/ --type py        # → 0 matches
rg "UnsafeNoOpPermissionResolver" src/meridian/lib/streaming/ # → 0 matches
rg "spec: ResolvedLaunchSpec \| None = None" src/meridian/lib/streaming/ # → 0 matches
```

## Verification

```bash
uv run pyright        # 0 errors
uv run ruff check .   # clean
uv run pytest-llm     # all tests pass
```

Commit when done.
