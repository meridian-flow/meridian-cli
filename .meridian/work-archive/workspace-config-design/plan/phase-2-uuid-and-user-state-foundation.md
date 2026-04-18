# Phase 2: UUID and User-State Foundation

## Scope

Establish the split path model that D28 requires: repo `.meridian/` owns only
shared project artifacts plus `.meridian/id`, while runtime state resolves to a
user-level project directory. This phase owns the helper/API foundation and the
repo-level helper cleanup that later operation callers will rely on.

## Boundaries

In scope:

- add `src/meridian/lib/state/user_paths.py` with:
  - `get_user_state_root()`
  - `get_or_create_project_uuid()`
  - `get_project_state_root()`
- slim `src/meridian/lib/state/paths.py` so:
  - `StatePaths` owns repo `.meridian/` artifacts and exposes `id_file`
  - `StateRootPaths` represents the user-level runtime state root
- update low-level helpers that currently derive repo artifacts from
  `MERIDIAN_STATE_ROOT` so `fs/`, `work/`, `work-archive/`, and work-item
  metadata remain project-scoped after the runtime-home split
- update runtime/bootstrap helpers enough to centralize lazy UUID generation and
  platform-root resolution without yet migrating every high-level caller
- add focused tests for helper semantics, override precedence, invalid-user-root
  handling, and Windows path construction

Out of scope:

- migrating every `resolve_state_root()` caller in ops/CLI/launch layers
- end-to-end spawn smoke for move-preservation or `MERIDIAN_HOME`
- any resurrection of `workspace.local.toml`, context-root projection, or other
  superseded workspace-topology work

## Touched Files and Modules

- `src/meridian/lib/state/user_paths.py` (new)
- `src/meridian/lib/state/paths.py`
- `src/meridian/lib/ops/runtime.py`
- `src/meridian/lib/core/context.py`
- `src/meridian/lib/launch/env.py`
- `src/meridian/lib/state/work_store.py`
- `src/meridian/lib/ops/config.py`
- `tests/test_state/test_paths.py`
- `tests/test_state/test_project_paths.py`
- `tests/ops/test_runtime_bootstrap.py`
- `tests/exec/test_permissions.py`

## Claimed EARS Statement IDs

- `HOME-1.u1`
- `HOME-1.u2`
- `HOME-1.u4`
- `HOME-1.e1`
- `HOME-1.e2`

## Touched Refactors

- none; this phase executes D28 directly while preserving the completed R01/R02
  boundaries

## Dependencies

- [phase-1-config-surface-convergence.md](phase-1-config-surface-convergence.md)
  stays the config/bootstrap prerequisite and must remain green.

## Tester Lanes

- `@verifier`
  Runs the targeted automated suites plus `uv run ruff check .` and
  `uv run pyright`.
- `@unit-tester`
  Pins user-root resolution, UUID helper behavior, invalid-user-root failures,
  and repo-level `fs/work` helper ownership.

Escalation rule:

- Spawn a scoped GPT `@reviewer` only if testers find ambiguity about when the
  UUID is allowed to materialize, or if repo/user path responsibilities still
  overlap after the helper split.

## Exit Criteria

- `src/meridian/lib/state/user_paths.py` is the sole owner of user-root
  defaults, `MERIDIAN_HOME`, and project UUID access.
- `StatePaths` no longer exposes `spawns.jsonl`, `sessions.jsonl`, `spawns/`,
  or cache paths; those belong to the user-level runtime state object.
- Repo-level helpers for `fs/`, `work/`, `work-archive/`, and work-item
  metadata still resolve under the project `.meridian/` after the split.
- Helper-level tests prove:
  - Unix/macOS default user root is `~/.meridian/`
  - Windows default prefers `%LOCALAPPDATA%\\meridian\\`
  - Windows fallback uses `%USERPROFILE%\\AppData\\Local\\meridian\\`
  - invalid or unwritable user roots fail clearly
  - UUID creation writes plain 36-character text with no trailing newline
- The phase leaves `ruff`, `pyright`, and targeted unit coverage clean.
