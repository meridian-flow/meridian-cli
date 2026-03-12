# Implementation Risk Review

Scope: static review of `.meridian/work/solid-consistency-refactor/design.md`, `.meridian/work/auto-work-items/design.md`, and the current implementation.

Method: document review plus code inspection only. No tests run.

## Overall Assessment

The phase plan is directionally right, but the ordering is not fully safe as written.

- Phase 9 is the biggest blocker. The proposed lock rewrite fixes one inversion, but it introduces a chat-ID allocation race and a stale-cleanup TOCTOU that can append a stop event for a newly restarted session.
- Phase 3 is not a simple prerequisite. The `collect_active_chat_ids(): None -> frozenset()` change alters failure semantics in `process.py` and can turn a read error into an aggressive orphan-materialization sweep.
- Phases 4 and 5 are not really independent because both converge on `src/meridian/lib/ops/runtime.py` and the same ops modules.
- Auto-work cleanup in `auto-work-items` Section 7 does not yet integrate cleanly with Phase 6. It needs SessionScope-level state and an active-session/reference check that the design does not include.

## 1. Dependency Accuracy

### Phase 1-3 are not all true prerequisites

- Phase 1a is folded into Phase 2 anyway. If Phase 2 lands first, `spawn_store._parse_event` gets fixed as part of the shared reader. It is useful as a quick safety patch, but not a hard prerequisite.
- Phase 3 is not a clean prerequisite for later work. The `update_work_item()` exception cleanup is isolated, but the `collect_active_chat_ids()` return-type change at `solid-consistency-refactor/design.md:257-269` is behavior-changing because `_sweep_orphaned_materializations()` currently treats `None` as "abort cleanup" and `frozenset()` as "no active sessions, safe to sweep" in `src/meridian/lib/launch/process.py:158-185`.
- Phase 6 does not actually depend on Phase 2. `SessionScope` can call the current `start_session()`, `stop_session()`, `get_session_active_work_id()`, and `update_session_work_id()` directly. The stated dependency at `solid-consistency-refactor/design.md:787` is overstated.

### Phases 4 and 5 are not truly independent

- Both phases edit `src/meridian/lib/ops/runtime.py` and both touch the same ops modules (`work.py`, `report.py`, and likely `spawn/api.py`).
- If Phase 5 uses Option B from `solid-consistency-refactor/design.md:382-392`, it stops being independent entirely because it changes the manifest contract and the `DirectAdapter` tool path, which currently consumes `OperationSpec.handler` directly in `src/meridian/lib/harness/direct.py:115-149`.
- Recommendation: either combine 4 and 5 into one "ops surface cleanup" branch or do 4 first, then 5 immediately after with no unrelated work between them.

### Hidden couplings the design understates

- Phase 2 does not fully isolate session-state mechanics yet. `session_store` still imports `next_chat_id` from `spawn_store` today (`src/meridian/lib/state/session_store.py:14`), so the shared JSONL extraction only removes part of the coupling. That matters because Phase 9's `start_session()` rewrite needs session-local ID reservation semantics, not just shared append/read helpers.
- Phase 7 is broader than the document implies. Registry callers do not live only in harness adapters; launch, prompt resolution, and direct mode all depend on `HarnessRegistry.get()` returning the kitchen-sink `HarnessAdapter` today (`src/meridian/lib/harness/registry.py:18-64`).
- Phase 8 is not uniformly generic. The manifest-driven registration pattern exists in several CLI modules, but `doctor_cmd` and `sync_cmd` are not the same shape, so the phase is likely "consolidate most group registration" rather than a complete one-shot replacement.

## 2. Migration Safety

### Intermediate-state risks

- Phase 3 must update store code and CLI/MCP callers atomically. A half-migration leaves mixed `KeyError`/`ValueError` handling in work operations.
- Phase 6 is only independently shippable if it is a narrow extraction. The current primary and child flows are similar, but not identical:
  - child execution uses a live harness-session observer in `src/meridian/lib/ops/spawn/execute.py:495-502`
  - primary launch does orphan sweep before start and extracts the latest harness session ID after process exit in `src/meridian/lib/launch/process.py:426-430` and `src/meridian/lib/launch/process.py:527-546`
- A `SessionScope` that claims to own "harness session ID observation" but only wraps start/stop will create another partial abstraction.
- Phase 10a is not independently safe unless the writer and reader land together. Writing `launch_intent.json` without reaper support is dead code; teaching reaper to read it without writers means the new branch never executes.
- Phase 11 is not just refactoring. Once `validate_transition()` is enforced, existing recovery paths become behaviorally constrained. The migration has to update every place that currently depends on ad hoc status repair in one commit.

## 3. Testing Gaps

The plan says each phase is independently testable, but it does not define the gates needed for that to be true.

### Shared infrastructure that needs tests before shipping

- `event_store` needs targeted unit tests for:
  - trailing truncated line recovery
  - mid-file malformed JSON skip
  - schema-validation skip parity with both spawn and session events
  - concurrent append serialization across processes
- `SessionScope` needs smoke or integration tests for:
  - primary launch path
  - child spawn execution path
  - auto-created work inheritance into `MERIDIAN_WORK_DIR`
  - materialization cleanup on both success and exception
  - harness session ID update timing

### Phase-specific gaps

- Before Phase 3 ships, add a regression test for `collect_active_chat_ids()` failure handling in the orphan-materialization sweep path. Today there is no test covering the `None` sentinel behavior in `src/meridian/lib/launch/process.py:171-183`.
- Before Phase 5 ships, add one async non-blocking test per converted module. Current code clearly blocks in `src/meridian/lib/ops/report.py:227-245`, `src/meridian/lib/ops/work.py:572-632`, and `src/meridian/lib/ops/catalog.py:390-411`, but there is no event-loop regression test guarding the fix.
- Before Phase 7 ships, add registry/type-routing tests proving:
  - direct mode never goes through subprocess-only APIs
  - subprocess launch code cannot receive `DirectAdapter`
- Before Phase 8 ships, add CLI registration tests for default command behavior and missing-handler failures.
- Before Phase 9 ships, add multiprocessing tests for:
  - start/stop/cleanup with reused `chat_id`
  - no deadlock under concurrent `start_session()`, `stop_session()`, and `cleanup_stale_sessions()`
  - crash after acquiring session lock but before appending the start event
- Before Phase 10 ships, add crash-window tests for:
  - intent file with `child_pid=None`, parent alive
  - intent file with `child_pid=None`, parent dead
  - intent file with `child_pid` set but missing `.pid` file
  - `active-primary.lock` mutual exclusion and stale-lock recovery
- Before Phase 11 ships, add transition-table tests plus end-to-end reaper/runner/store tests for each legal transition.
- Before Phase 12a ships, add heartbeat tests proving a quiet but healthy process is not marked stale.
- Before Phase 12b ships, add the reused-chat-id regression that the design already describes.

Current coverage is useful but insufficient. There are tests for basic stale-session cleanup, reaper happy paths, and auto-generated work rename flows in `tests/test_state/test_session_store.py`, `tests/test_state/test_reaper.py`, and `tests/ops/test_work.py`; there are not concurrency or mixed-version tests for the risky phases.

## 4. Rollback Risk

Several phases are only rollback-safe if reverted as a unit.

- Phase 3 is partially rollback-hostile because the `collect_active_chat_ids()` sentinel change affects cleanup policy, not just typing.
- Phase 6 is safe to revert only if it remains a pure extraction. If SessionScope also takes on cleanup or harness-session-id behavior, reverting it means restoring two launch paths in lockstep.
- Phase 10a must be rolled back with the corresponding reaper changes.
- Phase 10b must be rolled back with the lock cleanup logic. A flock-based `active-primary.lock` with old unlink-only cleanup is inconsistent, and the reverse is also inconsistent.
- Phase 11 is high rollback cost because it changes validation boundaries. Once callers rely on transition helpers, reverting just the state machine leaves dead imports or unreachable states.

Recommendation: split high-coupling phases so rollback units match runtime behavior:

- Split Phase 10 into `10a intent-file crash recovery` and `10b primary-launch mutex`.
- Split Phase 11 into `11a transition model` and `11b stats dedupe/string-literal cleanup`.
- Split Phase 12 into `12a heartbeat/configurable stale threshold` and `12b reused-chat-id fix`.

## 5. Scope Creep

The following phases are carrying more than one kind of change and should be split further.

- Phase 3 mixes error-semantics cleanup with a session-activity semantic change.
- Phase 10 combines two unrelated correctness fixes that touch different failure domains.
- Phase 11 combines a state-machine refactor with stats aggregation cleanup.
- Phase 12 combines reaper liveness policy with a session-log correctness fix.

Lower-risk cleanup phases could also be trimmed:

- Phase 8 should probably exclude bespoke CLI groups and only consolidate the pure manifest-registration modules first.
- Phase 7 should explicitly budget for registry callsite migration outside the adapter files themselves.

## 6. Concurrency In Practice

### Phase 9 has two new race conditions as written

1. `start_session()` lock-before-event needs an ID reservation strategy.

- The design changes `start_session()` to acquire the per-session lock before writing the start event at `solid-consistency-refactor/design.md:912-935`.
- That is correct for the crash window, but the snippet silently drops the current global-lock protection around `next_chat_id()`.
- If two processes generate `cN` from the same log snapshot before either appends a start event, they can choose the same chat ID.
- The fix needs either:
  - a global reservation step for chat ID generation, or
  - a retry loop that probes/locks candidate IDs without relying on a stale count.

2. The proposed stale-cleanup phases can append a stop event for a newly restarted session.

- The new `cleanup_stale_sessions()` detects a stale lock, releases it, then later appends stop events under the global lock at `solid-consistency-refactor/design.md:844-903`.
- If another process restarts the same `chat_id` between detection and the stop-write phase, cleanup can append a stop event for the new live session.
- The Phase 3 re-probe only protects lock-file deletion; it does not protect event-log correctness.
- The fix needs a stronger identity check than `chat_id` alone, such as matching the stale lock against the exact session instance being stopped.

### Phase 9 also needs failure cleanup

- If `start_session()` acquires the per-session lock first and the later append fails, the new code must release the lock before bubbling the exception.
- The design snippet does not show that cleanup path.

### Phase 10 changes lock behavior in ways that need lock-aware cleanup

- `cleanup_orphaned_locks()` currently only parses JSON and unlinks the file in `src/meridian/lib/launch/process.py:115-137`.
- Once `active-primary.lock` becomes a real flock mutex, cleanup has to probe the flock before unlinking, not just inspect `child_pid`.

## 7. Auto Work Items Section 7 vs. Phase 6

Section 7 of `auto-work-items/design.md` does not integrate cleanly with the proposed SessionScope extraction yet.

### Hidden dependency

- Auto-work creation is already duplicated in both launch paths today:
  - `src/meridian/lib/ops/spawn/execute.py:466-480`
  - `src/meridian/lib/launch/process.py:431-446`
- If cleanup is added before Phase 6, the code will duplicate the stop-path logic in both places and then immediately re-extract it in Phase 6.
- Recommendation: either defer cleanup until SessionScope exists, or add a shared cleanup helper first and call it from both sites.

### The cleanup rule is unsafe for shared active work

- Section 7 says "only the last session to stop would attempt cleanup" at `auto-work-items/design.md:264-271`, but the proposed `_cleanup_auto_work_item()` does not verify that.
- If two live sessions reference the same untouched auto-generated work item, the first one to stop can delete the directory while the second session is still active.
- SessionScope needs to check whether any other active session still points at that `work_id` before deleting it.

### SessionScope needs more state than the draft carries

- `SessionScopeResult` currently returns only `chat_id` and `work_id` at `solid-consistency-refactor/design.md:432-491`.
- Cleanup needs at least:
  - whether the work item was auto-created for this session
  - the current active work item at exit, not just the one seen at entry
- Without that, a later `work start`, `work switch`, or `work clear` during the session makes exit-time cleanup ambiguous.

### GC needs the same active-session guard

- The periodic GC in `auto-work-items/design.md:273-296` is not safe to run opportunistically unless it also skips work items referenced by active sessions.
- Otherwise `work list` or `status` can race with a live session that has not yet written any files.

## Recommended Ordering

I would not ship the phases in the current order. A lower-risk order is:

1. Phase 1a only if you want the immediate malformed-event safety patch.
2. Phase 5 and Phase 4 together, or 4 then 5 immediately after.
3. Phase 2.
4. Phase 9, but split into:
   - `9a start-session lock ordering and chat-ID reservation`
   - `9b stale-session cleanup rewrite`
5. Phase 6, with auto-work cleanup hooks designed in at the same time if that feature is still planned.
6. Phase 10a and 10b as separate rollback units.
7. Phase 7.
8. Phase 8.
9. Phase 11 split.
10. Phase 12b (`collect_active_chat_ids` ordering fix) earlier than 12a if you want the smallest correctness win first.
11. Phase 12a last, because it is policy-heavy and touches both runner and reaper.

## Bottom Line

The main implementation risk is not the abstractions themselves; it is shipping session and launch refactors before the underlying concurrency semantics are correct. Fix the session-lock correctness story first, keep SessionScope narrow until that is stable, and split the mixed phases so tests and rollbacks match real runtime behavior.
