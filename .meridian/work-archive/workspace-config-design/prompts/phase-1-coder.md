Implement `phase-1-paths-foundation.md` only.

Read:
- `plan/overview.md`
- `plan/phase-1-paths-foundation.md`
- `plan/pre-planning-notes.md`
- `design/refactors.md`

Goal:
- Land R01/R04 foundation without widening into config-command rewiring.

Current worktree state:
- `src/meridian/lib/config/project_paths.py` already exists with `ProjectPaths` plus
  `meridian_toml` / `workspace_local_toml`.
- `src/meridian/lib/state/paths.py` already removed `StatePaths.config_path`,
  deleted the `.meridian/.gitignore` `!config.toml` exception, and stopped
  defining `ProjectPaths`.
- Many callers already switched from `resolve_repo_root` to
  `resolve_project_root`.

Finish from that partial state. Do not discard or rework those edits unless a
targeted correction is required.

Known remaining fallout to close:
- `src/meridian/cli/main.py` still imports/calls `resolve_repo_root`.
- `src/meridian/lib/ops/config.py` still imports/calls `resolve_repo_root`
  through `_resolve_repo_root`.
- tests still import `ProjectPaths` / `resolve_project_paths` from
  `meridian.lib.state.paths` instead of the new `meridian.lib.config.project_paths`
  module.
- Any remaining rename or export fallout from moving `ProjectPaths` out of the
  state package must be resolved cleanly.

Required outcomes:
- Create a real project-root file abstraction for `meridian.toml` and `workspace.local.toml`.
- Stop `StatePaths` from owning canonical project config.
- Rename `resolve_repo_root` to `resolve_project_root` across the live caller set.
- Remove the `.meridian/.gitignore` `!config.toml` exception.
- Update affected tests for the new path abstraction / rename surface.

Do not:
- Rewire `config init/show/set/get/reset` to `meridian.toml` yet.
- Add workspace parsing, workspace commands, or launch projection behavior.
- Revert unrelated worktree changes.

Before finishing:
- Run focused tests for changed path/config modules.
- Report changed files, verification run, and any fallout deferred to phase 2.
