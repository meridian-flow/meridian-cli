# Slice: Extract materialization cleanup from session_store

## Goal
Remove the `state → harness` dependency in `session_store.py` before moving it to the `state/` package.

## Context
`src/meridian/lib/space/session_store.py` has a function `cleanup_stale_sessions()` that calls `cleanup_materialized()` from `harness/materialize.py`. This creates a dependency from a state store into the harness layer, which violates the target architecture boundary. Before we can move `session_store.py` into `lib/state/`, we need to break this dependency.

## Work
1. Read `src/meridian/lib/space/session_store.py` — find `cleanup_stale_sessions()` and understand how it calls `cleanup_materialized()`
2. Modify `cleanup_stale_sessions()` to RETURN the stale `(harness_id, chat_id)` pairs (or whatever identifiers are needed) instead of calling `cleanup_materialized()` directly
3. Find all callers of `cleanup_stale_sessions()` — likely in `src/meridian/lib/ops/diag.py` and `src/meridian/cli/main.py`
4. Update each caller to:
   a. Call `cleanup_stale_sessions()` to get the stale pairs
   b. Call `cleanup_materialized()` themselves with those pairs
5. Remove the `harness/materialize` import from `session_store.py`

## Rules
- Read every file before modifying
- Preserve the same overall behavior — cleanup still happens, just the caller orchestrates it
- The return type should be clear (e.g., `list[tuple[str, str]]` or a named type)
- No other structural changes in this slice

## Verification
Run `uv run pytest-llm` and `uv run pyright` — both must pass.
