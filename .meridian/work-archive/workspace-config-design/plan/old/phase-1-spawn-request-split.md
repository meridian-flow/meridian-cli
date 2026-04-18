# Phase 1: SpawnRequest / SpawnParams Split

## Scope

Introduce `SpawnRequest` as the user-facing DTO. `SpawnParams` stays but carries only resolved/internal fields. This is a type-level split — no behavioral change.

## Current state

`SpawnParams` at `src/meridian/lib/harness/adapter.py:147-166` carries both user-facing and resolved fields mixed together:

**User-facing fields** (go to SpawnRequest):
- prompt: str
- model: ModelId | None
- effort: str | None
- skills: tuple[str, ...] (as refs, not resolved paths)
- agent: str | None
- extra_args: tuple[str, ...]
- interactive: bool
- mcp_tools: tuple[str, ...]

**Resolved/internal fields** (stay on SpawnParams):
- repo_root: str | None (as posix string — resolved path)
- continue_harness_session_id: str | None (resolved from session intent)
- continue_fork: bool (resolved)
- report_output_path: str | None (resolved)
- appended_system_prompt: str | None (composed from policy + skills)
- adhoc_agent_payload: str (built by adapter)

## Plan

1. Add `SpawnRequest` frozen dataclass to `src/meridian/lib/harness/adapter.py` (or a new `src/meridian/lib/launch/request.py`).
2. Keep `SpawnParams` but document it as resolved-only inputs.
3. SpawnParams gets all current fields (backwards compat for this phase — driving adapters still construct SpawnParams directly in phases 1-3; phases 4-6 will change them to construct SpawnRequest).
4. Add a `SpawnRequest.to_params(...)` or factory method that produces SpawnParams given the resolved fields.
5. Update tests that reference SpawnParams/SpawnRequest.

## Key constraint

This phase does NOT change any calling code. SpawnParams keeps all its fields for now. The split is a type addition, not a breaking change. Phases 4-6 will migrate callers to construct SpawnRequest instead.

## Files touched

- `src/meridian/lib/harness/adapter.py` — add SpawnRequest, keep SpawnParams
- Tests that construct SpawnParams — no changes needed this phase (SpawnParams unchanged)

## Exit criteria

- `rg "^class SpawnRequest\b" src/` → 1 match
- `rg "^class SpawnParams\b" src/` → 1 match
- pyright 0 errors, ruff clean, all tests pass
