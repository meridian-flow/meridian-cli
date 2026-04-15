# Feasibility Record — Round 2

Probe evidence and assumption verdicts for the Round 2 design. Every F-finding
from the preservation hint (F1-F8) gets an explicit verdict. Re-run any probe
that goes stale.

## Evidence — the failure is real, reproducible, and ongoing

Source: investigator reports `p1715`, `p1716`; direct inspection of
`src/meridian/lib/state/reaper.py`, `runner.py`, `spawn_store.py`,
`spawn_lifecycle.py`; meta-evidence from the Round 1 review runs themselves.

### Round 1 incidents

- **`p1711` / `p1712`** — `.meridian/spawns.jsonl` contains paired finalize
  events: an earlier `failed/orphan_run` at `2026-04-14T06:06:44Z`, and a later
  `succeeded` with `exit_code=0`, full usage, and intact `report.md` at 06:16:22
  and 06:19:53 respectively.
- **Simultaneous stamp** — both `p1711` and `p1712` stamped at exactly
  06:06:44Z. Only a batch reconciler sweep iterating `list_spawns` could
  produce that timing. Since `diag.py:145` already skips when
  `MERIDIAN_DEPTH > 0`, the triggering invocation is one of the read-path
  call sites in `ops/work_dashboard.py`, `ops/spawn/api.py`, or `cli/spawn.py`.
- **Parent reparent timing** — parent dev-orch `p1704` (worker pid `1914282`)
  exited 1s before the stamp. The two child runners were reparented to init at
  that instant. This is the signal that psutil's false-negative originates in
  sandbox / PID-namespace opacity, not in a genuine death.

### Round 2 meta-incidents

During Round 1 review, `p1731` and `p1732` themselves fired the exact bug —
stamped `failed/orphan_run` at 13:00:55Z, then `succeeded` at 13:05:07Z /
13:06:18Z. `spawns.jsonl` now contains four live incidents (p1711, p1712,
p1731, p1732) that the Round 2 projection must self-repair on read.

### Commit that regressed the behaviour

- `2f5d391` — "Phase 4: Replace 500-line reaper state machine with trivial
  liveness guard". Pre-rewrite `reaper.py` contained `_STALE_THRESHOLD_SECS =
  300` and `_spawn_is_stale`; the current reaper has neither. No corresponding
  defence was added elsewhere. Direct diff inspection confirms.

## Probe results

### P1 — Harness output-cadence evidence (F4)

Source: `../../probe-heartbeat.md` (explorer spawn p1739).

| Harness | Sample size | p50 inter-event gap | p95 | Max observed gap |
|---|---:|---:|---:|---:|
| claude   | 12 | 0.304s | 23.059s | **153.922s** |
| codex    | 12 | 0.008s |  7.639s |  86.799s |
| opencode | 10 | 0.006s |  0.092s |   1.201s (sample too small to conclude) |

Harness-specific silence scenarios:

- **claude** — adapter blocks on `stdout.readline()` with no timer; long
  model thinking, tool round-trips, and approval waits all silent by
  construction. 153.9s gap observed in `p1736` while a background
  `meridian spawn wait` command was still running.
- **codex** — websocket reader in `codex_ws.py` has no keepalive. 86.8s gap
  observed in `p1727` between successive response items.
- **opencode** — SSE loop in `opencode_http.py` only yields on chunks; no
  synthesized heartbeat. Healthy server can sit silent indefinitely; sample
  too small to prove an upper bound.

**Verdict**: the 120s heartbeat window keyed on harness-output mtime is
**unsafe** for `running`. A runner-owned periodic heartbeat (30s tick, 4×
safety factor relative to the 120s window) is required. Encoded as S-RN-004
and R-06.

### P2 — Projection is first-terminal-event-wins (confirmed)

- Current projection logic at `spawn_store.py:534-557` preserves
  `status`/`exit_code`/`error` from the first terminal event; later events
  merge metadata only.
- Round 2 replaces this with authority-aware projection keyed on
  `origin`/`terminal_origin` (never on `error` content in new code). Legacy
  rows fall back to `resolve_finalize_origin` once, then carry
  `terminal_origin` explicitly.

### P3 — Reaper calls `finalize_spawn` directly on read paths (confirmed)

- `reaper.py:57` via `finalize_spawn(...)` inside `_finalize_and_log`. This is
  the single reconciler writer site. Round 2 tags it `origin="reconciler"`
  and adds the CAS-based re-validation guard (S-RP-008).

### P4 — Depth-gate surface is wider than a single call site (confirmed — F3)

- Nine batch entrypoints via `reconcile_spawns`: `cli/spawn.py:502`,
  `ops/diag.py:72`, `ops/spawn/api.py:157,258`,
  `ops/spawn/context_ref.py:40`, `ops/spawn/query.py:30`,
  `ops/work_dashboard.py:329,347,394,464`.
- One single-row entrypoint via `reconcile_active_spawn` direct call:
  `ops/spawn/query.py:70` (used by `read_spawn_row`, which flows into
  `spawn show`, `spawn files`, `spawn wait`, `spawn log`, and the post-run
  blocking status read).
- Moving the gate inside `reconcile_active_spawn` covers both surfaces
  uniformly (R-05).

### P5 — Finalize writer surface is 11 sites (confirmed — F5)

Enumerated via `git grep -n "finalize_spawn"`:

1. `lib/launch/runner.py:851` — runner (authoritative)
2. `lib/launch/streaming_runner.py:1184` — runner (authoritative)
3. `lib/launch/process.py:426` — launcher (authoritative)
4. `cli/streaming_serve.py:115` — launcher (authoritative)
5. `lib/app/server.py:145` — launcher (authoritative)
6. `lib/app/server.py:256` — launch_failure (authoritative)
7. `lib/ops/spawn/execute.py:578` — launch_failure (authoritative)
8. `lib/ops/spawn/execute.py:637` — launch_failure (authoritative)
9. `lib/ops/spawn/execute.py:881` — launch_failure (authoritative)
10. `lib/ops/spawn/api.py:493` — cancel (authoritative)
11. `lib/state/reaper.py:57` — reconciler (non-authoritative)

Complete enumeration confirmed; no terminal state in `spawns.jsonl` is produced
from any other site (verified by p1732: `SpawnFinalizeEvent` is constructed
only inside `spawn_store.finalize_spawn`).

### P6 — Atomicity of `running → finalizing` (F2)

Source: direct inspection of `spawn_store.py:253-290` (`update_spawn`) and
`spawn_store.py:317-363` (`finalize_spawn`).

- `update_spawn` appends blindly — no flock-scoped pre-condition check.
- `finalize_spawn` already acquires the flock but reads the projected status
  only to compute the `was_active` return; it does not re-validate the
  projected status for *admissibility* of the write.
- The two operations therefore race: a runner about to mark `finalizing` and
  a reconciler about to mark `orphan_run` can both observe `running` and both
  append. First-wins projection then freezes whichever lost-the-race writer
  appears later.

**Verdict**: confirmed. Round 2 adds `mark_finalizing` CAS (atomic check +
append under the same flock) and an origin-aware guard in `finalize_spawn`
that drops reconciler-origin writes when the projected status has crossed
into `finalizing` or terminal (S-RP-008, R-03).

### P7 — Consumer hard-codes (F6)

Source: `git grep` for literal status sets.

Confirmed hard-coded active/terminal literals in:

- `cli/spawn.py:446-470` — `view_map["active"] = ("queued", "running")`,
  `--status` validator set.
- `cli/spawn.py:54` — post-launch render check `{"succeeded", "running",
  "dry-run"}`.
- `ops/spawn/api.py:284-316` — stats accumulator hardcodes `running` bucket.
- `ops/spawn/api.py:202` — `running` + `exited_at is not None` heuristic label.

These are **implementation scope** for shipping `finalizing`. R-01 updates
each; they cannot stay on the current literals without visibly miscounting
or rejecting valid statuses.

## Verified assumptions

- **`execute_with_finalization` has the canonical runner-origin finalize
  site** — confirmed at `runner.py:825-867`. The `finalizing` state must be
  entered *before* pipe-drain / redaction / report-extraction work runs.
- **`POST_EXIT_PIPE_DRAIN_TIMEOUT_SECONDS` bounds post-exit work** —
  confirmed at `runner.py:369-395`. The drain window is ~10s; report
  redaction is sub-second; guardrails have their own timeout. The 120s
  heartbeat window on `finalizing` is well above realistic upper bounds.
- **`diag.py:145` already skips when `MERIDIAN_DEPTH > 0`** — confirmed;
  Round 2's new gate at `reconcile_active_spawn` mirrors this semantically.
- **`update_spawn(status=...)` has no in-tree caller outside
  `mark_spawn_running`** — confirmed via `git grep` (memo `arch-cas-memo.md`
  §4). Safe to retire the public surface.
- **`validate_transition` in `spawn_lifecycle.py` is currently unused** —
  confirmed via `git grep`. Round 2 wires it into the new helpers
  (R-02, R-03) rather than deleting it.

## F-finding verdict table

| Finding | Status | How addressed | Primary spec / refactor |
|---|---|---|---|
| F1 (origin first-class) | addressed | `SpawnOrigin` enum, `origin` on event, `terminal_origin` on record, projection keys off it. | S-PR-001, S-PR-005, R-02 |
| F2 (atomic `running → finalizing`) | addressed | `mark_finalizing` CAS, reconciler guard in `finalize_spawn`, `SpawnUpdateEvent` never downgrades terminal. | S-LC-004, S-RP-008, S-PR-006, R-03 |
| F3 (depth gate on single-row path) | addressed | Gate moved inside `reconcile_active_spawn`; batch wrapper inherits. | S-RP-006, R-05 |
| F4 (running heartbeat) | addressed | Runner-owned 30s tick, probe evidence per harness. | S-RN-004, R-06 |
| F5 (full writer surface) | addressed | 11-writer table with explicit origin per site. | S-RN-005, R-02 |
| F6 (consumer audit) | addressed | `view_map`, `--status` validator, stats all updated; constants derive from single source. | S-CF-001..003, R-01 |
| F7 (decide/write split) | addressed | Pure `decide_reconciliation` + I/O shell. | S-RP-009, R-04 |
| F8 (heartbeat stat cost) | addressed | Helper kept isolable for future `scandir`/single-artifact swap. | R-06 (nit-scope) |

## Open questions (non-blocking)

- **Heartbeat task implementation model.** The runner is already
  asyncio-heavy in primary; streaming runner has its own loop. Implementation
  should choose between a shared `launch/heartbeat.py` helper and inline
  per-runner tasks; the contract (S-RN-004) is implementation-agnostic.
- **OpenCode sample size.** `probe-heartbeat.md` reports only 10 OpenCode
  spawns, max gap 1.2s. Sample is too small to prove a safe upper bound —
  the runner-heartbeat decision is already driven by Claude (153.9s) and
  Codex (86.8s), so OpenCode uncertainty is non-blocking. If the heartbeat
  task is chosen to be shared, OpenCode benefits automatically.
- **`exited_at` removal cycle.** Blocked on R-08 (deferred). Not a
  correctness concern; a future-cycle cleanup.

## Residual risks

- **Heartbeat-task starvation.** A runner whose event loop is blocked
  (synchronous GIL contention, blocked I/O thread) could miss its 30s tick.
  At 4× safety factor, three consecutive missed ticks (90s) are required to
  reach the window. This is detectable from outside (no heartbeat mtime
  advance) and is itself a real liveness signal — a runner that can't tick
  is genuinely unresponsive.
- **Legacy-row origin-inference correctness.** The shim relies on the
  `LEGACY_RECONCILER_ERRORS` set. Any new reconciler-origin error code added
  between now and R-07's deletion window must be added to the set or tagged
  explicitly via `origin="reconciler"` (and the latter is now mandatory for
  new code). A unit test asserts the shim is never consulted when `origin`
  is present.
- **`mark_finalizing` CAS miss under contention.** A runner losing the CAS
  race gracefully writes its terminal finalize anyway (authoritative), and
  the projection authority rule supersedes the prior reconciler-origin
  terminal. This path is explicitly tested.
