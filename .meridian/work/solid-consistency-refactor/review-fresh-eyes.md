# Fresh-Eyes Review: SOLID & Consistency Refactor Design

**Reviewer perspective:** Independent review, not informed by prior review documents. Read design.md, then read every source file it proposes to change. Looking for what focused reviewers (correctness, risk, SOLID principles) might miss.

---

## 1. Does the 12-Phase Sequence Tell a Coherent Story?

**Mostly yes, but with a structural tension the design doesn't acknowledge.**

Phases 1-8 are a **clean code refactor**: DRY extraction, interface segregation, consistent error semantics. Phases 9-12 are **safety/correctness fixes**: lock-order inversions, PID race windows, state machine enforcement. The design presents them as a single linear sequence, but they serve two different masters.

The problem: Phases 9-12 are the ones that fix real bugs (lock-order inversion, PID-before-fork crash window, stale detection of reused chat IDs). But they're gated behind 8 phases of cleanup that touch ~40 files. If Phase 7 (Harness ISP, Medium risk, 7 files) introduces a regression, Phases 9-12 are blocked.

**Recommendation:** The design should explicitly state that Phases 9, 10, 12 can be implemented independently of Phases 1-8. The dependency claim at line 1404-1408 is weak:
- "Phase 9 uses `lock_file` from Phase 2's shared event store" — but `_lock_file` already exists in session_store.py; you don't need Phase 2's extraction to fix the lock order.
- "Phase 12 uses `read_events` from Phase 2" — but it could use the existing `_read_events` just as well.

The safety fixes are being held hostage by the aesthetics passes. Ship them independently.

---

## 2. Unstated Assumptions

### 2a. JSONL files stay small enough to read fully into memory

The entire design assumes JSONL files are small enough to `read_text()` or `readlines()` in one shot. This is true today but the design introduces no guardrails. As spawns accumulate over long-running projects, `spawns.jsonl` grows monotonically (append-only, no compaction). Every `list_spawns()` call reads the entire file, parses every event, and builds every SpawnRecord.

**Specific hot path:** `get_spawn()` (line 546-553) calls `list_spawns()` which reads ALL events and builds ALL records, then linearly scans for one ID. This is called from:
- `runner.py` (line 475, 565) — on every spawn execution
- `report.py` (line 50) — on every report create
- `execute.py` (line 537) — on background execution start
- `api.py` (line 372, 400) — on wait/show

None of the 12 phases address this. The Phase 2 `read_events` extraction actually makes this slightly worse by hiding the full-file read behind a clean API — callers will assume it's cheap.

**Not blocking, but missing:** A compaction strategy or indexed lookup should at least be mentioned as a future concern.

### 2b. `_records_by_session()` is called multiple times without caching

Similarly, `_records_by_session()` re-reads and re-parses `sessions.jsonl` on every call. It's invoked 6 times across `get_session_active_work_id`, `resolve_session_ref`, `get_session_harness_id`, `get_session_harness_ids`, `get_last_session`, and `cleanup_stale_sessions`. In a single `run_harness_process` call (process.py), several of these are called in sequence — each time re-reading the entire file.

Phase 2's `read_events` doesn't help here. Phase 6's `session_scope` might help a bit by reducing call sites, but the underlying read-everything-every-time pattern persists.

### 2c. The design assumes single-machine deployment

`fcntl.flock` is process-local on Linux and doesn't work across NFS or networked filesystems. The design doubles down on `flock` (Phases 9, 10) without noting this constraint. If someone runs meridian with `.meridian/` on a shared drive, all the careful lock ordering becomes meaningless.

---

## 3. Missing Phases: Problems Visible in the Code That the Design Doesn't Address

### 3a. `get_spawn()` is O(N) and called in hot loops

As noted above, `get_spawn()` linearly scans all records. This is fine for 10 spawns but becomes noticeable at 1000+. The design's Phase 2 (shared event store) was the natural place to add an indexed lookup or at least a `get_by_id` that short-circuits the fold. It doesn't.

### 3b. Double-call to `_state_root()` on the same line

Several call sites resolve state paths twice unnecessarily:
```python
# api.py line 136:
spawns = list(reversed(reconcile_spawns(_state_root(repo_root), spawn_store.list_spawns(_state_root(repo_root)))))
```

Phase 4 (Ops Helper Consolidation) addresses `_state_root` duplication across modules, but doesn't address the pattern of calling it twice per expression. The Phase 4 helpers should produce a `(repo_root, state_root)` tuple that callers use, not two separate calls.

### 3c. `_utc_now_iso()` is duplicated in both stores

Both `spawn_store.py` (line 167) and `session_store.py` (line 83) define identical `_utc_now_iso()` functions. Phase 2 doesn't mention deduplicating this (it should go in `event_store.py` or a time utility).

### 3d. No mention of the `StateRootPaths` vs `StatePaths` situation

`spawn_store.py` uses `StateRootPaths.from_root_dir(state_root)` while `session_store.py` also uses `StateRootPaths.from_root_dir(state_root)`. But the `paths.py` module has `resolve_state_paths()` returning a `StatePaths`. These are two different path-resolution mechanisms for the same concept. Phase 2's refactored stores should pick one consistently. The design doesn't mention this.

### 3e. `collect_active_chat_ids` re-resolves state paths from repo_root

`collect_active_chat_ids()` (session_store.py line 381-401) imports `resolve_state_paths` internally and does its own path resolution from `repo_root`, unlike every other function in the module which takes `state_root` directly. This inconsistency is visible in the code but not addressed in the design. Phase 3 proposes changing the return type but doesn't fix the parameter inconsistency.

---

## 4. Interaction Effects Between Phases

### 4a. Phase 2 + Phase 11: `exclude_none` behavior change

**This is subtle and the design doesn't call it out.**

Current code: `event.model_dump(exclude_none=True)` — None fields are omitted from JSON.
Phase 2 proposes: `event.model_dump(mode="json")` — None fields become `null` in JSON.

Phase 11's `_record_from_events` fold uses `if event.status is not None` checks extensively. If None is now serialized as `null`, Pydantic will deserialize it back as `None`, so the fold still works. **But** the JSONL file grows larger (more fields per event), and old meridian reading new-format files will see `null` values where before there were missing keys.

This is probably fine (Pydantic handles both), but the design should explicitly confirm backward/forward compatibility. A single sentence saying "old readers handle null values correctly because Pydantic's `model_validate` treats missing keys and explicit null identically for Optional fields" would suffice.

### 4b. Phase 6 + Phase 9: Session scope exception handling interacts with lock ordering

Phase 6 introduces `session_scope` which wraps `stop_session()` in a try/except that swallows exceptions. Phase 9 changes the lock acquisition order in `start_session` and `cleanup_stale_sessions`. If Phase 6 is implemented first and Phase 9's changes later break `stop_session` (e.g., by introducing a new lock that `stop_session` needs), the exception swallowing in `session_scope` would silently hide the failure.

**Recommendation:** Phase 9 should come before Phase 6, or Phase 6's error handling should be implemented only after Phase 9 is complete. The design's dependency graph shows Phase 6 before Phase 9, which is the wrong order for this interaction.

### 4c. Phase 7 + Phase 10: Registry split interacts with primary launch lock

Phase 7 splits the adapter into `SubprocessHarness`, `StreamParsingHarness`, `SessionAwareHarness`, and `InProcessHarness`. Phase 10 modifies `run_harness_process` which calls `harness_registry.get(HarnessId(...))` — a call that Phase 7 changes to `get_subprocess_adapter()`. If Phase 10 is implemented on top of Phase 7, the code will work. But if someone implements Phase 10 first (which is safe from a correctness standpoint), Phase 7 will need to re-touch the same code.

This is a minor coordination risk, but the design should acknowledge it.

### 4d. Phase 11 + Phase 2: validate_transition breaks finalize_spawn_if_active

Phase 11 adds `validate_transition()` calls to `finalize_spawn()`. But `finalize_spawn_if_active()` currently allows `queued -> failed` (e.g., reaper finding a missing PID after grace period). The design's `_ALLOWED_TRANSITIONS` table includes `"queued": frozenset({"running", "failed", "cancelled"})`, so this works. But `finalize_spawn()` (not `_if_active`) hardcodes `validate_transition("running", status)` at design line 1177 — meaning `finalize_spawn()` can ONLY be called when the spawn is running.

Today, `finalize_spawn` is called from `execute.py` line 731 on background launch OSError when the spawn is in `queued` state:
```python
spawn_store.finalize_spawn(
    context.state_root,
    context.spawn.spawn_id,
    status="failed",
    exit_code=1,
    error=str(exc),
)
```

This call would crash with Phase 11's validation because the spawn's from_status is `queued`, not `running`. The design's `finalize_spawn` validates `("running", status)` but the caller is finalizing a queued spawn. **This is a concrete breakage.**

---

## 5. User-Facing Impact

### 5a. Phase 3: `KeyError` -> `ValueError` changes CLI error output

The design notes this but underestimates the impact. Any scripts or tools that parse meridian's stderr for `KeyError` will break. This should be explicitly noted as a **breaking change** in the commit message.

### 5b. Phase 7: Registry API change blocks third-party harness adapters

If anyone has written a custom harness adapter implementing the current `HarnessAdapter` protocol, the ISP split breaks their code. They now need to implement the correct subset protocols instead. The design should specify a migration path or deprecation period.

### 5c. Phase 11: validate_transition may surface as unexpected crashes

If any edge case currently produces an "illegal" transition (e.g., a double-finalize due to a race), it silently succeeds today (the fold just applies the last event). After Phase 11, it raises `ValueError`, which could crash a CLI command mid-operation. The design should specify that validation is **logged as a warning** rather than raised as an exception, at least initially.

### 5d. Phase 12a: Configurable stale threshold

Adding `stale_threshold_secs` to config is a user-visible feature. The design doesn't specify the config key name, default, documentation, or validation. What happens if someone sets it to 0? Or -1?

---

## 6. Performance Concerns

### 6a. Phase 2: `read_text()` vs `readlines()` — memory profile change

The current code uses `handle.readlines()` which returns a list of strings. The design's `data_path.read_text(encoding="utf-8")` reads the entire file into a single string, then `splitlines()` creates a second copy as a list. For a 100MB spawns.jsonl (unlikely today, possible in future), this doubles memory usage temporarily. Not blocking, but the design should acknowledge the tradeoff.

### 6b. Phase 6: `session_scope` adds another `get_session_active_work_id` call

Phase 6's `session_scope` calls `get_session_active_work_id()` on every session start. This reads and parses `sessions.jsonl` fully. Combined with the `start_session()` call (which also reads for ID generation), a single session start now reads the JSONL file at least twice. Neither the current code nor the design addresses this.

### 6c. Phase 11: `validate_transition` adds `get_spawn()` call to every write

The design's `mark_spawn_running` calls `get_spawn()` before validation. `get_spawn()` reads the entire JSONL and builds all records. This means every state transition now requires a full file read, even if the caller already has the record. The design should use the record the caller already holds, not re-read from disk.

---

## 7. What's Actually Good

To be fair, several aspects of this design are excellent:

1. **Phase 1a is a real bug fix.** The missing `ValidationError` catch in `spawn_store._parse_event` means a single corrupted event line crashes all read paths. This should ship immediately, independently of everything else.

2. **Phase 9's lock-order analysis is thorough.** The three-phase detect/mutate/delete pattern with re-probing is well-reasoned and correctly handles the TOCTOU gap.

3. **Phase 10's PID intent file** is a clever approach to the fork crash window. The "parent alive means still launching" inference is sound.

4. **Phase 12b** correctly identifies the set-subtraction bug in `collect_active_chat_ids`. The fix (sequential event processing) is clean and correct.

5. **Phase 2's shared event store** is the right abstraction. The two stores have clearly drifted and a shared foundation will prevent future divergence.

---

## 8. Summary of Actionable Findings

| # | Finding | Severity | Action |
|---|---------|----------|--------|
| 1 | Safety fixes (9, 10, 12) are unnecessarily gated behind aesthetic refactors (1-8) | **High** | Allow independent implementation |
| 2 | Phase 11's `finalize_spawn` hardcodes "running" as from_status, breaks queued->failed path | **High** | Fix validation to check actual record status |
| 3 | Phase 11's `validate_transition` adds full file reads to every write | **Medium** | Pass existing record to avoid re-read |
| 4 | No compaction/indexed-lookup strategy as JSONL grows | **Medium** | Mention as future concern in design |
| 5 | Phase 2 changes `exclude_none` semantics without stating compatibility guarantee | **Medium** | Add explicit forward/backward compat statement |
| 6 | Phase 6 before Phase 9 creates silent failure masking risk | **Medium** | Reorder or note interaction |
| 7 | `get_spawn()` is O(N) through `list_spawns()`, not addressed | **Low** | Phase 2 could add `get_by_id` shortcut |
| 8 | `_utc_now_iso()` not deduplicated in Phase 2 | **Low** | Add to event_store.py |
| 9 | `collect_active_chat_ids` parameter inconsistency (repo_root vs state_root) not addressed | **Low** | Fix in Phase 3 or 12b |
| 10 | Phase 12a stale threshold has no validation/docs spec | **Low** | Specify bounds and docs |
