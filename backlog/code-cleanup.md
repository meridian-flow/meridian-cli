# Code Cleanup Backlog

Date added: 2026-03-02

## 1) Unify spawn execution lifecycle paths
- Status: `todo`
- Priority: `high`
- Goal: Remove duplicated lifecycle logic between background and blocking spawn execution paths.
- Current duplication:
  - `src/meridian/lib/ops/_spawn_execute.py` (`_execute_spawn_background`, `_execute_spawn_blocking`)
- Proposed direction:
  - Extract shared lifecycle helper(s) for start/session/materialize/cleanup and subrun event emission.
  - Keep transport-specific behavior (background worker launch vs blocking terminal streaming) in thin wrappers.
- Acceptance:
  - No behavior change in spawn state transitions, session tracking, and emitted subrun events.

## 2) Consolidate space-resolution helpers
- Status: `todo`
- Priority: `high`
- Goal: Eliminate duplicate space-id resolution logic.
- Current duplication:
  - `src/meridian/lib/ops/_runtime.py` (`resolve_space_id`, `require_space_id`)
  - `src/meridian/lib/ops/_spawn_query.py` (`_resolve_space_id`)
- Proposed direction:
  - Use one canonical resolver in runtime helpers and consume it from spawn query/ops layers.
- Acceptance:
  - Space-required errors/messages remain consistent across CLI/MCP/ops paths.

## 3) Merge repeated warning/normalization utilities
- Status: `todo`
- Priority: `medium`
- Goal: Remove repeated utility patterns (`_merge_warnings`, space normalization, string stripping).
- Current duplication:
  - `src/meridian/lib/ops/spawn.py`
  - `src/meridian/lib/ops/_spawn_prepare.py`
- Proposed direction:
  - Add a small shared internal utility module for warning composition and input normalization.
- Acceptance:
  - No user-visible behavior change in warning text composition.

## Notes
- This backlog is intentionally behavior-preserving; schema or external contract changes are out of scope.
