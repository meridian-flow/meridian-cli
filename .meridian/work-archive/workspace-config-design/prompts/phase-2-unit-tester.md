Test `phase-2-config-bootstrap-rewire.md` only.

Read:
- `plan/overview.md`
- `plan/phase-2-config-bootstrap-rewire.md`
- `requirements.md`

Goal:
- Add or tighten focused tests for `ProjectConfigState`, canonical
  `meridian.toml` ownership, precedence preservation, and the bootstrap split.

Required output:
- Add the smallest useful regression coverage for:
  - loader/config command shared state
  - no fallback to `.meridian/config.toml`
  - generic startup not creating `meridian.toml`
  - `config init` idempotent creation behavior
- Run the smallest relevant test selection proving that coverage passes.
- Report changed files and exact test commands run.

Do not:
- Add workspace-file behavior.
- Add migration tests for legacy config files.
