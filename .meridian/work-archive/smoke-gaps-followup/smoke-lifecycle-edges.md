# Spawn Lifecycle Edge Smoke

Date: 2026-04-14
Repo: `/home/jimyao/gitrepos/meridian-cli`
Tester lane: smoke / lifecycle edges
Design package: `.meridian/work-archive/orphan-run-reaper-fix/`

## Scope

Read first:

- `README.md`
- `tests/smoke/spawn/lifecycle.md`
- `.meridian/work-archive/orphan-run-reaper-fix/design/spec/overview.md`
- `.meridian/work-archive/orphan-run-reaper-fix/design/architecture/overview.md`
- `.meridian/work-archive/orphan-run-reaper-fix/plan/leaf-ownership.md`

Relevant EARS leaves exercised here:

- `S-LC-004`, `S-LC-006`
- `S-RP-002`, `S-RP-003`, `S-RP-006`, `S-RP-008`
- `S-PR-001`, `S-PR-002`, `S-PR-003`, `S-PR-004`
- `S-CF-002`, `S-CF-003`, `S-CF-004`
- `S-BF-001`, `S-BF-002`

`impl-orch` owns `plan/leaf-ownership.md` updates. I did not modify it.

## Summary

| Scenario | Relevant IDs | Outcome | Classification |
|---|---|---|---|
| 1. `mark_finalizing -> SIGKILL` gap | `S-LC-004`, `S-LC-006`, `S-RP-002`, `S-RP-003` | `blocked` | timing-gap |
| 2. reconciler stamp then runner finalize | `S-RP-008`, `S-PR-001`, `S-PR-002` | `verified` | working-as-designed |
| 3. double `finalize_spawn` idempotency | `S-PR-002`, `S-PR-004` | `verified` | working-as-designed |
| 4. PID reuse guard | exploratory | partial | timing-gap for real PID reuse; guard branch works |
| 5. `--status finalizing` filter | `S-CF-002` | `verified` | working-as-designed |
| 6. `spawn show` on `finalizing` | `S-CF-004` | `verified` | working-as-designed |
| 7. backfill self-repair on legacy rows | `S-BF-001`, `S-BF-002`, `S-PR-003` | `verified` | working-as-designed |
| 8. depth-gated reconciler | `S-RP-006` | `verified` | working-as-designed |
| 9. stats schema coverage | `S-CF-003` | `verified` | working-as-designed |
| 10. `spawn wait` returning `finalizing` | exploratory | not reproduced | working-as-designed / premise did not occur |

## Scenario 1

### 1. `mark_finalizing -> SIGKILL` gap

Outcome: `blocked`
Classification: timing-gap

Setup:

- disposable git repo
- real background spawn on `gpt-5.3-codex-spark`
- watcher polling `.meridian/spawns.jsonl` for `status=finalizing`, then `SIGKILL` runner once `heartbeat` exists

Invocation:

```bash
uv run meridian --json spawn --background -m gpt-5.3-codex-spark -a reviewer \
  -p 'Reply with exactly ok, then create the required Meridian report.'
```

Watcher result:

```text
finalize landed before kill; timing gap not caught
```

Observed state transitions from `/tmp/meridian-edge-s1.Rb43vA/.meridian/spawns.jsonl`:

```json
{"event":"exited","exit_code":0,"exited_at":"2026-04-14T18:59:23Z","id":"p1","v":1}
{"event":"update","id":"p1","status":"finalizing","v":1}
{"duration_secs":15.935744105954655,"event":"finalize","exit_code":0,"finished_at":"2026-04-14T18:59:23Z","id":"p1","origin":"runner","status":"succeeded","v":1}
```

Observed result:

- real run completed `running -> finalizing -> succeeded`
- watcher never landed `SIGKILL` between the `finalizing` update and runner finalize
- window is very small in practice

Pass/fail:

- fail to reproduce requested gap
- not a bug signal by itself
- keep as timing-gap evidence

## Scenario 2

### 2. Authority rule: reconciler stamp then runner finalize

Outcome: `verified`
Classification: working-as-designed

Setup:

- seeded repo `/tmp/meridian-edge-s2.fsJS6I`
- synthetic `running` row with dead `runner_pid`
- `mark_finalizing()`
- stale `heartbeat`
- `spawn show` to trigger reconciler
- direct authoritative `finalize_spawn(... origin="runner")`

Invocation:

```bash
uv run meridian spawn show p1
uv run python - <<'PY'
from pathlib import Path
from meridian.lib.state.spawn_store import finalize_spawn
finalize_spawn(Path("$MERIDIAN_STATE_ROOT"), "p1", status="succeeded", exit_code=0, origin="runner")
PY
uv run meridian spawn show p1
```

Observed state transitions:

```json
{"error":"orphan_finalization","event":"finalize","exit_code":1,"finished_at":"2026-04-14T18:59:53Z","id":"p1","origin":"reconciler","status":"failed","v":1}
{"event":"finalize","exit_code":0,"finished_at":"2026-04-14T18:59:53Z","id":"p1","origin":"runner","status":"succeeded","v":1}
```

Observed result before authoritative finalize:

```text
Spawn: p1
Status: failed (exit 1)
Failure: orphan_finalization (harness likely completed; report.md may still contain useful content)
```

Observed result after authoritative finalize:

```text
Spawn: p1
Status: succeeded (exit 0)
```

Pass/fail:

- pass
- reconciler-origin terminal did not permanently poison the row
- runner-origin terminal overwrote status / exit code / error as intended

## Scenario 3

### 3. Double `finalize_spawn` idempotency

Outcome: `verified`
Classification: working-as-designed

Setup:

- seeded repo with one running row
- first authoritative finalize: `failed`, `exit_code=7`, `error=first_failure`, `duration_secs=1.0`
- second authoritative finalize: `succeeded`, `exit_code=0`, `duration_secs=9.0`

Invocation:

```bash
uv run meridian spawn show p1
uv run meridian --json spawn stats
```

Observed finalize events:

```json
{"duration_secs":1.0,"error":"first_failure","event":"finalize","exit_code":7,"finished_at":"2026-04-14T19:00:02Z","id":"p1","origin":"runner","status":"failed","v":1}
{"duration_secs":9.0,"event":"finalize","exit_code":0,"finished_at":"2026-04-14T19:00:02Z","id":"p1","origin":"runner","status":"succeeded","v":1}
```

Observed result:

```text
Spawn: p1
Status: failed (exit 7)
Duration: 9.0s
Failure: first_failure
```

Observed behavior:

- first authoritative terminal tuple won
- later authoritative finalize did not flip `failed -> succeeded`
- metadata still merged from the later finalize (`Duration: 9.0s`)

Pass/fail:

- pass

## Scenario 4

### 4. PID reuse guard

Outcome: partial
Classification: timing-gap for real PID reuse; guard branch works

Real same-PID reuse was not forced on demand.

Two probes:

1. direct function branch check

```text
pid=3148703
create_time=1776193215.16
guard_same_start=True
guard_old_start=False
guard_recent_start=True
```

2. user-visible consequence with a live process and deliberately stale `started_at`

Invocation:

```bash
sleep 60 &
uv run meridian spawn show p1
```

Observed result:

```text
ps before show:
UID          PID    PPID  C STIME TTY          TIME CMD
jimyao   3152437 3152434  0 14:02 ?        00:00:00 sleep 60

spawn show:
Spawn: p1
Status: failed (exit 1)
Failure: orphan_run
```

Observed finalize event:

```json
{"error":"orphan_run","event":"finalize","exit_code":1,"finished_at":"2026-04-14T19:02:02Z","id":"p1","origin":"reconciler","status":"failed","v":1}
```

Interpretation:

- I did not reproduce real kernel PID reuse
- I did verify the guarded branch that would reject a reused PID by create-time mismatch
- exploratory only; no direct Round 2 EARS leaf covers this exact liveness subcase

## Scenario 5

### 5. `--status finalizing` filter

Outcome: `verified`
Classification: working-as-designed

Setup:

- seeded `finalizing` row with recent `heartbeat`

Invocation:

```bash
uv run meridian spawn list --status finalizing --limit 20
uv run meridian --json spawn list --status finalizing --limit 20
uv run meridian spawn list --status running --limit 20
```

Observed result:

```text
spawn  status      model    duration
p1     finalizing  gpt-5.4  -
```

```json
{"spawns": [{"cost_usd": null, "duration_secs": null, "model": "gpt-5.4", "spawn_id": "p1", "status": "finalizing"}], "truncated": false}
```

Running parity check:

```text
(no spawns)
```

Empty-when-none check in fresh repo:

```text
(no spawns)
```

Pass/fail:

- pass

## Scenario 6

### 6. `spawn show` on a `finalizing` spawn

Outcome: `verified`
Classification: working-as-designed

Setup:

- seeded `finalizing` row with recent `heartbeat`

Invocation:

```bash
uv run meridian spawn show p1
```

Observed result:

```text
Spawn: p1
Status: finalizing (cleanup in progress)
Model: gpt-5.4 (codex)
```

Pass/fail:

- pass
- detail view does not regress to `running`
- detail view does not invent the old `awaiting finalization` heuristic

## Scenario 7

### 7. Backfill self-repair

Outcome: `verified`
Classification: working-as-designed

IDs examined:

- `p1711`
- `p1712`
- `p1731`
- `p1732`

Raw legacy finalize pairs still present:

```json
{"error":"orphan_run","event":"finalize","exit_code":1,"finished_at":"...","id":"p1711","status":"failed","v":1}
{"duration_secs":1131.2635273199994,"event":"finalize","exit_code":0,"finished_at":"...","id":"p1711","status":"succeeded","v":1}
```

Representative projected result after `uv run meridian spawn show <id>`:

```text
Spawn: p1711
Status: succeeded (exit 0)
...
Spawn: p1712
Status: succeeded (exit 0)
...
Spawn: p1731
Status: succeeded (exit 0)
...
Spawn: p1732
Status: succeeded (exit 0)
```

No migration rewrite check:

```text
before=dd99bcf66627f6c92be11061384d69b9364c7ee309d1427f988610516f71f45c
after=dd99bcf66627f6c92be11061384d69b9364c7ee309d1427f988610516f71f45c
match=yes
```

Pass/fail:

- pass
- reads self-repair projection output
- read path did not rewrite `.meridian/spawns.jsonl`

## Scenario 8

### 8. Depth-gated reconciler

Outcome: `verified`
Classification: working-as-designed

Setup:

- seeded stale `running` row that would normally reconcile to `orphan_run`

Invocation:

```bash
MERIDIAN_DEPTH=1 uv run meridian spawn show p1
uv run meridian spawn show p1
```

Observed result with depth gate:

```text
Spawn: p1
Status: running
Model: gpt-5.4 (codex)
```

Observed finalize count after depth-gated read:

```text
0
```

Observed result without depth gate:

```text
Spawn: p1
Status: failed (exit 1)
Failure: orphan_run
```

Observed reconciler finalize after normal read:

```json
{"error":"orphan_run","event":"finalize","exit_code":1,"finished_at":"2026-04-14T19:01:05Z","id":"p1","origin":"reconciler","status":"failed","v":1}
```

Pass/fail:

- pass

## Scenario 9

### 9. Stats schema coverage

Outcome: `verified`
Classification: working-as-designed

Setup:

- one row each in `succeeded`, `failed`, `cancelled`, `running`, `finalizing`
- recent `heartbeat` for active rows so stats read does not reconcile them away

Invocation:

```bash
uv run meridian spawn stats
uv run meridian --json spawn stats
```

Observed text result:

```text
total_runs: 5
succeeded: 1 (20.0%)
failed: 1 (20.0%)
cancelled: 1 (20.0%)
running: 1
finalizing: 1
```

Observed JSON result:

```json
{"cancelled": 1, "children": [], "failed": 1, "finalizing": 1, "models": {"gpt-5.4": {"cancelled": 1, "cost_usd": 0.0, "failed": 1, "finalizing": 1, "running": 1, "succeeded": 1, "total": 5}}, "running": 1, "succeeded": 1, "total_cost_usd": 0.0, "total_duration_secs": 0.0, "total_runs": 5}
```

Invariant check:

```text
{'total_runs': 5, 'summed': 5, 'holds': True}
```

Pass/fail:

- pass

## Scenario 10

### 10. CLI post-launch / `spawn wait` returning `finalizing`

Outcome: not reproduced
Classification: working-as-designed / premise did not occur

Setup:

- seeded `finalizing` row with recent `heartbeat`

Invocation:

```bash
uv run meridian spawn wait p1 --timeout 0.001
```

Observed result:

```text
exit=124
error: Timed out waiting for spawn(s) 'p1'
```

Interpretation:

- `spawn wait` treated `finalizing` as active and did not return a `finalizing` detail row
- I did not observe a real runtime where `spawn wait` returned `finalizing`
- no evidence here of a bad zero/non-zero exit mapping on that path

## Surprises

- The live `finalizing -> kill` window is narrower than expected. I could catch the `finalizing` event in `spawns.jsonl`, but not kill the runner before terminal finalize landed.
- Backfill self-repair is projection-only in the exercised cases. The on-disk event log checksum did not change after reading legacy poisoned rows.
- `spawn wait` timing out on a seeded `finalizing` row makes the scenario-10 premise look unlikely by design, not just unlikely in practice.

## Bug Calls

- No new real bug found in the exercised surfaces.
- One blocked runtime probe remains: scenario 1 needs either a slower injected finalizing window or a more intrusive kill hook if the team wants a deterministic reproduction.
