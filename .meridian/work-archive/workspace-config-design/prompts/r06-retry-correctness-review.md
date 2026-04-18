# R06 Retry — Correctness Review

Read `r06-retry-context-brief.md` first. That is the shared ground truth — do not re-derive it.

## Your Focus

You are the **correctness reviewer**. Your job is to **enumerate concrete defects with code pointers** in the current R06 skeleton state (commits 3f8ad4c..45d18d7). No philosophy, no design debate — just find every composition leak, race, orphan window, and dead-code trap with file:line.

## What to Read

1. Source under `src/meridian/lib/launch/`:
   - `context.py` — factory + pipeline stages
   - `plan.py` — spawn-plan construction (composition before factory)
   - `process.py` — primary synchronous launch driver
   - `runner.py` — runtime execution path
   - `streaming_runner.py` — worker driver
   - `command.py`, `env.py`, `policies.py`, `permissions.py`, `fork.py` — stage modules
   - `resolve.py` — input-resolution helpers
2. `src/meridian/lib/ops/spawn/prepare.py` — spawn prep (request → plan → execution context); prior reviewer flagged direct `fork_session` here
3. `src/meridian/lib/app/server.py` + `src/meridian/cli/streaming_serve.py` — app driver
4. `src/meridian/lib/harness/adapter.py` — ports
5. `src/meridian/lib/harness/claude.py`, `codex.py`, `opencode.py` — driven adapters (session-id handling especially)
6. `src/meridian/lib/safety/permissions.py` — `TieredPermissionResolver`
7. `scripts/check-launch-invariants.sh` — current CI

## What to Produce

A markdown report at `$MERIDIAN_WORK_DIR/reviews/r06-retry-correctness.md` organized by defect class. Per defect: code pointer, what's wrong, severity (blocker/major/minor), fix sketch.

### Defect classes to hit

1. **Composition leaks** — every site outside `build_launch_context()` that calls `resolve_policies`, `resolve_permission_pipeline`, `TieredPermissionResolver`, `build_launch_env`, `build_launch_spec`/`build_command`, `build_env_plan`, or constructs `ExecutionPolicy`. Not just what CI flags — find every one.
2. **Fork ordering / orphan windows** — every path that can leave a half-written `.meridian/spawns/<id>` dir, fork without the corresponding spawn/session row, spawn/session row without the corresponding fork, or session write before fork materialization.
3. **Session-id observation races** — `observe_session_id()` wiring: confirm it is or isn't implemented per adapter. Find any process-global session state on adapter singletons. Trace how a session id actually reaches `spawn_store.finalize_spawn` today — is it via `observe_session_id` or the old inline path?
4. **Dry-run correctness under bypass** — confirm 45d18d7 is complete. Are there other dry-run paths that still preview the non-bypass command?
5. **Dead hooks / dead wrappers** — functions or parameters that exist only to satisfy rg counts (callers don't pass them, results aren't used). Include wrapper-over-wrapper (`build_env_plan` vs `build_launch_env` kind of thing).
6. **Sum-type exhaustiveness** — every `LaunchContext` match. Are they all exhaustive via `assert_never`? Any that drop to a default branch?
7. **rg-invariants gaming surface** — for each rg check in `scripts/check-launch-invariants.sh`, describe a concrete rename-or-shim that satisfies the count while violating the architectural intent.

## Style

Caveman full. Terse defect lines. Code pointers exact (`path:line`). No prose padding.

## Termination

Report path + defect counts per severity.
