# Phase 4+5+6: Rewire All Three Driving Adapters Through the Factory

You are implementing the core rewiring of R06. The three driving adapters (primary launch, background worker, app streaming HTTP) must all route through `build_launch_context()`. This is the behavioral change phase.

## Current state

Phase 3 created the infrastructure:
- `NormalLaunchContext` / `BypassLaunchContext` sum type in `src/meridian/lib/launch/context.py`
- `LaunchOutcome` / `LaunchResult` in same file
- `build_launch_context()` factory (currently delegates to `prepare_launch_context()`)
- `observe_session_id()` adapter seam on `SubprocessHarness`
- `materialize_fork()` in `src/meridian/lib/launch/fork.py`
- `SpawnRequest` DTO in `src/meridian/lib/harness/adapter.py`

The three driving adapters currently compose independently:

### 1. Background worker (spawn path)
- `src/meridian/lib/ops/spawn/prepare.py:build_create_payload()` resolves policies, permissions, constructs SpawnParams, packs into PreparedSpawnPlan
- `src/meridian/lib/ops/spawn/execute.py` calls `prepare_launch_context()` with the PreparedSpawnPlan (at the `prepare_launch_context` call around line ~445-460)
- Also has independent `resolve_permission_pipeline()` call at execute.py:~861

### 2. Primary launch
- `src/meridian/lib/launch/plan.py:resolve_primary_launch_plan()` does everything: policy resolution, permission pipeline, session intent, skill injection, SpawnParams construction, command building, MERIDIAN_HARNESS_COMMAND bypass
- `src/meridian/lib/launch/process.py` calls `build_launch_env()` from `command.py` for env, has its own fork materialization at `_resolve_command_and_session()`
- `src/meridian/lib/launch/command.py:build_launch_env()` uses `core/context.py:RuntimeContext` for primary env

### 3. App streaming HTTP
- `src/meridian/lib/app/server.py:~268-365` constructs SpawnParams directly, creates TieredPermissionResolver, calls adapter.resolve_launch_spec()
- Hands `spec` to `spawn_manager.start_spawn(config, spec)`

## What to do

### Strategy: keep the spawn path working first, then evolve

The spawn path (background worker) already goes through `prepare_launch_context()` which `build_launch_context()` delegates to. The immediate task is:

1. **Keep the background worker path working as-is** — `prepare_launch_context()` already works for spawns. Don't break what works.

2. **Make `build_launch_context()` the real factory** by making it handle the spawn case directly (inlining `prepare_launch_context()` into it). Then mark `prepare_launch_context()` as deprecated/internal.

3. **For the app streaming HTTP path**: change `server.py` to call `build_launch_context()` instead of constructing SpawnParams and calling resolve_launch_spec directly. The factory already handles SpawnParams construction, spec resolution, and env building.

4. **For the primary launch path**: this is the hardest change. `resolve_primary_launch_plan()` does much more than the factory — session intent, skill injection, prompt building. The factory should NOT absorb all of that. Instead:
   - Keep `resolve_primary_launch_plan()` for primary-launch-specific logic (session intent, prompt composition)
   - But after it resolves policies and builds the prompt, it should call `build_launch_context()` for the shared composition (SpawnParams construction, spec resolution, env building, fork materialization)
   - The MERIDIAN_HARNESS_COMMAND bypass moves into the factory (returns `BypassLaunchContext`)

### Detailed changes

#### `src/meridian/lib/launch/context.py`

Evolve `build_launch_context()` to inline the logic from `prepare_launch_context()`. Keep the same signature for now since the spawn path uses it. Then remove `prepare_launch_context()`.

Make the factory also handle the `BypassLaunchContext` case: if `MERIDIAN_HARNESS_COMMAND` is set (can be passed as a parameter), return a `BypassLaunchContext` instead.

#### `src/meridian/lib/ops/spawn/execute.py`

Find where `prepare_launch_context()` is called and change to `build_launch_context()` (same signature — should be a rename).

Find the independent `resolve_permission_pipeline()` call (around line 861) — this is the one the design says to remove. It should already be handled by the spawn plan's `execution.permission_resolver`. Check if removing it breaks anything.

#### `src/meridian/lib/app/server.py`

The create_spawn handler at lines 268-365 currently:
1. Constructs `SpawnParams` directly (line ~333)
2. Creates `TieredPermissionResolver` (line ~316)
3. Calls `adapter.resolve_launch_spec(params, permission_resolver)` (line ~338)
4. Passes `spec` to `spawn_manager.start_spawn(config, spec)` (line ~341)

Change to construct through the factory. However, the server path is different — it gets its inputs from an HTTP request, not from CLI args. The factory currently takes a `PreparedSpawnPlan` which is a spawn-CLI concept.

**Option**: Instead of making the server path use `PreparedSpawnPlan`, make `build_launch_context()` accept an alternative set of args for the "direct composition" case. Or make the server construct a minimal PreparedSpawnPlan.

Actually, the simplest approach: the server should still construct SpawnParams and hand it with a resolver to the factory. But then the factory needs an overload or alternative entry point for pre-resolved inputs. 

**Simplest approach**: keep `prepare_launch_context()` as an internal helper that `build_launch_context()` calls, and have `build_launch_context()` be the one true entry point. The server can call a different factory method or supply pre-resolved params. For now, the server path is less critical — focus on getting primary and spawn paths through the factory first.

#### `src/meridian/lib/launch/plan.py`

`resolve_primary_launch_plan()` currently returns a `ResolvedPrimaryLaunchPlan` which carries `run_params`, `command`, `permission_config`, `permission_resolver`, etc. Process.py then uses these to call `build_launch_env()` and run the harness.

The change: after `resolve_primary_launch_plan()` resolves policies, permissions, session, and prompt, it should produce a `NormalLaunchContext` (or `BypassLaunchContext`) instead of separately producing SpawnParams + command.

This means `ResolvedPrimaryLaunchPlan` should carry a `LaunchContext` instead of `run_params` + `command` + `permission_config` separately. Or better: `resolve_primary_launch_plan()` should return a `LaunchContext` directly (primary launch doesn't need a plan object — it executes immediately).

#### `src/meridian/lib/launch/process.py`

- `_resolve_command_and_session()` (fork materialization) moves to use `materialize_fork()` from fork.py
- `build_launch_env()` call from command.py gets replaced by the factory's env building
- The process runner receives a `LaunchContext` instead of a `ResolvedPrimaryLaunchPlan`

#### `src/meridian/lib/launch/command.py`

- `build_launch_env()` can be deprecated/removed — env building moves into the factory
- The `MERIDIAN_HARNESS_COMMAND` branch in this file moves into the factory

### Test updates

Run the test blast radius query:
```bash
rg -l "RuntimeContext|prepare_launch_context|LaunchContext|build_launch_context|build_launch_env|build_harness_child_env|PreparedSpawnPlan|resolve_policies|resolve_permission_pipeline|SpawnParams|merge_env_overrides|resolve_launch_spec|run_streaming_spawn|SpawnRequest|materialize_fork" tests/
```

Update tests that construct `LaunchContext` (now `NormalLaunchContext`), tests that call `prepare_launch_context` (now `build_launch_context`), and tests that reference old function names.

### Critical constraints

- **Every intermediate state must pass pyright + ruff + pytest.** If you need to make the change in sub-steps, do so.
- Do NOT delete `run_streaming_spawn` yet — that's phase 7
- Do NOT delete `SpawnManager.start_spawn` fallback yet — that's phase 7
- The `MERIDIAN_HARNESS_COMMAND` bypass in plan.py can move to the factory in this phase or phase 8 — whichever is cleaner. If it's complex, defer to phase 8.
- Use `materialize_fork()` from `launch/fork.py` instead of the inline fork code in process.py and prepare.py

### Verification

```bash
uv run pyright        # 0 errors
uv run ruff check .   # clean
uv run pytest-llm     # all tests pass
```

Exit criteria checks:
```bash
# Factory has callers from the three driving adapter locations
rg "build_launch_context\(" src/ --type py

# prepare_launch_context should be gone or internal-only
rg "prepare_launch_context\(" src/ --type py
```

Commit when done with a descriptive message.
