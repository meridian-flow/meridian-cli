# Task: Fix Accuracy Findings in fs/ Spawn-Lifecycle Docs

An accuracy reviewer (p1775) flagged factual errors in the recently-updated fs/ docs. Apply targeted fixes. Do NOT rewrite — address each finding in place.

## Authoritative correction (propagated error from original writer prompt)

The original writer prompt incorrectly said `mark_finalizing` runs *before* drain. The correct ordering per `src/meridian/lib/launch/runner.py` and `streaming_runner.py` is:

1. Harness process exits (retry loop breaks)
2. Redact + persist `report.md` (if present)
3. `enrich_finalize()` (report extraction from output)
4. `extract_latest_session_id()` and persist via `update_spawn`
5. Guardrails, retry handling
6. (After retry loop exits, in finalization `finally`) **`mark_finalizing()` CAS** — `running → finalizing`
7. `finalize_spawn(origin="runner")` — terminal

So `finalizing` is a narrow window immediately before terminal finalize, *after* the runner has already drained output and extracted the report. It signals "terminal state is being committed" rather than "draining output". Fix the docs to reflect this.

## Findings to address

1. **`state/spawns.md:~112`** (medium) — no-`runner_pid` branch: reaper returns `FinalizeSucceededFromReport` first if durable report exists; only returns `missing_worker_pid` after startup grace AND no durable report. See `reaper.py:157-165`.

2. **`state/overview.md:~13`** (low) — spawn events list says `start/update/finalize`; actual event types are `start`, `update`, `exited`, `finalize` (`spawn_store.py:122-194`). Add `exited`.

3. **`state/overview.md:~53`** (medium) — remove/revise "no coordination signals" claim — `heartbeat` is now a live coordination artifact in the spawn dir.

4. **`launch/process.md:~31`** (medium) — primary-path sequence: `finalize_spawn(origin="launcher")` happens BEFORE `extract_latest_session_id()` in `run_harness_process` (`process.py:413-459`). Currently doc has them reversed.

5. **`launch/process.md:~66`** (high) — fix `mark_finalizing` timing per the "Authoritative correction" above.

6. **`launch/overview.md:~34` and `:~95`** (high) — same `mark_finalizing` ordering fix. Lifecycle list currently puts `mark_finalizing` before `enrich_finalize`; code does the opposite.

7. **`overview.md:~33`** (medium) — claim that `lib/launch/process.py` "calls runner" is incorrect. `run_harness_process()` is primary-launch only; subagent spawns dispatch from `ops/spawn/execute.py` directly to `execute_with_finalization()` or `execute_with_streaming()`. Fix routing description.

8. **`orphan-investigation.md:~178`** (low) — archived header is fine, but Resolution claim "heartbeat covers queued + running + finalizing" overstates queued coverage. Heartbeat starts when the worker process/connection starts (inside the running transition), not across the full queued interval. Revise to match source (`runner.py:556-589` and `streaming_runner.py:579-910`).

## Full reviewer report

See `.meridian/spawns/p1775/report.md` for verbatim findings.

## Files

- `.meridian/fs/state/spawns.md`
- `.meridian/fs/state/overview.md`
- `.meridian/fs/launch/process.md`
- `.meridian/fs/launch/overview.md`
- `.meridian/fs/overview.md`
- `.meridian/fs/orphan-investigation.md`

Source of truth files are already attached. Do not run git — orchestrator commits.
