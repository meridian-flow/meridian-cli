# R06 Retry Correctness Review

## 1) Composition Leaks

### D1. Policy + permission composition still outside factory
- Pointer: `src/meridian/lib/launch/plan.py:234`, `src/meridian/lib/launch/plan.py:329`, `src/meridian/lib/ops/spawn/prepare.py:202`, `src/meridian/lib/ops/spawn/prepare.py:323`, `src/meridian/cli/streaming_serve.py:65`, `src/meridian/lib/app/server.py:319`
- Wrong: drivers still do `resolve_policies`, `resolve_permission_pipeline`, direct `TieredPermissionResolver`. factory not owner.
- Severity: major
- Fix sketch: change factory input to raw request + overrides; move policy/permission resolution inside `build_launch_context()`; delete driver-side resolution.

### D2. Command composition still outside factory
- Pointer: `src/meridian/lib/launch/plan.py:383`, `src/meridian/lib/ops/spawn/prepare.py:335`, `src/meridian/lib/launch/process.py:351`
- Wrong: drivers still call `build_command`. `process.py` rebuilds command after factory already built `spec`.
- Severity: major
- Fix sketch: move command projection to one stage; return final argv in `NormalLaunchContext`; delete adapter `build_command` calls from drivers.

### D3. `ExecutionPolicy` still composed in drivers
- Pointer: `src/meridian/lib/launch/plan.py:202`, `src/meridian/lib/ops/spawn/prepare.py:387`, `src/meridian/lib/ops/spawn/execute.py:414`, `src/meridian/lib/app/server.py:345`, `src/meridian/cli/streaming_serve.py:82`
- Wrong: execution policy assembled in multiple places, not one factory pipeline.
- Severity: major
- Fix sketch: factory builds `ExecutionPolicy` from raw safety inputs; callers pass only request-level intent.

## 2) Fork Ordering / Orphan Windows

### D4. Direct fork in prepare path before any spawn/session row
- Pointer: `src/meridian/lib/ops/spawn/prepare.py:296`, `src/meridian/lib/ops/spawn/prepare.py:305`
- Wrong: `fork_session()` runs in prepare step. if later create/start fails, fork exists with no matching meridian row.
- Severity: blocker
- Fix sketch: remove fork from `prepare.py`; materialize fork only in canonical factory stage after rows exist.

### D5. Session/spawn row can exist before fork materialization
- Pointer: `src/meridian/lib/launch/process.py:276`, `src/meridian/lib/launch/process.py:306`, `src/meridian/lib/launch/process.py:328`, `src/meridian/lib/ops/spawn/execute.py:685`, `src/meridian/lib/ops/spawn/execute.py:730`, `src/meridian/lib/ops/spawn/execute.py:756`, `src/meridian/lib/launch/context.py:190`
- Wrong: session + spawn rows written first; fork happens later in factory. if fork fails, rows persist but no forked session.
- Severity: major
- Fix sketch: atomic launch transaction model: create/mark rows provisional, materialize fork, then commit row session id; on failure rollback/provenance marker.

### D6. Fork can happen before spawn row in streaming fallback path
- Pointer: `src/meridian/lib/launch/streaming_runner.py:637`, `src/meridian/lib/launch/streaming_runner.py:692`, `src/meridian/lib/launch/context.py:190`
- Wrong: `build_launch_context()` (fork stage) runs before fallback `start_spawn` when row missing.
- Severity: major
- Fix sketch: enforce precondition `spawn row must exist` for `execute_with_streaming`; fail fast if missing.

### D7. Half-written spawn dir window (`.meridian/spawns/<id>`) before row
- Pointer: `src/meridian/lib/launch/context.py:117`, `src/meridian/lib/launch/cwd.py:24`, `src/meridian/lib/launch/streaming_runner.py:637`, `src/meridian/lib/launch/streaming_runner.py:692`
- Wrong: nested Claude path can `mkdir` spawn dir during context build before fallback row create.
- Severity: major
- Fix sketch: require row first, then make child cwd; or attach directory creation to row creation transaction.

## 3) Session-ID Observation Races / Wiring

### D8. `observe_session_id()` port is dead (declared, not wired)
- Pointer: `src/meridian/lib/harness/adapter.py:332`, `src/meridian/lib/harness/adapter.py:466`, `src/meridian/lib/harness/claude.py`, `src/meridian/lib/harness/codex.py`, `src/meridian/lib/harness/opencode.py`
- Wrong: no concrete adapter implements `observe_session_id`; no caller invokes it.
- Severity: major
- Fix sketch: implement per-adapter `observe_session_id`; call once in primary/streaming finalize path; delete duplicate inline extraction logic.

### D9. Session id still flows via old inline extractor path
- Pointer: `src/meridian/lib/launch/process.py:452`, `src/meridian/lib/launch/process.py:454`, `src/meridian/lib/launch/streaming_runner.py:859`, `src/meridian/lib/launch/session_ids.py:16`
- Wrong: `extract_latest_session_id()` old path still owns observation; new driven-port contract unused.
- Severity: major
- Fix sketch: make extractors internal to adapter `observe_session_id`; keep one observation path.

### D10. Primary finalizes spawn before best-effort session-id observation
- Pointer: `src/meridian/lib/launch/process.py:443`, `src/meridian/lib/launch/process.py:452`
- Wrong: terminal row written first, session id update later in swallowed best-effort block. failure there leaves terminal spawn/session stale.
- Severity: major
- Fix sketch: observe session id before terminal finalize, or include session id in same finalize write.

### Note: process-global adapter session state
- Scan result: no `_observed_session_id` style mutable singleton state in current `claude/codex/opencode` adapters.

## 4) Dry-Run Correctness Under Bypass

### D11. Bypass dry-run preview misses preflight-expanded args
- Pointer: `src/meridian/lib/launch/__init__.py:77`, `src/meridian/lib/launch/context.py:120`, `src/meridian/lib/launch/context.py:162`, `src/meridian/lib/harness/claude_preflight.py:120`
- Wrong: dry-run bypass preview uses `command_request.passthrough_args`; runtime bypass uses `preflight.expanded_passthrough_args`. nested Claude `--add-dir` expansion can be missing in preview.
- Severity: major
- Fix sketch: build dry-run preview by calling same preflight stage as runtime (or share a pure helper returning expanded passthrough args).

### Note: other dry-run paths
- Primary dry-run path is only `launch_primary` dry-run site. no extra primary preview path found.

## 5) Dead Hooks / Dead Wrappers

### D12. Stage wrapper modules are dead pass-throughs
- Pointer: `src/meridian/lib/launch/policies.py:1`, `src/meridian/lib/launch/permissions.py:1`
- Wrong: wrappers only re-export symbols; no stage behavior.
- Severity: minor
- Fix sketch: delete wrappers or make them real stage owners with logic + tests.

### D13. `build_launch_env()` appears dead
- Pointer: `src/meridian/lib/launch/command.py:16`
- Wrong: no in-repo caller for `build_launch_env`.
- Severity: minor
- Fix sketch: delete function/export, or route all env planning through it.

### D14. Context result types are dead surface
- Pointer: `src/meridian/lib/launch/context.py:57`, `src/meridian/lib/launch/context.py:66`, `src/meridian/lib/harness/adapter.py:466`
- Wrong: `LaunchOutcome`/`LaunchResult` + `observe_session_id` contract not used by runtime paths.
- Severity: minor
- Fix sketch: wire these types into process/streaming path or remove them now.

### D15. Unused fields on resolved primary plan
- Pointer: `src/meridian/lib/launch/plan.py:51`, `src/meridian/lib/launch/plan.py:52`, `src/meridian/lib/launch/plan.py:53`
- Wrong: `run_params`, `permission_config`, `permission_resolver` fields set but not read.
- Severity: minor
- Fix sketch: delete unused fields or make one consumer use them as canonical data.

## 6) Sum-Type Exhaustiveness

### D16. App server LaunchContext handling not exhaustive typed match
- Pointer: `src/meridian/lib/app/server.py:364`
- Wrong: `if not isinstance(..., NormalLaunchContext)` branch, no `match` + `assert_never`; new variant can slip to runtime-only error path.
- Severity: minor
- Fix sketch: switch to `match launch_context` with explicit `NormalLaunchContext` and `BypassLaunchContext`, then `assert_never` default.

## 7) rg-Invariants Gaming Surface

### D17. Script checks are easy to satisfy with rename/shim tricks
- Pointer: `scripts/check-launch-invariants.sh:72`
- Wrong: count checks verify symbol presence, not ownership behavior.
- Severity: major
- Fix sketch: replace with behavioral tests around `build_launch_context()` input->output invariants.

Concrete game examples per check:
- `:72` `resolve_policies definition`: keep one thin wrapper def; real composition moved to driver helper names.
- `:73` `resolve_permission_pipeline definition`: same shim trick.
- `:74` `materialize_fork definition`: keep one no-op def; call `fork_session` in driver under another name.
- `:77/:78` context class count: keep tiny classes; runtime passes dict/tuple in parallel path.
- `:79` `RuntimeContext definition`: keep one dead class in another module; real runtime env uses plain dict.
- `:82` match-count: add dead `match launch_context` block; real branch logic in `if` chain.
- `:83` assert_never count: add unreachable helper with `assert_never` twice.
- `:84` no `pyright: ignore`: use `# type: ignore` (without `pyright`) to bypass grep.
- `:85` no `cast(Any,`: use `cast("Any", x)` string-form; grep misses.
- `:88/:89` SpawnRequest/SpawnParams count: keep one skeletal class, real fields carried in different DTO.
- `:92/:93` LaunchResult/LaunchOutcome count: keep dead types, never used.
- `:96` no concrete harness imports: use `importlib.import_module("meridian.lib.harness.codex")` string import.
- `:99` MERIDIAN_HARNESS_COMMAND in context: leave constant/comment reference only.
- `:100/:101` no env var in plan/command: build key by concat (`"MERIDIAN_"+"HARNESS_COMMAND"`).
- `:104` `run_streaming_spawn deleted`: keep alias function different name calling same old behavior.

## Severity Count
- blocker: 1
- major: 11
- minor: 5

