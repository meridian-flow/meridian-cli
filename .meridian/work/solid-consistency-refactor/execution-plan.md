# Execution Plan: Tier 1 — Immediate Safety

## Phases

### Phase 10b — Primary-Launch Flock Mutex (🔴 High Risk)

**Files:** `src/meridian/lib/launch/process.py`, `src/meridian/lib/state/reaper.py`, `src/meridian/lib/launch/__init__.py`

**Agents:**
1. **Implementer** (gpt-5.3-codex): Write the flock-backed `primary_launch_lock()` context manager. Thread the flocked FD through the full `launch_primary()` / `run_harness_process()` lifetime. Replace `_write_lock()` / unlink pattern. Update `cleanup_orphaned_locks()` to probe flock, not JSON payload. Coordinate reaper changes so foreground reconciliation respects the flock-held window.
2. **Tester** (gpt-5.3-codex): flock mutex unit tests, real two-process concurrent launch smoke test, crash/restart cleanup smoke test, verify startup cleanup cannot remove a live flock-held lock. Process-lifetime gate: flock ownership held across full primary launch lifetime.
3. **Reviewer A** (gpt-5.4): Review correctness — flock lifetime, lock semantics, file descriptor handling, error paths.
4. **Reviewer B** (gpt-5.4): Review reaper coordination — concurrent launch contention, cleanup-vs-live-lock interaction, edge cases.

**Both reviewers must be satisfied before commit.**

---

### Phase 1 — Malformed-Event Guard + Dead Code Removal (🟢 Low Risk)

**Files:** `src/meridian/lib/state/spawn_store.py`, `src/meridian/lib/ops/spawn/api.py`

**Agents:**
1. **Implementer** (gpt-5.3-codex): Guard `ValidationError` in `spawn_store._parse_event()`. Remove dead code (`SpawnListFilters`, `reconcile_running_spawn()`). Fix `spawn_continue_sync()` to pass RuntimeContext through to `spawn_create_sync()`.
2. **Tester** (gpt-5.3-codex): Unit test proving `list_spawns()` and `get_spawn()` survive a malformed JSONL row without crashing. Verify `spawn_continue_sync()` passes RuntimeContext through.
3. **Reviewer** (gpt-5.4): Review all three changes for correctness.

---

### Phase 12a.1 — Heartbeat Lifecycle Wiring (🟡 Medium Risk)

**Files:** `src/meridian/lib/launch/heartbeat.py` (new or existing), `src/meridian/lib/launch/runner.py`, `src/meridian/lib/launch/process.py`, `src/meridian/lib/ops/spawn/execute.py`, `src/meridian/lib/state/reaper_config.py`

**Agents:**
1. **Implementer** (gpt-5.3-codex): Wire `heartbeat_scope` into background spawn execution (runner.py), primary launch (process.py), and foreground execution. Handle async/sync boundary — primary launch is synchronous, so needs threaded heartbeat writer or heartbeat started from async wrapper layer. Add validated reaper timing config with bounds.
2. **Tester** (gpt-5.3-codex): Heartbeat start/cancel/await tests. Verify heartbeat files are written in all execution paths (background spawn, primary launch, foreground). Test config validation bounds.
3. **Reviewer A** (gpt-5.4): Review lifecycle correctness — heartbeat starts before reaper window opens, cancels cleanly on exit.
4. **Reviewer B** (gpt-5.4): Review sync-primary-launch integration — threaded heartbeat writer correctness, async/sync boundary.

---

### Phase 12a.2 — Stale-Policy Flip (🟢 Low Risk)

**Files:** `src/meridian/lib/state/reaper.py`

**Agents:**
1. **Implementer** (gpt-5.3-codex): Change `_should_finalize_stale()` so live processes are never finalized as stale. Add comment about hung-but-alive processes and future health-check rule.
2. **Tester** (gpt-5.3-codex): Regression test — quiet but live PID is not finalized as stale. Smoke test for `spawn wait` on a long-running quiet spawn. Verify dead spawns (no PID alive) still get finalized correctly.
3. **Reviewer** (gpt-5.4): Review policy change — confirm no regression on dead-spawn cleanup, confirm hung-process trade-off is documented.

---

## Execution Order

```
         ┌─── Phase 10b (implement → test → review) ───┐
parallel │                                               ├─→ Phase 12a.1 (implement → test → review) ─→ Phase 12a.2 (implement → test → review)
         └─── Phase 1   (implement → test → review) ───┘
```

- **10b and 1 run in parallel** — different files, no overlap
- **12a.1 starts after both 10b and 1 are committed** — depends on stable launch/execution paths
- **12a.2 starts after 12a.1 is reviewed and committed** — policy depends on mechanism

## Flow Per Phase

1. **Implementer** writes code changes
2. **Tester** writes verification tests (unit + smoke) and runs them
3. **Reviewers** review both implementation AND tests together
4. **Primary evaluates** reviewer findings
5. **Rework** if needed (max 3 cycles, targeted — only fix what reviewers flagged)
6. **Commit** with descriptive message
7. **Smoke test** to verify no regressions

## Agent Totals

| Phase | Implementers | Testers | Reviewers | Total |
|-------|-------------|---------|-----------|-------|
| 10b   | 1           | 1       | 2         | 4     |
| 1     | 1           | 1       | 1         | 3     |
| 12a.1 | 1           | 1       | 2         | 4     |
| 12a.2 | 1           | 1       | 1         | 3     |
| **Total** | **4**   | **4**   | **6**     | **14** |

With rework cycles (max 3 per phase): up to ~20 agents.

## Review Gates

- **High risk (10b):** Both reviewers must be satisfied. If they disagree, tiebreak with a third reviewer from a different model family.
- **Medium risk (12a.1):** Both reviewers must be satisfied.
- **Low risk (1, 12a.2):** Single reviewer sufficient.
- **Rework:** If reviewers find issues, spawn targeted rework agent with reviewer findings. Re-review after rework. Max 3 cycles — escalate to user if not converging.

## Model Selection

- **Implementers:** gpt-5.3-codex (strong at code generation, follows instructions well)
- **Testers:** gpt-5.3-codex (needs to write and run code)
- **Reviewers:** gpt-5.4 (strongest reasoning, catches subtle issues)
- **Tiebreak reviewers (if needed):** opus or gemini (different model family for diversity)
