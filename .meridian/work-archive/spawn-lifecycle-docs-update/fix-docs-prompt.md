# Task: Fix Accuracy Findings in docs/ Spawn-Lifecycle Updates

An accuracy reviewer (p1776) flagged factual errors in the recently-updated user-facing docs. Apply targeted fixes. Do NOT rewrite.

## Authoritative correction (propagated error from original writer prompt)

The original writer prompt incorrectly said `finalizing` means "harness has exited and the spawn is draining output / emitting its report." That's wrong. Per `src/meridian/lib/launch/runner.py` and `streaming_runner.py`:

1. Harness exits → retry loop
2. `report.md` redacted + persisted
3. `enrich_finalize()` extracts report from output
4. Session ID extracted + persisted
5. Guardrails, retry handling
6. **After retry loop exits**, in finalization `finally`: `mark_finalizing()` CAS (`running → finalizing`)
7. Immediately after: `finalize_spawn(origin="runner")` → terminal

So `finalizing` is a narrow window between "all runner post-exit work is done" and "terminal state committed." The drain/extract/report work happens while status is still `running`. User-facing description should be along the lines of "the spawn has finished its work and is committing its terminal state" — not "draining output."

## Findings to address

1. **`docs/commands.md:~85`** and **`docs/mcp-tools.md:~44`** — `finalizing` description wrong per the correction above. Revise user-facing language.

2. **`docs/troubleshooting.md:~62`** — "no heartbeat has been recorded for 120s" is too narrow. Reaper activity check uses any of `heartbeat`, `output.jsonl`, `stderr.log`, `report.md` — the 120s window applies to any of them. See `reaper.py:26-27, 92` (`_ACTIVITY_ARTIFACTS`, `_HEARTBEAT_WINDOW_SECS`). Revise to "no recent activity on the spawn's artifacts (heartbeat, output, stderr, or report) for 120s."

3. **`docs/troubleshooting.md:~64-65`** — `orphan_run` vs `orphan_finalization` split is keyed to the recorded `status` at reconcile time, not to a "before/after harness exit" semantic. `orphan_finalization` means the spawn record was `status==finalizing` when reaped; `orphan_run` means it was `status==running` (or `queued`, effectively). Rephrase to describe the classification in terms of status at reap time, and note that because drain/extract happens while still `running`, a crash during drain typically produces `orphan_run`, while `orphan_finalization` indicates a crash in the narrow finalize window after post-exit work completed.

4. **`docs/_internal/ARCHITECTURE.md:~271`** — Event-sourcing `start` event example shows `"status":"running"`. Primary and child spawns both start with `"status":"queued"` (`process.py:325, 341`, `runner.py:515, 530`), then transition to `running` via `mark_spawn_running()` (`runner.py:558`). Fix the example.

5. **`docs/_internal/ARCHITECTURE.md:~276, ~385, ~397`** — Fix `finalizing` timing claim and the "stream output → mark finalizing → extract results → finalize" sequence. Actual sequence is "extract results → mark finalizing → finalize." Update diagram and prose accordingly.

## Full reviewer report

See `.meridian/spawns/p1776/report.md` for verbatim findings.

## Files

- `docs/commands.md`
- `docs/mcp-tools.md`
- `docs/troubleshooting.md`
- `docs/_internal/ARCHITECTURE.md`

Source files are attached. Do not run git — orchestrator commits.
