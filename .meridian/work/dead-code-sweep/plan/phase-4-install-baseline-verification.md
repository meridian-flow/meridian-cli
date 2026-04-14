# Phase 4 — Install and Baseline Verification

## Scope and Boundaries

Validate that the cleanup phases left the repository green, refresh the global
`meridian` binary from current source, and confirm the installed version matches
`src/meridian/__init__.py`.

This phase is a closure gate, not a new cleanup lane. If a check fails because
an earlier phase left breakage behind, route the fix back to the owning phase
before closing this one.

## Touched Files / Modules

- repository root tooling/config only as needed for mechanical verification
- `src/meridian/__init__.py` for version comparison only

## Claimed EARS Statement IDs

- `S-VER-001`
- `S-DIST-001`

## Touched Refactor IDs

- `R-07`

## Dependencies

- `Phase 2 — state-schema-cleanup`
- `Phase 3 — module-compat-cleanup`

## Tester Lanes

- `@verifier`

## Exit Criteria

- `uv run ruff check .` passes.
- `uv run pyright` passes with zero errors.
- `uv run pytest-llm` passes.
- `uv tool install --reinstall .` succeeds.
- `meridian --version` matches `src/meridian/__init__.py::__version__`.
- Any failure discovered here is either fixed by the owning prior phase and
  re-verified or blocks this phase explicitly; it is not silently carried into
  smoke.
