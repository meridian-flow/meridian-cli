# Unify Harness Launch Pipeline

Status: **completed** (2026-03-04)
Owner: platform/runtime
Backlog links: TD-7, TD-12, TD-13, TD-14, TD-15, TD-16

Completion:
- Checkpoint 1 (TD-12, TD-13, TD-15): `87af9f0`
- Checkpoint 2 (TD-14, TD-16): `bda59aa`

## Goal

Remove harness-specific branching from shared launch code and make adapters/registry the single authority for harness command and environment behavior.

## Scope

In scope:
- TD-12: remove harness-id string branching in spawn prepare (`str(harness.id) == "codex"`)
- TD-13: remove Claude-specific allowed-tools merge from generic strategy builder
- TD-15: replace hardcoded primary harness allowlist validation with registry-derived validation
- TD-14: unify primary launch env wiring with adapter env/MCP env flow
- TD-16: replace `_build_interactive_command` with adapter-delegated command building (fixes codex interactive bug)

Out of scope:
- New harness implementations
- Permission model redesign
- Session store schema changes

## Current Smells (Code References)

1. Spawn prepare branches on harness string:
- `src/meridian/lib/ops/_spawn_prepare.py` (reference loading mode)

2. Generic command builder has Claude-specific behavior:
- `src/meridian/lib/harness/_strategies.py` (`_merge_claude_allowed_tools` and harness guard)

3. Primary launch env wiring differs from spawn execution env wiring:
- `src/meridian/lib/space/launch.py` (`_build_space_env`)
- `src/meridian/lib/exec/spawn.py` (`adapter.env_overrides` + `resolve_mcp_config` merge)

4. Primary harness override validation is hardcoded:
- `src/meridian/lib/space/launch.py` (`_resolve_harness` allowlist)

5. Primary launch command building bypasses adapter pattern entirely:
- `src/meridian/lib/space/launch.py` (`_build_interactive_command`, lines 139-271)
- Duplicates base command, model transform, prompt mode, resume flag, agent flag logic from adapters
- Hardcoded `if harness == "codex": ["codex", "exec"]` uses headless mode for interactive launch — causes non-interactive bug when running bare `meridian`
- Every piece of logic in this function already has an adapter equivalent (`BASE_COMMAND`, `STRATEGIES`, `PROMPT_MODE`, `build_command()` post-processing)

## Design Direction

1. Adapter-declared behavior, not harness-id string checks
- Add explicit adapter capability for reference input mode (inline vs paths), or equivalent adapter hook.
- Spawn prepare uses adapter capability/hook instead of `str(harness.id)` comparisons.

2. Keep generic strategy builder harness-agnostic
- Move Claude allowed-tools merging out of `_strategies.py` into Claude adapter command assembly.
- `_strategies.py` should only apply generic field strategies and append generic permission flags.

3. Registry as harness authority
- `_resolve_harness` validates override against registry-supported primary harness IDs (not hardcoded tuple).

4. Shared env assembly path
- Introduce a shared helper used by both primary launch and spawn execution to assemble child env overlays:
  - runtime env vars
  - adapter `env_overrides(permission_config)`
  - `resolve_mcp_config(adapter, run_params).env_overrides`
- Primary launch should reuse this helper so behavior matches spawn execution.

5. Single `build_command()` with `interactive` mode on `SpawnParams`
- Add `interactive: bool = False` to `SpawnParams` — mode is data, not a protocol concern.
- Each adapter's existing `build_command()` checks `run.interactive` to pick base command and prompt handling.
- Protocol unchanged — no new methods, no default-implementation complexity.
- New harnesses implement `build_command()` and handle the flag however they want (or ignore it).
- Primary launch builds `SpawnParams(interactive=True, ...)` and calls the adapter via the registry.

6. Dependency injection for registry in primary launch
- `launch_primary()` accepts `harness_registry: HarnessRegistry` as a parameter, matching the spawn path's `OperationRuntime.harness_registry` pattern.
- `get_default_harness_registry()` is only called at composition roots (CLI entry point via `_run_primary_launch`, `build_runtime()`).
- No global singleton access deep in the call chain — dependencies are explicit in function signatures.
- Tests inject a registry with stub adapters without monkeypatching module globals.

## Execution Plan

## Checkpoint 1 (single refactor slice): TD-12 + TD-13 + TD-15

Target risk: medium

### Step 1.1: Add adapter-declared reference mode
- Files:
  - `src/meridian/lib/harness/adapter.py`
  - adapter implementations (`claude.py`, `codex.py`, `opencode.py`, `direct.py` if needed)
  - `src/meridian/lib/ops/_spawn_prepare.py`
- Change:
  - Replace `str(harness.id) == "codex"` decision with adapter capability/hook.
- Acceptance:
  - No harness-id string checks remain in spawn prepare for reference mode.

### Step 1.2: Remove Claude special-casing from `_strategies.py`
- Files:
  - `src/meridian/lib/harness/_strategies.py`
  - `src/meridian/lib/harness/claude.py`
  - tests under `tests/test_flag_strategy.py` and profile/launch tests touching `--allowedTools`
- Change:
  - Delete `_merge_claude_allowed_tools` call path from shared strategy builder.
  - Apply merge in Claude adapter only.
- Acceptance:
  - Strategy builder contains no harness-specific conditional branches.
  - Claude command behavior remains unchanged in tests.

### Step 1.3: Registry-driven primary harness override validation
- Files:
  - `src/meridian/lib/space/launch.py`
  - `src/meridian/lib/harness/registry.py` (if helper is added)
  - tests in `tests/test_space_launch_sliceb.py`, `tests/test_space_slice6.py`
- Change:
  - `_resolve_harness` derives allowed override IDs from registry (filtered to primary-supported harnesses), not literal set.
- Acceptance:
  - No hardcoded `claude/codex/opencode` allowlist in `_resolve_harness`.
  - Existing override compatibility semantics preserved.

### Checkpoint 1 verification
- `uv run pytest-llm tests/test_flag_strategy.py tests/test_space_launch_sliceb.py tests/test_default_agent_profiles.py tests/test_space_slice6.py`
- `uv run pyright`

Commit after green:
- `refactor(harness): move harness-specific branching behind adapter/registry boundaries`

## Checkpoint 2 (separate slice): TD-14 + TD-16

Target risk: high (behavioral/command+env parity)

### Step 2.1: Add `interactive` field to `SpawnParams`
- Files:
  - `src/meridian/lib/harness/adapter.py`
  - `src/meridian/lib/harness/_strategies.py` (add `"interactive"` to `_SKIP_FIELDS`)
- Change:
  - Add `interactive: bool = False` to `SpawnParams`
  - No protocol change — `build_command(run, perms)` signature unchanged
- Acceptance:
  - Existing subagent spawn callers unaffected (default `interactive=False`)

### Step 2.2: Update adapters to handle interactive mode
- Files:
  - `src/meridian/lib/harness/claude.py`
  - `src/meridian/lib/harness/codex.py`
  - `src/meridian/lib/harness/opencode.py`
  - `src/meridian/lib/harness/direct.py` (if needed)
  - `tests/test_flag_strategy.py`
- Change per adapter:
  - Add `PRIMARY_BASE_COMMAND` class var (e.g. `("codex",)` instead of `("codex", "exec")`)
  - When `run.interactive`:
    - Use `PRIMARY_BASE_COMMAND`
    - Don't replace prompt with `"-"` (no stdin piping — inherited stdio for interactive)
    - Adjust resume flag shape if needed (e.g. `codex resume <id>` vs `codex exec resume <id>`)
  - When not interactive: existing behavior unchanged
- Acceptance:
  - `CodexAdapter().build_command(SpawnParams(interactive=True, ...))` produces `codex --model X ...` (no `exec`)
  - `ClaudeAdapter().build_command(SpawnParams(interactive=True, ...))` produces `claude --model X --append-system-prompt ...` (no `-p`)
  - Non-interactive commands unchanged in all existing tests

### Step 2.3: Replace `_build_interactive_command` with adapter delegation (DI)
- Files:
  - `src/meridian/lib/space/launch.py`
  - `src/meridian/cli/main.py` (thread registry through `_run_primary_launch`)
  - tests in `tests/test_space_launch_sliceb.py`, `tests/test_space_slice6.py`
- Change:
  - `launch_primary()` accepts `harness_registry: HarnessRegistry` as a parameter (DI, matching the spawn path's `OperationRuntime.harness_registry` pattern)
  - CLI entry point (`root()` → `_run_primary_launch()`) passes `get_default_harness_registry()` at the composition root — this is the only place the global is accessed
  - Delete `_build_interactive_command` entirely
  - New `_build_harness_command` implementation:
    1. `MERIDIAN_HARNESS_COMMAND` override short-circuit (keep existing)
    2. Get adapter from injected `harness_registry.get(harness)`
    3. Build `SpawnParams(interactive=True, prompt=..., model=..., agent=..., appended_system_prompt=..., continue_harness_session_id=..., extra_args=passthrough_args, repo_root=..., mcp_tools=...)`
    4. Build `PermissionResolver` (existing `build_permission_resolver()` logic)
    5. Return `adapter.build_command(params, perms)`
  - Profile loading, skill composition, permission resolution stay in launch.py — they feed into `SpawnParams`
  - Materialization stays in launch.py — `agent` field in `SpawnParams` receives the materialized name
  - `_normalize_system_prompt_passthrough_args` feeds into `SpawnParams.appended_system_prompt`
- Acceptance:
  - No `get_default_harness_registry()` calls inside launch.py — registry comes from caller
  - No harness-id string checks remain in command building
  - `uv run meridian --dry-run` produces same Claude command as before
  - `uv run meridian --dry-run --model codex` produces `codex` (not `codex exec`)

### Step 2.4: Extract shared child env assembly helper
- Files:
  - new helper module (e.g. `src/meridian/lib/harness/env.py` or `lib/exec/_env.py`)
  - `src/meridian/lib/exec/spawn.py`
  - `src/meridian/lib/space/launch.py`
- Change:
  - Build one shared function to merge:
    - runtime env overrides
    - adapter env overrides
    - MCP env overrides from `resolve_mcp_config`
  - Use it from both primary launch and spawn execution.
  - Adapter is already resolved in launch.py (from Step 2.3), so calling `adapter.env_overrides()` and `adapter.mcp_config()` for env is natural.
  - Keep primary-only env vars (`MERIDIAN_SPACE_ID`, prompt, autocompact) while adopting shared adapter/MCP env behavior.
- Acceptance:
  - OpenCode/Claude/Codex adapter env and MCP env behavior is consistent between primary and spawn paths.

### Checkpoint 2 verification
- `uv run pytest-llm`
- `uv run pyright`
- Dry-run spot checks:
  - `uv run meridian --dry-run` (Claude unchanged)
  - `uv run meridian --dry-run --model gpt-5.3-codex` (now `codex`, not `codex exec`)
  - `uv run meridian --dry-run --model opencode-...` (now `opencode`, not `opencode run`)
- Manual: `uv run meridian --model codex` launches interactive session

Commit after green:
- `refactor(launch): unify primary command+env building through adapter pattern`

## Guardrails

- Do not delete untracked files.
- Keep changes checkpointed; no cross-checkpoint accumulation.
- Preserve user-visible command semantics unless explicitly intended and covered by tests.

## Rollback Strategy

- If Checkpoint 2 causes launch regressions, revert only Checkpoint 2 commit and keep Checkpoint 1 improvements.
- Checkpoint 1 is intentionally isolated so adapter-boundary cleanup can stand independently.
- Within Checkpoint 2, steps 2.1-2.3 (command unification) can be reverted independently of step 2.4 (env unification) if needed.
