# Space Plumbing Fix: Thread Space ID Explicitly

**Status:** partially implemented

## Current Implementation Snapshot (2026-03-03)

- Spawn query/list/stats/show/wait paths now accept explicit `space` and thread it through resolution helpers.
- Canonical runtime helper `require_space_id(space)` exists and is used across spawn ops.
- Remaining items in this doc should be treated as follow-up cleanup/revalidation, not fresh greenfield work.

## Problem

Space ID resolution is env-coupled throughout the run query/execution layer. Functions call `os.getenv("MERIDIAN_SPACE_ID")` instead of using the space ID that's already been resolved and threaded through `payload.space`. This causes:

1. `meridian run spawn --space s1` fails with SPACE_REQUIRED (even though space exists)
2. Auto-created spaces fail in the same run that created them
3. `run list/stats --space` requires env var despite accepting `--space` flag
4. `run show/wait/continue` all env-coupled via `_read_run_row`
5. `-f @name` reference loading ignores threaded space, reads env directly

### Root cause

`_run_query.py` defines `_require_space_id()` which reads `os.getenv("MERIDIAN_SPACE_ID")` directly. Every query function calls this instead of accepting an explicit space parameter. The execution path threads space correctly, but post-execution queries lose it.

## Step 0: Make `_run_query` accept explicit space_id (P0, localized)

The core fix. All query helpers currently derive space from env. Thread it explicitly.

### Files to change

#### `src/meridian/lib/ops/_run_query.py`

- **Change** `_require_space_id()` → `_resolve_space_id(space: str | None) -> str` — check `space` param first, then env fallback
- **Change** `_space_dir(repo_root, space=None)` → accept optional space param
- **Change** `_read_run_row(repo_root, run_id, space=None)` → thread space
- **Change** `_detail_from_row(*, repo_root, row, report, include_files, space_id=None)` → use passed space_id instead of `_require_space_id()` on line 108
- **Change** `resolve_run_reference(repo_root, ref, space=None)` → thread space
- **Change** `resolve_run_references(repo_root, refs, space=None)` → thread space

All callers that already have space context pass it; callers without still fall back to env.

#### `src/meridian/lib/ops/run.py`

- **Change** `_require_space_dir(repo_root)` → `_resolve_space_dir(repo_root, space=None)` — accept optional space
- **Change** `run_list_sync` (line 130): pass `payload.space` to `_resolve_space_dir`
- **Change** `run_stats_sync` (line 168): pass `payload.space` to `_resolve_space_dir`
- **Change** `run_show_sync` (line 231): thread space through `_read_run_row` and `_detail_from_row`
- **Change** `run_wait_sync`: thread space through wait loop

#### `src/meridian/lib/ops/_run_execute.py`

- **Change** `_execute_run_blocking` (line 736): pass resolved `space_id` to `_read_run_row` instead of relying on env
  - `space_id` is already resolved on line 672 via `_resolve_space(runtime.repo_root, payload.space)` — just thread it to the post-run read

### Tests

- Add unit test: `run_create_sync(space='s1')` succeeds without `MERIDIAN_SPACE_ID` env
- Add unit test: `run_list_sync(space='s1')` succeeds without env
- Add unit test: post-run row read uses resolved space, not env
- Run full suite

## Step 1: Fix report_path semantics (P1, mixed)

### Sub-issue 1A: report_path is not a write target

`report_path` flows into `RunActionOutput` but the agent decides whether to write it. The actual report is extracted to `.meridian/.spaces/<space>/runs/<run-id>/report.md` by finalization.

**Decision needed:** Is `report_path` a user-visible workspace file the agent writes, or just metadata? Current behavior: it's metadata pointing to where the user expects to find the report, but nothing enforces it.

**Proposed:** Remove `report_path` from `RunActionOutput` (it's misleading). The canonical report location is always `<space>/runs/<run-id>/report.md`. CLI `_read_run_report_text` already reads from there.

### Sub-issue 1B: CLI report lookup scans all spaces

`main.py:116-124` scans all spaces for matching run ID when env space is unset. Run IDs repeat across spaces (`r1`, `r2`...), so this can return the wrong report.

**Fix:** When space is known (from run output or env), use it directly. Only scan when truly unknown.

### Files to change

- `src/meridian/lib/ops/_run_prepare.py` — remove `report_path` from `_PreparedCreate` or change to relative-only
- `src/meridian/lib/ops/_run_models.py` — evaluate `report_path` field on `RunActionOutput`
- `src/meridian/cli/main.py` — `_find_run_report_file` should prefer space from `RunActionOutput` metadata
- `src/meridian/lib/prompt/compose.py` — `build_report_instruction` review

## Step 2: Thread space into reference loading (P1, broader)

`-f @name` references resolve against space artifacts but read `MERIDIAN_SPACE_ID` from env directly.

### Files to change

- `src/meridian/lib/prompt/reference.py` (line 112) — accept explicit `space_id` parameter
- `src/meridian/lib/ops/_run_prepare.py` — pass resolved space to `load_reference_files`

## Step 3: Space-aware artifact keys (P1, broader refactor)

Run IDs are per-space (`r1`, `r2`...) but artifact keys are `{run_id}/...` with no space component. Cross-space collisions possible.

### Design options

**Option A:** Prefix artifact keys with space ID: `{space_id}/{run_id}/...`
- Pro: globally unique keys
- Con: migration needed for existing artifacts

**Option B:** Scope artifact store per-space (store lives under space dir)
- Pro: no key changes, natural isolation
- Con: artifacts already live under `.meridian/artifacts/` globally

**Option C:** Make run IDs globally unique (UUIDs instead of sequential)
- Pro: eliminates collision without key restructuring
- Con: less human-readable

**Recommendation:** Option B — move artifact storage under space dir. Aligns with files-as-authority philosophy where all state lives under `.meridian/.spaces/<space-id>/`.

### Files to change

- `src/meridian/lib/state/artifact_store.py` — scope to space
- `src/meridian/lib/state/paths.py` — add per-space artifacts path
- `src/meridian/lib/ops/_run_execute.py` — use space-scoped store
- `src/meridian/lib/ops/_run_query.py` — use space-scoped store
- Migration: move existing global artifacts into space dirs (or ignore — no real user data)

## Implementation Order

| Step | Risk | Scope | Dependencies | Priority |
|------|------|-------|-------------|----------|
| 0: Thread space_id explicitly | Low | Localized | None | P0 — fixes spawn |
| 1: Fix report_path | Medium | Mixed | Step 0 | P1 |
| 2: Thread space into references | Low | Localized | Step 0 | P1 |
| 3: Space-aware artifacts | Medium | Broader | Steps 0-1 | P1 |

**Recommend:** Step 0 now (unblocks `meridian run spawn` without env var). Steps 1-3 as a batch after.
