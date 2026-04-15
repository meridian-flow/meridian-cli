# B-06 Session Mining: Root Cause Found

## Verdict

**B-06 is not a meridian bug and not a Claude Code harness bug.** It is a shell
pipeline exit-code masking issue combined with meridian's default 30-minute wait
timeout.

The prior investigator (p1868, gpt-5.4) was correct that `spawn_wait_sync()`
itself is sound. But the conclusion that the spurious completion "must come from
the Claude Code harness's `run_in_background` task-notification layer" was
**partially wrong** — the harness is reporting exactly what it sees (exit code 0
from the pipeline). The actual causal chain is simpler and fully explains every
observed instance.

## Causal Chain

1. Orchestrator runs: `meridian spawn wait p1861 2>&1 | tail -3`
2. This is backgrounded by Claude Code (`run_in_background`)
3. `meridian spawn wait` polls for ~30 minutes (default `wait_timeout_minutes`)
4. Target spawn (p1861) is still running after 30 minutes
5. `spawn_wait_sync()` raises `TimeoutError` → caught → `_emit_error(exit_code=124)`
6. Meridian exits with code **124** and prints: `error: Timed out waiting for spawn(s) 'p1861'`
7. But the command was **piped to `tail -3`**
8. Without `set -o pipefail` (not set in Claude Code's bash), the pipeline exit
   code is the **last command's exit code** — `tail -3` exits 0
9. Claude Code harness sees exit code 0 → fires `<task-notification>` with
   `<status>completed</status>` and `completed (exit code 0)`
10. Orchestrator sees "completed" notification → interprets as "spawn finished"
11. Orchestrator checks `meridian spawn show p1861` → still `running` → confusion

## Evidence from Session Transcript

### Instance 1: `wait p1843` (task `b65vrig0p`)

- **Command:** `meridian spawn wait p1843 2>&1 | tail -3` (message 223)
- **Background task started:** message 224, task ID `b65vrig0p`
- **Notification arrived:** message 307 (`completed (exit code 0)`)
- **Actual task output file:**
  ```
  error: Timed out waiting for spawn(s) 'p1843'
  ```
- **Output file timestamp:** `2026-04-14 21:20:04` (46 bytes)
- **p1843 spawned at:** ~20:49 (dir listing in message 221)
- **Wait started at:** ~20:50 (message 223)
- **20:50 + 30 min = 21:20** ✓ matches timeout

### Instance 2: `wait p1843 p1844` (task `btr6gouz1`)

- **Command:** `meridian spawn wait p1843 p1844 2>&1 | tail -5` (message 236)
- **Background task started:** message 237, task ID `btr6gouz1`
- **Notification arrived:** message 309 (`completed (exit code 0)`)
- **Actual task output file:**
  ```
  error: Timed out waiting for spawn(s) 'p1843', 'p1844'
  ```
- **Output file timestamp:** `2026-04-14 21:23:10` (55 bytes)
- **Wait started at:** ~20:53 (p1844 spawned at 20:53)
- **20:53 + 30 min = 21:23** ✓ matches timeout

### Instance 3: `wait p1861` (task `bagr4q2ze`) — the primary B-06 report

- **Command:** `meridian spawn wait p1861 2>&1 | tail -3` (message 446)
- **Background task started:** message 447, task ID `bagr4q2ze`
- **Notification arrived:** message 449 (`completed (exit code 0)`)
- **Actual task output file:**
  ```
  error: Timed out waiting for spawn(s) 'p1861'
  ```
- **Output file timestamp:** `2026-04-14 23:25:47` (46 bytes)
- **Spawn launched at:** 22:55:40 (buvawoxks output timestamp)
- **22:55 + 30 min = 23:25** ✓ matches timeout
- **p1861 heartbeat at detection:** `2026-04-14 23:25:40` (16s before check)
- **p1861 output.jsonl:** 201 lines and growing
- **p1861 children:** actively spawning (p1862-p1867)

### Retry confirmation (message 467)

After noticing the bug, the orchestrator ran `timeout 5 meridian spawn wait p1861`
(without pipe). It was terminated by the 5s timeout (SIGTERM, not natural exit).
This proves `spawn_wait_sync()` was correctly blocking — it never returned early
on its own.

## Hypothesis Evaluation

### Hypothesis A: Claude Code harness fires premature notifications

**Refuted.** The harness faithfully reports the pipeline exit code. The pipeline
exits 0 because `tail -3` succeeds, masking meridian's exit code 124. The harness
is behaving correctly.

### Hypothesis B: Real meridian bug missed by prior investigator

**Refuted.** `spawn_wait_sync()` correctly times out after 30 minutes and exits
124. The prior investigator's code-path analysis was accurate. The retry at
message 467 confirms wait blocks correctly.

### Hypothesis C: Environment mismatch between wait and show

**Refuted.** Both used the same repo root. The wait simply timed out.

### Hypothesis D: Something else entirely

**Confirmed: exit-code masking via pipe + timeout = false success signal.**

## Root Causes (Two Orthogonal Issues)

### Issue 1: Pipeline exit-code masking (primary)

The pattern `meridian spawn wait ... 2>&1 | tail -N` masks non-zero exit codes.
`tail` always exits 0 if it received input. Without `pipefail`, the shell reports
the last command's exit code.

This is not a bug in any component — it's a usage pattern that defeats error
propagation. The orchestrator wrote this command, and without `pipefail` the
harness cannot distinguish success from timeout.

### Issue 2: Default 30-minute wait timeout too short for impl-orchestrators

`wait_timeout_minutes` defaults to 30.0 (`settings.py:688`). Impl-orchestrators
routinely run 30-60+ minutes. The timeout fires during normal operation, not as
an error recovery mechanism.

The timeout is working as designed — but the default is wrong for the common
case of waiting on long-running orchestrators.

## Recommended Fixes

### Fix 1: Stop piping `spawn wait` output (orchestrator prompt guidance)

The orchestrator should use `meridian spawn wait p1861` without piping to
`tail -3`. The `| tail -3` was added to keep context small, but it masks errors.
Alternative: use `2>&1; echo "EXIT:$?"` to preserve both output truncation and
exit code visibility.

### Fix 2: Increase default `wait_timeout_minutes` or accept `--timeout` in wait

For impl-orchestrators, 30 minutes is frequently too short. Options:
- Increase default to 120 minutes
- Have orchestrator agents pass explicit `--timeout 120`
- Document the timeout in the `meridian-spawn` skill

### Fix 3 (defense-in-depth): Make `spawn wait` output parseable terminal evidence

Per the prior investigator's recommendation: include the terminal status in
wait's stdout on success, so the caller can verify the spawn actually finalized
even if the exit code is masked.

## Code References

- `spawn_wait_sync()`: `src/meridian/lib/ops/spawn/api.py:580-648`
- Timeout raise: `api.py:636-637` (`TimeoutError`)
- Error handler: `src/meridian/cli/main.py:1340-1341` (exit code 124)
- Default timeout: `src/meridian/lib/config/settings.py:688` (`wait_timeout_minutes: float = 30.0`)

## Status

**B-06 closed as not-a-bug.** Two actionable follow-ups:
1. Fix orchestrator prompt to not pipe `spawn wait` through `tail`
2. Consider increasing default `wait_timeout_minutes` for long-running spawns
