Verify `phase-2-config-bootstrap-rewire.md` only.

Read:
- `plan/overview.md`
- `plan/phase-2-config-bootstrap-rewire.md`
- `plan/pre-planning-notes.md`
- `design/refactors.md`
- `requirements.md`

Goal:
- Verify the R02 config/bootstrap rewrite without widening into workspace
  features.

Checks:
- Loader, config commands, and any config-path helpers use one shared
  `ProjectConfigState`.
- Project config now lives at `meridian.toml`.
- Generic startup no longer auto-creates `meridian.toml`.
- `config init` remains the only creator and stays idempotent.
- No fallback or migration path for `.meridian/config.toml` was introduced.
- CLI help and manifests match the new canonical path.

Required verification:
- Run focused affected tests first.
- Run `uv run ruff check .`.
- Run `uv run pyright`.

Report:
- Findings first, with severity and file:line references.
- Then list exact commands run and their results.
- If clean, state that explicitly and call out anything intentionally deferred to
  phase 3.
