# Phase 2: Build Health

## Scope and Boundaries

Verify that the minimal PTY fix preserves repository build health.

In scope:

- run `uv run ruff check .`
- run `uv run pyright`
- if either command fails because of direct fallout from Phase 1, apply the smallest correction required and rerun both commands

Out of scope:

- unrelated lint cleanup
- unrelated typing cleanup
- smoke and interactive terminal behavior checks (owned by Phase 3)

## Touched Files and Modules

- repository-wide validation surface
- source edits are not planned; if a direct fallout fix is required, keep it limited to `src/meridian/lib/launch/process.py` unless verifier evidence proves a second file is directly affected

## Claimed EARS Statement IDs

- none

This phase establishes static/build confidence, not behavioral EARS evidence.

## Touched Refactor IDs

- none

## Dependencies

- Phase 1 complete
- may run in parallel with Phase 3 once the Phase 1 patch exists

## Tester Lanes

- `@verifier` mandatory

## Execution Notes

- Keep failure triage narrow: only correct issues directly caused by the PTY fix.
- If `ruff` or `pyright` expose pre-existing unrelated issues, record them as blockers to clean build evidence rather than absorbing them into this task.
- Preserve the minimal-change constraint; Phase 2 is not permission to broaden implementation scope.

## Exit Criteria

- `uv run ruff check .` passes
- `uv run pyright` passes with zero errors
- any direct-fallout correction remains minimal and traceable to the PTY fix
