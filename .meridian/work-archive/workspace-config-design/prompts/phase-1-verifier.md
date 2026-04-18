Verify `phase-1-paths-foundation.md` only.

Read:
- `plan/overview.md`
- `plan/phase-1-paths-foundation.md`
- `plan/pre-planning-notes.md`
- `design/refactors.md`

Goal:
- Verify the R01/R04 prep refactor without widening into phase-2 behavior.

Checks:
- `ProjectPaths` now owns root-level Meridian file policy.
- `StatePaths` no longer owns project-config path or the `.meridian/.gitignore`
  `!config.toml` exception.
- `resolve_project_root` replaced `resolve_repo_root` across the live caller set.
- No config-command rewiring to `meridian.toml` happened yet.

Required verification:
- Run focused affected tests first.
- Run `uv run ruff check .`.
- Run `uv run pyright`.

Report:
- Findings first, with severity and file:line references.
- Then list exact commands run and their results.
- If clean, state that explicitly and mention any residual risk deferred to phase 2.
