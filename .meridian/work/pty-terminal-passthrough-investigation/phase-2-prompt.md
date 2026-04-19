# Phase 2: Build Health Verification

## Task

Verify the PTY fix in `src/meridian/lib/launch/process.py` preserves repository build health.

## Commands to Run

1. `uv run ruff check .` — lint check
2. `uv run pyright` — type check (must show 0 errors)

## Scope

- Run both commands
- If either fails due to direct fallout from the PTY fix, apply the smallest correction
- Do NOT fix unrelated pre-existing issues — just report them as blockers

## Exit Criteria

- `uv run ruff check .` passes
- `uv run pyright` passes with zero errors
