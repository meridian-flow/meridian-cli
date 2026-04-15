# Task: Final Two Accuracy Fixes

Two remaining findings from re-review. Apply minimal targeted edits.

## fs/ fix

**File:** `.meridian/fs/launch/overview.md` around line 27-28.

Currently the primary-path lifecycle list places `extract_latest_session_id()` (session ID persistence) before `Finalize spawn state`. In source (`src/meridian/lib/launch/process.py:426` and `:437`), `finalize_spawn(origin="launcher")` runs BEFORE `extract_latest_session_id()`. Swap the order in the list so finalize precedes session-ID extraction, consistent with the already-fixed `launch/process.md`.

## docs/ fix

**File:** `docs/_internal/ARCHITECTURE.md` around line 419.

The `orphan_finalization` table row still says `"Runner died after harness exit but before persisting the final report"`. The reconciler actually classifies this based on `record.status == "finalizing"` at reap time (see `src/meridian/lib/state/reaper.py:150`). Rewrite that row to match the status-at-reap wording already used in `docs/troubleshooting.md:65` — something like `"Spawn was in 'finalizing' status when reaped (runner crashed after post-exit work, before terminal finalize)"`.

Do not run git. Do not rewrite surrounding text. Just these two edits.
