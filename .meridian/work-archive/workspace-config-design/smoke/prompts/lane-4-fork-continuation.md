# Smoke Lane 4: Fork + Continuation

You are 1 of 5 parallel smoke lanes validating the **R06 launch-refactor skeleton** (8 commits, `3f8ad4c..45d18d7`) before meridian-cli 0.0.30 ships. Unit tests pass; this lane exercises real CLI paths that unit tests cannot catch.

## What changed that makes this lane matter

`src/meridian/lib/launch/fork.py` is **new** — introduced by the R06 skeleton to carry fork-transaction logic that used to live inline in various drivers. Fork/continuation is fragile by nature (session-continuation fields, continuation resolution, fork-from-ref semantics, row-before-fork ordering), and any regression here breaks a user flow nobody will hit in a pyright check.

## Your scope

1. **Run `tests/smoke/fork.md` end to end.** This is the biggest smoke file (580 lines). Work through each scenario methodically.
2. **Cross-harness fork matrix** where applicable:
   - `--continue-fork` on a prior spawn
   - `--fork-from <ref>` from a session ID
   - Fork a spawn that itself was already a fork (chain)
   - Fork across harness types (if the scenario supports it)

## Ground rules

- **Always use `uv run meridian`** for CLI invocations under test. The installed `meridian` binary is v0.0.29 which does NOT have Fix A (codex prompt truncation); `uv run meridian` uses local source which does.
- Do not reinstall the global binary. Do not touch files outside your report path.
- If a harness binary is missing, report `harness-unavailable: X` for that scenario and continue.
- Fork scenarios exercise real child spawns that spend real API credits — don't loop unnecessarily, but do exercise each distinct code path at least once.

## What to look for

- Fork command produces a working child spawn (not orphaned, not duplicated)
- Continuation context (prior messages, session state) is correctly threaded into the forked spawn's initial state
- Session IDs are correctly resolved from the parent / `--from` reference
- Spawn store records the fork relationship correctly (visible via `meridian spawn show` / `spawn children`)
- Row-ordering invariant: the fork's spawn row must be created before the fork transaction opens (D7/I-10 concern in R06 design)

## Report

Write at `.meridian/work/workspace-config-design/smoke/lane-4-fork-continuation.md` with this shape:

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

## Fork coverage matrix
<table: fork-type × harness, pass/fail/unavailable per cell>

## Surprises
<anything unexpected>
```

## Final report message

Your final assistant message must be the terminal report above. End with the report path and verdict.
