# Requirements — orphan_run reaper fix (GH #14, reopened)

## Problem

`meridian`'s read-path reconciler stamps spawns `failed/orphan_run` while their
runners are still alive and actively writing artifacts. The bug is reproducible
in sandboxed / reparented-to-init environments where `psutil.pid_exists` and
`create_time` return false-negatives on living PIDs.

## Observed failure (2026-04-14)

- Architects `p1711` and `p1712` stamped `failed/orphan_run` at the same
  instant (`2026-04-14T06:06:44Z`) — 1s after parent dev-orch `p1704` exited and
  reparented them to init.
- Both runners were alive and later wrote `succeeded` finalize events at
  `06:16:22Z` / `06:19:53Z` with intact `report.md` and usage data.
- First-terminal-event-wins in the `spawns.jsonl` projection
  (`spawn_store.py:534`) poisoned the row — the later, correct `succeeded`
  finalize was ignored.

## History

- Issue #14 first closed 2026-04-12 with a narrow mitigation.
- Commit `2f5d391` (Phase 4 reaper rewrite, v0.0.27) replaced the previous
  reaper and **removed** two defences: the `_STALE_THRESHOLD_SECS = 300` mtime
  heartbeat fallback and any awareness of a post-exit controlled-cleanup
  window. Those deletions are the regression vector.

## Scope

Two complementary fixes, shipped together:

- **Fix A — immediate/defensive.** Restore an mtime heartbeat fallback in
  `reaper.py` and gate read-path sweeps on `MERIDIAN_DEPTH == 0`. Protects
  against `psutil` false-negatives during normal execution.
- **Fix B — durable/structural.** Add a non-terminal `finalizing` lifecycle
  state set between `spawn_and_stream()` returning and the terminal
  `finalize_spawn()` write. Reconcilers must treat `finalizing` as
  runner-owned. Protects the post-exit drain/report-persistence window.

Supplementary: a projection rule that lets a runner-origin finalize supersede
a prior reconciler-origin terminal stamp, so (a) historical poisoned rows
(`p1711`, `p1712`) self-repair on read, and (b) any prevention gap in
Fix A + Fix B is still recoverable.

## Success criteria

1. A spawn whose runner is alive and writing artifacts within the last
   heartbeat window is never stamped `orphan_run` / `orphan_finalization`,
   even when `psutil.pid_exists(runner_pid)` returns False.
2. A spawn whose harness subprocess has exited but whose runner is still in
   the drain/finalize window is classified `orphan_finalization` (not
   `orphan_run`) if the runner actually dies there.
3. Nested `meridian` invocations (`MERIDIAN_DEPTH > 0`) do not trigger
   foreground reconcile sweeps at all.
4. A runner-origin `succeeded` finalize arriving after a reconciler-origin
   `failed/orphan_*` finalize for the same spawn projects as `succeeded`.
5. Existing poisoned rows (`p1711`, `p1712`) project as `succeeded` on next
   read without rewriting `spawns.jsonl`.
6. `spawn_lifecycle.ACTIVE_SPAWN_STATUSES` and `is_active_spawn_status`
   include `finalizing`; every current read path that iterates active spawns
   continues to reconcile them correctly.

## Out of scope

- Redesign of the psutil liveness helper (keep as-is; treat as best-effort).
- Refactor of `reconcile_spawns` call-site fanout (7+ call sites keep their
  current invariants).
- New CLI surface (`spawn show`'s orphan_finalization rendering tweak is the
  only UI change).

## Risk posture

Bug reopened twice now. Prefer overlapping defences over elegance. Both fixes
ship; neither is considered "made redundant" by the other.
