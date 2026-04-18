# Phase 3: Runtime Consumers and Smoke

## Scope

Migrate high-level runtime callers onto the new user-level state root and prove
the new behavior end-to-end. This phase owns the default runtime-home behavior,
override precedence, and regression protection around repo `.meridian/`
artifacts that must stay project-scoped.

## Boundaries

In scope:

- migrate `resolve_state_root()` / `resolve_state_paths()` callers across the
  spawn, report, session, diagnostics, app, launch, and cache paths so runtime
  state lands under `~/.meridian/projects/<UUID>/` by default
- keep `MERIDIAN_STATE_ROOT` as an explicit override that bypasses UUID/user-root
  resolution when set
- preserve `MERIDIAN_FS_DIR` and `MERIDIAN_WORK_DIR` as repo-scoped paths even
  though `MERIDIAN_STATE_ROOT` now defaults to a user-level directory
- update smoke docs and integration-oriented tests to prove default behavior,
  move-preservation, and `MERIDIAN_HOME`

Out of scope:

- any compatibility or migration path for old repo-level `spawns.jsonl` /
  `sessions.jsonl`
- new workspace topology, harness workspace projection, or launch flag work

## Touched Files and Modules

- `src/meridian/lib/ops/runtime.py`
- `src/meridian/lib/ops/diag.py`
- `src/meridian/lib/ops/report.py`
- `src/meridian/lib/ops/session_log.py`
- `src/meridian/lib/ops/session_search.py`
- `src/meridian/lib/ops/spawn/api.py`
- `src/meridian/lib/ops/spawn/execute.py`
- `src/meridian/lib/ops/spawn/log.py`
- `src/meridian/lib/ops/spawn/prepare.py`
- `src/meridian/lib/ops/spawn/query.py`
- `src/meridian/lib/catalog/models.py`
- `src/meridian/lib/launch/process.py`
- `src/meridian/lib/launch/reference.py`
- `src/meridian/cli/app_cmd.py`
- `src/meridian/cli/spawn.py`
- `src/meridian/cli/streaming_serve.py`
- `tests/smoke/quick-sanity.md`
- `tests/smoke/state-integrity.md`
- `tests/smoke/spawn/lifecycle.md`
- targeted operation / spawn / app tests that currently assume repo-level
  runtime state

## Claimed EARS Statement IDs

- `HOME-1.u3`
- `HOME-1.p1`
- `HOME-1.p2`

## Touched Refactors

- none; this phase executes D28 directly while preserving the completed R01/R02
  boundaries

## Dependencies

- [phase-2-uuid-and-user-state-foundation.md](phase-2-uuid-and-user-state-foundation.md)
  must land first so every caller targets the same helper/API contract.

## Tester Lanes

- `@verifier`
  Runs the affected automated suites plus `uv run ruff check .` and
  `uv run pyright`.
- `@unit-tester`
  Pins operation-layer path resolution, explicit `MERIDIAN_STATE_ROOT`
  precedence, and repo-level `fs/work` env derivation.
- `@smoke-tester`
  Mandatory. Proves default spawn state location, project move continuity, and
  `MERIDIAN_HOME` behavior in a real CLI flow.

Escalation rule:

- Spawn a scoped GPT `@reviewer` only if testers find that launch/env handling
  leaks repo artifacts into user state, or if explicit override precedence is no
  longer field-by-field coherent.

## Exit Criteria

- Default runtime state for spawns, sessions, cache, and per-spawn artifacts
  lives under `~/.meridian/projects/<UUID>/`.
- Explicit `MERIDIAN_STATE_ROOT` still short-circuits the default user-root path
  and does not require `.meridian/id`.
- Moving a project directory with the same `.meridian/id` reuses the existing
  user-level project state.
- `MERIDIAN_FS_DIR` continues to point at repo `.meridian/fs`, and
  `MERIDIAN_WORK_DIR` continues to point at repo `.meridian/work/<work-id>`.
- Smoke evidence proves:
  - spawn creates runtime state under the user-level project root
  - repo move preserves UUID identity and finds prior runtime state
  - `MERIDIAN_HOME` redirects the default user state root
  - repo `.meridian/` no longer gains `spawns.jsonl`, `sessions.jsonl`, or
    per-spawn runtime artifacts
- `uv run pytest-llm`, `uv run ruff check .`, and `uv run pyright` pass before
  the final review loop starts.
