Test `phase-1-paths-foundation.md` only.

Read:
- `plan/overview.md`
- `plan/phase-1-paths-foundation.md`
- `plan/pre-planning-notes.md`

Goal:
- Add or update focused tests that pin the phase-1 path-owner split and rename
  fallout without reaching into phase-2 config-path behavior.

Focus:
- `ProjectPaths` import/ownership moved to `meridian.lib.config.project_paths`.
- `StatePaths` no longer exposes project-config ownership.
- `.meridian/.gitignore` required lines no longer preserve `!config.toml`.
- `resolve_project_root` is the public helper name used by live callers.

Required output:
- Implement any missing focused tests needed for the phase.
- Run the smallest relevant test selection proving the new coverage passes.
- Report changed files and exact test commands run.

Do not:
- Rewire project config to `meridian.toml`.
- Add workspace-file behavior.
