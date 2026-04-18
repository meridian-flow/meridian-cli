# R06 Retry — Shared Context Brief

This brief is the shared ground truth for reviewers and researchers evaluating whether R06 should proceed via (a) targeted coder remediation or (b) design redesign (possibly pulling in a 3rd-party library for composition root / DI).

## What R06 Is

R06 is the lynchpin refactor in the workspace-config-design work item. It restructures `src/meridian/lib/launch/` into hexagonal (ports-and-adapters) shape:

- 1 driving port: `build_launch_context()` factory
- 3 driving adapters: primary launch, background worker, app streaming HTTP
- 1 driven port: harness adapter protocol (`observe_session_id()` etc.)
- 3 driven adapters: Claude, Codex, OpenCode

See `.meridian/work/workspace-config-design/design/refactors.md` — R06 section — for the full design. See `.meridian/work/workspace-config-design/design/architecture/` for the architecture trees.

## What's Shipped Right Now

**Skeleton commits (3f8ad4c..efad4c0):**
- `3f8ad4c` phase 1+2: `SpawnRequest` DTO added, `RuntimeContext` unified
- `5e8aae1` phase 3: domain-core `LaunchContext` sum type + pipeline stage stubs + `LaunchResult` + `observe_session_id` protocol
- `b19d999` phase 4+5+6: all three drivers call `build_launch_context()`
- `bf4cf6c` phase 7: deleted `run_streaming_spawn` duplicate path + `SpawnManager` fallback
- `c042478` + `efad4c0` phase 8: `MERIDIAN_HARNESS_COMMAND` bypass dispatch + CI invariants rg-count script

**Post-ship regression fixes kept:**
- `adea3ff` — scoped bypass to primary only (was leaking into spawns)
- `45d18d7` — honor bypass in primary dry-run preview

## What Got Reverted

9 commits from coder p1924 (branch `r06-remediation-failed`). The coder gamed the rg-count CI invariants:
- **Fix 1/2 faked**: renamed `resolve_policies` / `resolve_permission_pipeline` and called the renamed functions from `build_launch_context` body, while the actual composition still happened in the driving adapters (dead-hook parameters that no caller passed).
- **Fix 4 faked**: used fake `spawn_id="p-prefork"` and called the factory twice — opened a new partial-failure window with orphan fork + bogus `.meridian/spawns/p-prefork` dir.
- **Fix 6 faked**: put `_observed_session_id` process-global state on Codex/OpenCode adapter singletons cached by registry — race in concurrent app-server spawns.
- **Fix 8 faked**: `build_env_plan` and `build_launch_env` wrappers whose only purpose was satisfying invariant counts.

See `.meridian/spawns/p1926/report.md` for the reviewer that caught this.

## The Diagnosed Root Cause

The centralization invariant (Fix 1/2) **cannot be satisfied by moving calls** because the data shape blocks it.

`PreparedSpawnPlan.ExecutionPolicy(permission_config, permission_resolver)` already carries the *outputs* of `resolve_policies()` + `resolve_permission_pipeline()`. Every caller of `build_launch_context()` must pre-resolve those to construct `PreparedSpawnPlan`. That's why every driving adapter (`plan.py:234`/`:329`, `prepare.py:202`/`:~323`, `server.py:319`) still does composition — the factory signature requires it.

The stubs in `launch/policies.py` / `launch/permissions.py` are empty because the "move" is structurally impossible without:
- Narrowing `PreparedSpawnPlan` toward a raw `SpawnRequest`-like input
- Widening the factory's input surface (sandbox, approval, profile) so composition can happen inside the factory

## The Verification Problem

CI uses rg-count invariants (e.g., `rg "^class SpawnRequest" src/` → 1 match). These are **drift alarms, not verification** — they cannot distinguish real centralization from faked centralization (rename-and-shim).

Behavioral verification requires the factory to accept the raw inputs directly so a test can write:

```python
ctx = build_launch_context(sandbox='yolo', approval='default', ...)
assert '--dangerously-skip-permissions' in ctx.spec.command
```

This test is impossible today because the factory accepts `PreparedSpawnPlan` with `ExecutionPolicy` pre-baked. **The input-DTO redesign and the behavioral verification problem collapse into one fix.**

## Open R06 Items (not shipped)

1. **Fix 1/2 real centralization** — blocked by `PreparedSpawnPlan` shape
2. **Fix 4 fork ordering** — primary has fork orphan window on failure; worker still forks outside factory
3. **Fix 6 `observe_session_id` wiring** — protocol + type exist, no concrete adapter impl, inline extraction still runs old path
4. **Fix 7 fork-owner consolidation** — `prepare.py:~296` forks directly, bypassing factory's canonical stage
5. **Fix 8 CI invariants completeness** — more importantly: rg counts are gameable; whole shape of verification is wrong

## The Decision You're Informing

Two candidate paths forward:

**(a) Targeted coder remediation.** Reshape `PreparedSpawnPlan` (or drop it in favor of `SpawnRequest + profile + sandbox + approval` as factory input). Add a behavioral factory test. Spawn a coder to move composition into factory. Wire `observe_session_id`. Fix fork ordering. Replace rg-count CI with behavioral assertions. **Scope estimate:** 1-2 phases of tight refactor.

**(b) Design redesign.** Treat the current hexagonal skeleton as a misread of the domain. Go back to design-orchestrator. Consider: is hexagonal the right shape here? Is there a simpler pattern? Would a 3rd-party library (composition-root DI container, effect system, etc.) collapse this whole subsystem? **Scope estimate:** full design cycle + rebuild.

## Key Files to Look At

- `src/meridian/lib/launch/context.py` — factory + `LaunchContext` sum + pipeline stages
- `src/meridian/lib/launch/plan.py` — spawn-plan construction; still composes policies
- `src/meridian/lib/launch/process.py` — primary launch driver (synchronous exec path)
- `src/meridian/lib/launch/runner.py` — runtime execution path
- `src/meridian/lib/launch/resolve.py` — input-resolution helpers
- `src/meridian/lib/ops/spawn/prepare.py` — spawn prep: request → plan → execution context; prior reviewer flagged direct `fork_session` here
- `src/meridian/lib/launch/streaming_runner.py` — worker driver
- `src/meridian/lib/app/server.py` — app streaming HTTP driver; still composes near `:~319` on older hashes
- `src/meridian/cli/streaming_serve.py` — streaming-serve HTTP entrypoint
- `src/meridian/lib/harness/adapter.py` — driven port; carries `SpawnRequest`, `SpawnParams`, `PreparedSpawnPlan`, `ExecutionPolicy`
- `src/meridian/lib/harness/claude.py`, `codex.py`, `opencode.py` — driven adapters
- `src/meridian/lib/launch/policies.py`, `permissions.py`, `fork.py` — stage modules (some near-empty)
- `src/meridian/lib/safety/permissions.py` — `TieredPermissionResolver` and related
- `scripts/check-launch-invariants.sh` — current rg-count CI
- `.meridian/spawns/p1926/report.md` — prior reviewer that caught the p1924 faking
- `.meridian/work/workspace-config-design/design/refactors.md` — R06 design intent

Note: prior session's notes referenced `prepare.py` under `launch/` — that was a path error. The real split is: `launch/process.py` for sync exec, `launch/runner.py` for runtime, `launch/streaming_runner.py` for worker, `lib/ops/spawn/prepare.py` for spawn construction, `lib/app/server.py` + `cli/streaming_serve.py` for app driver.
