Implement `phase-2-config-bootstrap-rewire.md` only.

Read:
- `plan/overview.md`
- `plan/phase-2-config-bootstrap-rewire.md`
- `plan/pre-planning-notes.md`
- `design/refactors.md`
- `requirements.md`

Goal:
- Land R02 only: move project config to `meridian.toml` and split generic
  bootstrap so normal startup creates runtime state only.

Current state after phase 1:
- `ProjectPaths` exists in `src/meridian/lib/config/project_paths.py`.
- Config loader and config commands still resolve `.meridian/config.toml`.
- `ensure_state_bootstrap_sync()` still scaffolds project config on generic
  startup.
- CLI help, manifests, and smoke docs still describe `.meridian/config.toml`.

Required outcomes:
- Introduce a shared `ProjectConfigState` in
  `src/meridian/lib/config/project_config_state.py`.
- Rewire loader, config commands, and bootstrap to one canonical
  `meridian.toml` path through that shared state.
- Keep generic startup limited to `.meridian/` runtime state and `mars.toml`
  side effects only.
- Make `config init` the only creator of `meridian.toml`, keeping it idempotent.
- Update CLI help/manifests and the existing config smoke docs to the new path.
- Do not add legacy fallback or migration behavior for `.meridian/config.toml`.

Do not:
- Add workspace parsing, workspace commands, or launch projection behavior.
- Reintroduce `.meridian/config.toml` as a fallback read/write path.
- Revert unrelated worktree changes.

Use the real affected test/doc surfaces in this tree, including:
- `tests/lib/config/test_settings_paths.py`
- `tests/test_cli_main.py`
- `tests/smoke/config/init-show-set.md`
- `tests/smoke/quick-sanity.md`

Before finishing:
- Run focused tests for the changed config/bootstrap surfaces.
- Report changed files, commands run, and any fallout intentionally deferred to
  phase 3.
