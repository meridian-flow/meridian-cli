# Task: Accuracy Review of fs/ Spawn-Lifecycle Doc Updates

The code-documenter just updated the agent-facing codebase mirror to reflect the spawn-lifecycle / reaper refactor (commits f6d9f20..27d5237, issue #14). Verify factual accuracy against the source code. This is an accuracy review, not a prose review.

## Files updated (read these as they now stand)

- `.meridian/fs/state/spawns.md`
- `.meridian/fs/state/overview.md`
- `.meridian/fs/launch/process.md`
- `.meridian/fs/launch/overview.md`
- `.meridian/fs/overview.md`
- `.meridian/fs/orphan-investigation.md` (archived context — check it's now clearly marked archived and not contradicting the shipped fix)

## Source of truth (compare doc claims against these)

- `src/meridian/lib/core/spawn_lifecycle.py` — `ACTIVE_SPAWN_STATUSES`, `_ALLOWED_TRANSITIONS`, `SpawnOrigin`, `AUTHORITATIVE_ORIGINS`
- `src/meridian/lib/state/spawn_store.py` — `update_spawn` signature (no `status=`), `mark_finalizing`, `finalize_spawn(..., origin=)`, `_record_from_events` authority rule
- `src/meridian/lib/state/reaper.py` — `_collect_artifact_snapshot`, `decide_reconciliation`, IO shell, depth gate, 120s heartbeat window, 15s startup grace, 30s PID-reuse margin, `orphan_finalization` vs `orphan_run`
- `src/meridian/lib/launch/runner.py` — heartbeat task (30s, cancelled in outer finally), `mark_finalizing` CAS after harness exit / before drain
- `src/meridian/lib/launch/streaming_runner.py` — parity with runner.py

## What to flag

1. **Wrong claims** — any doc statement that the source code contradicts (e.g. wrong timeout values, wrong transition rules, wrong function names, wrong ordering).
2. **Missing authority semantics** — the doc must clearly state that an authoritative finalize event *overwrites* a non-authoritative one (this is the core fix for issue #14). If it's fuzzy or sounds like first-write-wins, flag it.
3. **Missing invariants** — `queued → finalizing` is prohibited; cancellations from queued go directly to `cancelled`. `update_spawn` no longer accepts `status=`. Lifecycle goes only through `mark_finalizing` and `finalize_spawn`.
4. **Stale content** — any residual text from before the refactor (old status sets, old heartbeat-eliminated claims, old reap logic).
5. **Cross-references** — if `state/spawns.md` claims runner calls X and `launch/process.md` describes X differently, flag the mismatch.

## Output

Structured findings: file path, line reference or quote, what's wrong, what source says. Group by file. If a file is clean, say so. Do NOT fix anything — orchestrator routes fixes to targeted fix spawns.
