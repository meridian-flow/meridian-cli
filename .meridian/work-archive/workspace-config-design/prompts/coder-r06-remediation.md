# Coder Task — R06 Remediation (8 fixes against shipped skeleton)

## Context

R06 (hexagonal launch core) was shipped by an impl-orchestrator that wrote code inline without subagent delegation. Post-ship review by 4 independent agents found:
- **Runtime**: main paths work (primary, spawn, fork, bypass, Codex, OpenCode all pass smoke).
- **Design misalignment**: the factory doesn't actually centralize composition; `observe_session_id()` is dead weight; CI script omits half the exit criteria.
- **Edge regressions**: bypass scope, fork ordering, dry-run preview.
- **Structural debt**: fork in two places, primary composes command outside factory.

Your job: fix all 8 items below against the current code. The skeleton is correct — sum type, dispatch, type split, deletions, unification. You're completing the work that was deferred or done incorrectly.

## Current state

HEAD is at `efad4c0`. R06 skeleton is 6 commits (`3f8ad4c`..`efad4c0`). Working tree is clean.

Key files you'll touch (read these first):
- `src/meridian/lib/launch/context.py` — factory `build_launch_context()`, `LaunchContext` sum type, `LaunchOutcome`, `LaunchResult`
- `src/meridian/lib/launch/plan.py` — primary launch composition (currently calls `resolve_policies`, `resolve_permission_pipeline`)
- `src/meridian/lib/launch/process.py` — primary executor (PTY/Popen dispatch, `adapter.build_command()` call, fork materialization, session scope)
- `src/meridian/lib/launch/streaming_runner.py` — streaming executor
- `src/meridian/lib/launch/fork.py` — `materialize_fork()` pipeline stage
- `src/meridian/lib/launch/policies.py` — currently a re-export stub
- `src/meridian/lib/launch/permissions.py` — currently a re-export stub
- `src/meridian/lib/launch/env.py` — env builder
- `src/meridian/lib/ops/spawn/prepare.py` — `build_create_payload()`, direct `fork_session()` at :296
- `src/meridian/lib/ops/spawn/execute.py` — worker executor
- `src/meridian/lib/app/server.py` — app streaming, `TieredPermissionResolver` at :319
- `src/meridian/cli/streaming_serve.py` — `resolve_permission_pipeline` call
- `src/meridian/lib/harness/adapter.py` — `SubprocessHarness` protocol, `observe_session_id()` protocol
- `src/meridian/lib/harness/claude.py` — Claude adapter
- `src/meridian/lib/harness/codex.py` — Codex adapter
- `src/meridian/lib/harness/connections/codex_ws.py` — Codex WS, session_id at :190,:270
- `src/meridian/lib/harness/connections/opencode_http.py` — OpenCode HTTP, session_id at :137,:166
- `src/meridian/lib/harness/extractor.py` — `StreamingExtractor`, `connection.session_id` at :43
- `scripts/check-launch-invariants.sh` — CI invariants script

Also read the design for authoritative intent:
- `.meridian/work/workspace-config-design/design/refactors.md` R06 — scope + exit criteria
- `.meridian/work/workspace-config-design/decisions.md` D17 — architectural rationale

## The 8 fixes

### Fix 1 — Centralize `resolve_policies` into the factory (BLOCKER)

**Problem**: `resolve_policies()` is called from driving adapters (`plan.py:234`, `prepare.py:202`) instead of from `build_launch_context()`. `launch/policies.py` is a re-export stub, not a real pipeline stage.

**Fix**: Move the `resolve_policies()` call into `build_launch_context()`. The factory should accept raw policy inputs (harness id, model, approval mode, agent profile — whatever the driving adapters currently pass to `resolve_policies`) and call the resolver internally. Driving adapters pass raw inputs; factory resolves.

Turn `launch/policies.py` from a re-export into the real implementation (move the logic from `launch/resolve.py` or wherever it lives today), or keep it in its current location but ensure the factory is the sole caller.

**Verification**: `rg "resolve_policies\(" src/ --type py` → matches ONLY in the definition file and `launch/context.py`. Zero matches in `plan.py`, `prepare.py`, or any driving adapter.

### Fix 2 — Centralize `resolve_permission_pipeline` into the factory (BLOCKER)

**Problem**: `resolve_permission_pipeline()` is called from driving adapters (`plan.py:329`, `prepare.py:323`, `streaming_serve.py:65`) and `TieredPermissionResolver` is constructed directly in `server.py:319`.

**Fix**: Move `resolve_permission_pipeline()` into `build_launch_context()`. The factory accepts permission-relevant inputs (sandbox mode, approval level, agent profile permissions — whatever the callers currently pass) and resolves internally. Remove `TieredPermissionResolver` construction from `server.py` — the factory handles it.

**Verification**:
- `rg "resolve_permission_pipeline\(" src/ --type py` → matches ONLY in definition + `launch/context.py`.
- `rg "TieredPermissionResolver\(" src/ --type py` → matches ONLY in the permission builder module. Zero in `server.py`, `streaming_serve.py`, or any driving adapter.

### Fix 3 — Fix `MERIDIAN_HARNESS_COMMAND` bypass scope (MAJOR regression)

**Problem**: `context.py:153` treats `MERIDIAN_HARNESS_COMMAND` as a global factory bypass. Pre-R06, this env var only affected primary launch. Post-R06, `server.py:351` returns HTTP 400 and `streaming_runner.py:637` raises `RuntimeError` when the env var is set — breaking app spawns and streaming if the user has it exported.

**Fix**: The bypass check should only apply to primary launch, not to worker or app-streaming drivers. Options:
- (a) Add a `is_primary: bool` flag to the factory input. Only check `MERIDIAN_HARNESS_COMMAND` when `is_primary=True`.
- (b) Have the primary driver check the env var BEFORE calling the factory, and pass a `bypass_command: str | None` that the factory uses to return `BypassLaunchContext`. Worker and app-streaming never pass it.
- (c) Remove the env var check from the factory entirely; keep it in the primary driver only (it's a primary-specific concern, not a composition concern).

Pick the option that best matches the hexagonal framing (the factory shouldn't branch on "who called me"). Option (b) or (c) is probably cleaner. Verify that app/streaming still work with the env var exported.

**Verification**: `MERIDIAN_HARNESS_COMMAND=x uv run meridian spawn -p "test"` should succeed (spawn ignores the env var). `MERIDIAN_HARNESS_COMMAND=x uv run meridian` should use the bypass command (primary honors it).

### Fix 4 — Fix fork materialization ordering (MAJOR regression)

**Problem**: `process.py:276` enters `session_scope` and `:306` creates the primary spawn BEFORE `context.py:192` calls `materialize_fork()`. Pre-R06, fork ran before session/spawn creation. Now a transient fork failure leaves orphan stopped-session + failed-spawn rows.

**Fix**: `materialize_fork()` must run BEFORE session creation and spawn persistence. In the factory pipeline, fork should happen after spec resolution but before any persistence side effects. Since the factory currently calls `materialize_fork()`, the ordering issue is likely that the primary driver calls the factory too late (after already entering session scope). Fix: the primary driver should call `build_launch_context()` (which runs fork internally) BEFORE entering session scope. Check the worker path too — `prepare.py:296` has its own direct `fork_session()` call that also needs to move into the factory pipeline.

**Verification**: Simulate a fork failure (e.g., with a non-existent session ID) and verify no orphan session/spawn rows are created.

### Fix 5 — Fix `--dry-run` under bypass (MAJOR regression)

**Problem**: `plan.py:326` always builds `plan.command` from `adapter.build_command(...)`. The bypass override is applied later in `context.py:153`. So `--dry-run` prints the harness command even when execution would run the bypass binary.

**Fix**: If Fix 3 moves bypass checking to the primary driver (option b or c), dry-run should also consult the bypass command and preview THAT instead of the harness command. The dry-run output should match what will actually execute.

**Verification**: `MERIDIAN_HARNESS_COMMAND="echo hello" uv run meridian --dry-run` should show `echo hello` (or equivalent), not `claude ...`.

### Fix 6 — Wire `observe_session_id()` end-to-end (MAJOR gap)

**Problem**: `observe_session_id()` exists as a protocol method on `SubprocessHarness` with a base implementation returning `None`. No concrete adapter implements it. `LaunchOutcome` is defined but never constructed by any executor. Session-ID observation still happens inline the old way.

**Fix**:
1. **Executors** construct and return `LaunchOutcome` after process completes. For primary PTY: `LaunchOutcome(exit_code=..., child_pid=..., captured_stdout=<pty_buffer>)`. For async subprocess: `LaunchOutcome(exit_code=..., child_pid=..., captured_stdout=None)`.
2. **Driving adapters** call `adapter.observe_session_id(launch_context=..., launch_outcome=...)` post-exec and construct `LaunchResult`.
3. **Claude adapter** (`claude.py`): implement `observe_session_id()` by relocating the PTY session-ID scraping logic from wherever it currently lives in the executor. Return the scraped session ID, or `None` if Popen fallback.
4. **Codex adapter** (`codex.py`): implement `observe_session_id()` by reading `self._session_id` or equivalent internal state set during WebSocket bootstrap (`codex_ws.py:190,270`). The streaming executor doesn't need to pass captured_stdout — the adapter already has it from its connection.
5. **OpenCode adapter**: same pattern as Codex — reads `connection.session_id` set during session creation (`opencode_http.py:137,166`).
6. **Remove** old inline session-ID extraction code from executors once relocated to adapters.

Per the design, `observe_session_id()` is "a getter over adapter-held state, not a parser of `launch_outcome`." `captured_stdout` is there for Claude PTY scraping specifically; Codex/OpenCode use their connection state.

**Verification**: 
- `rg "observe_session_id\(" src/meridian/lib/harness/ --type py` → matches in `adapter.py` + `claude.py` + `codex.py` + `opencode.py` (or their adapter files).
- Smoke: run a spawn, verify `sessions.jsonl` records `harness_session_id` via the new path.

### Fix 7 — Consolidate fork to one owner (STRUCTURAL blocker)

**Problem**: Fork materialization exists in two places:
- `launch/context.py:192` via `materialize_fork()` (the factory pipeline stage).
- `ops/spawn/prepare.py:296` via direct `fork_session()` call.

Both do the same thing — call `fork_session()`, mutate SpawnParams, rebuild command. The "canonical" comment in `prepare.py:296` contradicts the factory owning it.

**Fix**: Delete the direct `fork_session()` call in `prepare.py:296`. All fork materialization goes through the factory's `materialize_fork()` stage. If `prepare.py` needs to know the fork result for its pre-worker bookkeeping, it should read it from the factory's output (`LaunchContext` fields), not re-derive it.

**Verification**: `rg "fork_session\(" src/ --type py` → matches only in `launch/fork.py` (the pipeline stage implementation) and the adapter's own method definition. Zero matches in `prepare.py` or `process.py`.

### Fix 8 — Complete CI invariants script (MAJOR gap)

**Problem**: `scripts/check-launch-invariants.sh` checks 18-19 conditions but omits 7+ from the design's exit criteria:
- `resolve_policies` sole-caller check
- `resolve_permission_pipeline` sole-caller check
- `build_env_plan` / `build_harness_child_env` sole-caller check
- `TieredPermissionResolver` outside permissions.py
- `observe_session_id` implementations in adapters
- `UnsafeNoOpPermissionResolver` deletion in streaming
- `resolve_launch_spec` sole-caller in factory+adapters

**Fix**: Add the missing checks. For each, the design's R06 exit criteria in `refactors.md` specifies the exact `rg` command and expected result. Transcribe them into the script. Each check should fail the script (exit nonzero) if the result doesn't match expectations.

Also add:
- `rg "pyright:\s*ignore" src/meridian/lib/launch/ src/meridian/lib/ops/spawn/` → 0 matches
- `rg "cast\(Any," src/meridian/lib/launch/ src/meridian/lib/ops/spawn/` → 0 matches

**Verification**: Run `bash scripts/check-launch-invariants.sh` — all checks pass. Temporarily break one (e.g., add a `resolve_policies(` call in a driving adapter) and verify the script fails.

## Ordering

Suggested order (some fixes depend on others):

1. **Fix 3** (bypass scope) — changes factory interface, affects other fixes.
2. **Fix 1 + Fix 2** (centralize policy/permissions) — biggest structural change; factory input shape changes.
3. **Fix 7** (consolidate fork) — removes the duplicate in prepare.py.
4. **Fix 4** (fork ordering) — now that fork is in one place, fix where it runs relative to session creation.
5. **Fix 5** (dry-run bypass) — depends on Fix 3's bypass approach.
6. **Fix 6** (wire observe_session_id) — independent of 1-5; can interleave.
7. **Fix 8** (CI script) — last, after all other fixes land so the checks pass.

Commit after each fix (or after each logical group) per CLAUDE.md. Run `uv run pyright`, `uv run ruff check .`, `uv run pytest-llm` after each commit. Run `bash scripts/check-launch-invariants.sh` after Fix 8.

## Guardrails

- **No backwards compatibility shims.** Per CLAUDE.md: "No real users, no real user data. No backwards compatibility needed."
- **Don't add unit tests for every fix** — prefer smoke-testable behavior over unit test proliferation for a refactor. Only add unit tests for genuinely hard-to-smoke logic (e.g., fork ordering failure behavior).
- **pyright must be 0 errors.** ruff must be clean.
- **Don't touch R01-R05 scope.** Don't rename `resolve_repo_root`, don't add `project_workspace()`, don't change config file paths.
- **Don't modify design docs.** If you discover design-reality tension, note it in your report; the design docs are handled separately.
- **Don't skip hooks** (`--no-verify`).

## Deliverable

Commit per fix (or per logical group). Return a report:
1. Per-fix summary (what changed, which files, one sentence).
2. Exit criteria verification — run each `rg` command from the design's R06 exit criteria and report results.
3. Test results (`pyright`, `ruff`, `pytest-llm`, `check-launch-invariants.sh`).
4. Any design-reality tension discovered that the design docs should address.
5. Any fix you couldn't complete and why.
