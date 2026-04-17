# Phase 1: Config-Surface Convergence

## Scope

Close the live residual R02 convergence gap before any new workspace behavior
lands. This phase establishes one shared config/workspace surface for
inspection commands and locks the already-landed bootstrap split behind tests so
downstream workspace work is not built on stale or duplicated config logic.

## Boundaries

In scope:

- keep `config init` on the runtime-only bootstrap path with no Mars-owned side
  effects and explicit `meridian.toml` creation only
- make config introspection reuse the loader's full user-config source
  resolution semantics
- introduce the shared `config_surface` builder used by both `config show` and
  `doctor`
- move any remaining config/workspace inspection formatting logic behind that
  shared builder

Out of scope:

- parsing `workspace.local.toml`
- adding a `workspace` command group
- projecting workspace roots into launch commands

## Touched Files and Modules

- `src/meridian/lib/config/settings.py`
- `src/meridian/lib/config/project_config_state.py`
- `src/meridian/lib/ops/config.py`
- `src/meridian/lib/ops/config_surface.py` (new)
- `src/meridian/lib/ops/diag.py`
- `src/meridian/lib/ops/runtime.py`
- `tests/lib/config/test_project_config_ops.py`
- `tests/ops/test_diag.py`
- `tests/test_cli_main.py`
- `tests/smoke/config/init-show-set.md`
- `tests/smoke/quick-sanity.md`

## Claimed EARS Statement IDs

- `BOOT-1.u1`
- `BOOT-1.e1`

## Touched Refactors

- `R02` carryover convergence only

## Dependencies

- R01 / R04 are already complete and remain prerequisites only.
- No remaining-phase dependency ahead of this phase.

## Tester Lanes

- `@verifier`
  Runs affected automated suites plus `uv run ruff check .` and
  `uv run pyright`.
- `@unit-tester`
  Pins runtime bootstrap, source attribution, and shared builder ownership.
- `@smoke-tester`
  Mandatory. Covers `config init`, `config show`, `config get`, and `doctor`
  from a clean repo root.

Escalation rule:

- Spawn a scoped GPT `@reviewer` only if testers find a real disagreement
  between loader resolution and config introspection, or if `doctor` still
  derives config/workspace state outside the shared builder.

## Exit Criteria

- `config init` creates `meridian.toml` only when explicitly requested and
  does not create `mars.toml`, `.mars`, or any Mars-managed side effect.
- Generic startup still creates only `.meridian/` runtime state and
  `.meridian/.gitignore`.
- `config show` and `config get` use the same resolved user-config source
  semantics as `load_config()`, including default-user-config fallback.
- `src/meridian/lib/ops/config_surface.py` is the shared owner for config /
  workspace inspection state consumed by both `config show` and `doctor`.
- Targeted tests and smoke pass, and the phase leaves `ruff` and `pyright`
  clean.
