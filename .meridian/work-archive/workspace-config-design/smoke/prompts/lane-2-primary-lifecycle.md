# Smoke Lane 2: Primary Launch Lifecycle + Quick Sanity

You are 1 of 5 parallel smoke lanes validating the **R06 launch-refactor skeleton** (8 commits, `3f8ad4c..45d18d7`) before meridian-cli 0.0.30 ships. Unit tests pass; this lane exercises real CLI paths that unit tests cannot catch.

## What changed that makes this lane matter

The primary launch driver (`launch/plan.py`, `launch/process.py`) was rewired through the new `build_launch_context(...)` factory (`b19d999` +360/-134 across 8 files). Spawn creation, progression through states, report emission, and exit-code handling all flow through the rewired path. This lane catches catastrophic primary-path breakage.

## Your scope

1. **Run `tests/smoke/quick-sanity.md`** — broad CLI-surface catch-all. Any catastrophic breakage surfaces here.
2. **Run `tests/smoke/spawn/lifecycle.md`** — create / wait / show / cancel / attach-report / stats. Exercise against real harnesses (Claude, Codex, OpenCode, in that order).
3. **Verify foreground/background UX:**
   - `uv run meridian spawn -a coder -p "echo ok" --dry-run` — should block until terminal state (new default per `cli/main.py`)
   - `uv run meridian spawn -a coder -p "echo ok" --dry-run --background` — should return immediately with spawn ID
   - Check spawn show reports the correct terminal state for each

## Ground rules

- **Always use `uv run meridian`** for CLI invocations under test. The installed `meridian` binary is v0.0.29 which does NOT have Fix A (codex prompt truncation); `uv run meridian` uses local source which does.
- Do not reinstall the global binary. Do not touch files outside your report path.
- If a harness binary is missing, report `harness-unavailable: X` for that scenario and continue. Not a regression.

## What to look for

- Spawn transitions: queued → running → finalizing → terminal. `meridian spawn show` must report each phase accurately.
- Exit codes: success = 0, failure = non-zero with report populated.
- Report extraction: the spawn's final assistant message ends up in `report.md`.
- State integrity: `.meridian/spawns.jsonl` and the per-spawn dir must be well-formed JSONL, no truncation, no stale lock files.

## Report

Write at `.meridian/work/workspace-config-design/smoke/lane-2-primary-lifecycle.md` with this shape:

```
## Verdict
<clean | regressions-found | inconclusive>

## Harness coverage
- claude: <exercised | unavailable>
- codex:  <exercised | unavailable>
- opencode: <exercised | unavailable>

## Scenarios passed
<one per line>

## Scenarios failed
For each:
- **Scenario:** <which step>
- **Command:** <exact>
- **Actual output:** <exact, trimmed if huge>
- **Expected behavior:** <what should have happened>

## Foreground/background UX check
<note any surprises — the default just flipped in cli/main.py>

## Surprises
<anything unexpected that isn't a regression per se>
```

## Final report message

Your final assistant message must be the terminal report above. End with the report path and verdict.
