Address the concrete phase-2 smoke findings only.

Read:
- `.meridian/spawns/p2060/report.md`
- `plan/phase-2-config-bootstrap-rewire.md`
- `plan/overview.md`
- `requirements.md`

Primary failures to fix:
1. `config init` ignores the documented env-directed repo root flow and writes
   `meridian.toml` to `Path.cwd()` instead of the active project root when
   `MERIDIAN_REPO_ROOT` is set.
2. Generic runtime bootstrap still performs Mars scaffolding, which violates the
   phase-2 requirement that ordinary startup create only `.meridian/` runtime
   state.
3. Tighten smoke docs/tests as needed so BOOT-1.u1 actually catches extra
   root-file side effects, not just `meridian.toml` creation.

Keep scope narrow:
- Do not widen into workspace features.
- Do not add fallback/migration behavior for `.meridian/config.toml`.
- Preserve the existing phase-2 `meridian.toml` rewrite and shared
  `ProjectConfigState` work.

Before finishing:
- Run the smallest focused tests and smoke-relevant checks proving the fixes.
- Report changed files, commands run, and whether the p2060 findings are closed.
