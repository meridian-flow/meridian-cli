# Smoke Lane 3: Dry-Run + Harness Bypass Dispatch

You are 1 of 5 parallel smoke lanes validating the **R06 launch-refactor skeleton** (8 commits, `3f8ad4c..45d18d7`) before meridian-cli 0.0.30 ships. Unit tests pass; this lane exercises real CLI paths that unit tests cannot catch.

## What changed that makes this lane matter

`c042478` refactored bypass dispatch and added `scripts/check-launch-invariants.sh`. Two **post-ship bugfixes** followed:

- `adea3ff` — scoped `MERIDIAN_HARNESS_COMMAND` bypass to primary launch only
- `45d18d7` — fixed primary dry-run preview to honor command bypass

That's a bugfix tail in the same area, which means more bugs may lurk here. This lane hunts for them.

## Your scope

1. **Run `tests/smoke/spawn/dry-run.md`** — covers prompt assembly, arg handling, template vars.
2. **Bespoke bypass scoping scenarios:**
   - Set `MERIDIAN_HARNESS_COMMAND=/bin/echo` in env
   - `uv run meridian spawn --dry-run -a coder -p "test"` — primary dry-run preview should show `/bin/echo` as the resolved harness command
   - `uv run meridian spawn --dry-run -a coder -p "test" --background` — same, background dry-run should also honor bypass
   - Now start an app-server: `uv run meridian app ...` (or streaming-serve if that's the current name) and spawn through it — the `MERIDIAN_HARNESS_COMMAND` bypass should NOT scope to worker/app-streamed spawns (that's the `adea3ff` scoping fix)
   - If you can't reliably exercise the worker/app path, document what you tried and skip
3. **Harness-command override flag** (if surfaced via CLI flag separate from env var): exercise that path too, same primary-vs-worker expectation.
4. **Bypass + dry-run interaction** (`45d18d7` focus):
   - Dry-run preview must accurately render the bypass-substituted command as what will be invoked
   - `meridian spawn show` on a bypass-substituted real spawn should reflect the bypassed command

## Ground rules

- **Always use `uv run meridian`** for CLI invocations under test. The installed `meridian` binary is v0.0.29 which does NOT have Fix A (codex prompt truncation); `uv run meridian` uses local source which does.
- Do not reinstall the global binary. Do not touch files outside your report path.
- Clean up env overrides between scenarios (`unset MERIDIAN_HARNESS_COMMAND`).
- If a harness binary is missing, report `harness-unavailable: X` for that scenario and continue.

## What to look for

- Bypass command actually substitutes in the invocation path the spawn uses (not silently dropped)
- Bypass does NOT leak into worker/app-streamed paths (primary-scope invariant)
- Dry-run preview output matches what would actually run
- No "command substituted but the real spawn ignored it" mismatch between dry-run and real-run

## Report

Write at `.meridian/work/workspace-config-design/smoke/lane-3-dry-run-bypass.md` with this shape:

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
- **Command / env:** <exact>
- **Actual output:** <exact>
- **Expected behavior:** <what should have happened>

## Bypass scoping matrix
<table showing primary/worker/app rows × with-bypass/without-bypass columns, your observed behavior per cell>

## Surprises
<anything unexpected>
```

## Final report message

Your final assistant message must be the terminal report above. End with the report path and verdict.
