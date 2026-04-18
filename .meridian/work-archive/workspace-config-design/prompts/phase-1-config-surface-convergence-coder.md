# Phase 1 Coder — Config-Surface Convergence

Implement `plan/phase-1-config-surface-convergence.md` in the live repo.

Focus on the three concrete residual R02 gaps confirmed by review:

1. `meridian config init` must not create `mars.toml`, `.mars`, or trigger
   Mars-owned side effects.
2. `config show` / `config get` must use the same effective user-config source
   semantics as `load_config()`, including default-user-config fallback.
3. `config show` and `doctor` must share one config/workspace surface builder
   instead of computing adjacent state independently.

Required outputs:

- code changes for phase 1 only
- targeted tests updated/added for the fixed behavior
- smoke docs updated only if phase-1 user-visible behavior changed materially
- verification run for the touched scope

Boundaries:

- do not implement `workspace.local.toml` parsing yet
- do not add the `workspace` command group yet
- do not implement launch-time workspace root projection yet

Report back with:

- what changed
- files changed
- tests/checks run and their results
- any unresolved issues that block verifier or later phases
