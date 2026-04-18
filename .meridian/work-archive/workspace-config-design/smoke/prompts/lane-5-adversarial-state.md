# Smoke Lane 5: Adversarial + State Integrity

You are 1 of 5 parallel smoke lanes validating the **R06 launch-refactor skeleton** (8 commits, `3f8ad4c..45d18d7`) before meridian-cli 0.0.30 ships. Unit tests pass; this lane is the creative bug-hunt + state-hygiene check.

## What changed that makes this lane matter

The R06 skeleton touched 34 files including state-adjacent code (`ops/spawn/execute.py`, `lib/app/server.py`, `launch/streaming_runner.py`). Adversarial smoke exercises odd inputs, race conditions, and state tampering — areas that unit tests rarely cover. State-integrity smoke verifies `.meridian/` stays coherent after everything runs.

## Your scope

1. **Run `tests/smoke/adversarial.md`** — go beyond the bullet list in that file; use your creativity. Try unusual prompts, weird flag combinations, malformed input files, interrupted flows, concurrent `meridian spawn` fires, env-var conflicts.
2. **Run `tests/smoke/state-integrity.md`** after your adversarial run — verify `.meridian/spawns.jsonl`, `.meridian/sessions.jsonl`, per-spawn dirs, and lock files all stayed coherent.

## Ideas for adversarial scenarios (go further than these)

- Concurrent spawns competing for the same work item
- Spawn while another spawn is writing state (race on `spawns.jsonl`)
- Kill -9 a running spawn, then inspect reconciliation (`meridian doctor`)
- Interrupt a streaming spawn mid-turn with `meridian spawn cancel`
- Spawn with prompts containing shell-metacharacter edge cases (backticks, `$`, newlines, null bytes)
- Spawn with `-f` pointing at a file that does not exist / is a directory / is a broken symlink
- `MERIDIAN_HARNESS_COMMAND` pointing at something that exits non-zero / doesn't exist / is `/dev/null`
- `meridian spawn cancel` on a spawn that already succeeded / was already cancelled / never existed
- Deeply nested spawn chain (spawn inside spawn inside spawn)

## Ground rules

- **Always use `uv run meridian`** for CLI invocations under test. The installed `meridian` binary is v0.0.29 which does NOT have Fix A (codex prompt truncation); `uv run meridian` uses local source which does.
- Do not reinstall the global binary. Do not touch files outside your report path.
- Do not delete or modify any `.meridian/` files manually — the whole point is to catch meridian's own behavior, not to force bad state.
- If a scenario would require running `git revert` / `git reset --hard` / `git clean` — don't. You're disallowed from those anyway.
- If a harness binary is missing, report `harness-unavailable: X` and continue.

## What to look for

- Tracebacks visible to the user (bad — should be a clean error)
- Malformed JSONL in `.meridian/spawns.jsonl` or `sessions.jsonl` after exercises
- Orphaned lock files
- Stale heartbeat / finalize state that `meridian doctor` can't reconcile
- Spawns stuck in `finalizing` indefinitely
- Silent failures (spawn reports success but did nothing)

## Report

Write at `.meridian/work/workspace-config-design/smoke/lane-5-adversarial-state.md` with this shape:

```
## Verdict
<clean | regressions-found | inconclusive>

## Harness coverage
- claude: <exercised | unavailable>
- codex:  <exercised | unavailable>
- opencode: <exercised | unavailable>

## Scenarios passed
<one per line, grouped by category>

## Scenarios failed / regressions found
For each:
- **Scenario:** <which step>
- **Command:** <exact>
- **Actual output:** <exact>
- **Expected behavior:** <what should have happened>
- **Severity:** <crash / data-loss / silent-wrong / cosmetic>

## State integrity findings
<results of state-integrity checks, including any tampering detected, orphaned files, stale locks>

## Creative scenarios you invented
<list whatever you probed beyond the adversarial.md bullet list — this is where the lane's value is>

## Surprises
<anything unexpected>
```

## Final report message

Your final assistant message must be the terminal report above. End with the report path and verdict.
