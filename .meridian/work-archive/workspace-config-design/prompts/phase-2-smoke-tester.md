Smoke-test `phase-2-config-bootstrap-rewire.md` only.

Read:
- `plan/overview.md`
- `plan/phase-2-config-bootstrap-rewire.md`
- `tests/smoke/config/init-show-set.md`
- `tests/smoke/quick-sanity.md`

Goal:
- Prove the user-visible config/bootstrap behavior now matches phase 2.

Must cover:
- `config init` creates `meridian.toml`
- `config show` reads the new canonical path
- generic first-run startup does not auto-create `meridian.toml`
- legacy `.meridian/config.toml` assumptions are gone from the smoke docs you
  exercise

Report:
- Exact commands run
- Pass/fail for each smoke scenario
- Any behavior mismatch with file/line references back to docs or code
