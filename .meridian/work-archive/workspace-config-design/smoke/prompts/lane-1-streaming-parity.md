# Smoke Lane 1: Streaming Adapter Parity

You are 1 of 5 parallel smoke lanes validating the **R06 launch-refactor skeleton** (8 commits, `3f8ad4c..45d18d7`) before meridian-cli 0.0.30 ships. Unit tests pass; this lane exercises real end-to-end CLI paths that unit tests cannot catch.

## What changed that makes this lane matter

The R06 skeleton centralized launch composition on a new factory `build_launch_context(...)` and **halved the streaming runner** (`bf4cf6c` removed −461 lines of duplicate path). `cli/streaming_serve.py` was reshaped. This lane verifies the subprocess vs streaming-transport launch-spec projection still produces equivalent behavior — the exact seam that was rewired.

## Your scope

1. **Run `tests/smoke/streaming-adapter-parity.md` end to end.** Work through every scenario in that file. Follow the file's guidance on expected output.
2. **Fix A spot-check** — verify codex no longer truncates large prompts:
   - Compose a prompt that is ~60 KiB of plain text (well above the old 50 KiB ceiling)
   - Run: `uv run meridian spawn -a coder --harness codex --dry-run -p "$(the_60kb_prompt)"`
   - Expect: dry-run succeeds, no `warning/promptTruncated` event, full prompt echoed back
   - Compose a prompt > 10 MiB (just test `validate_prompt_size()` rejects it — dry-run is fine)
   - Expect: `PromptTooLargeError` with clear message naming the bytes + harness

## Ground rules

- **Always use `uv run meridian`** for CLI invocations under test. The installed `meridian` binary is v0.0.29 which does NOT have Fix A; `uv run meridian` uses local source which does.
- Do not reinstall the global binary. Do not touch files outside your report path.
- If claude / codex / opencode binaries are missing, report `harness-unavailable: X` for that scenario and continue. Not a regression.
- Foreground is the new default for `meridian spawn` (per `cli/main.py` diff) — use `--background` explicitly only if a scenario needs the spawn to return immediately.

## Report

Write at `.meridian/work/workspace-config-design/smoke/lane-1-streaming-parity.md` with this shape:

```
## Verdict
<clean | regressions-found | inconclusive>

## Harness coverage
- claude: <exercised | unavailable>
- codex:  <exercised | unavailable>
- opencode: <exercised | unavailable>

## Scenarios passed
- <short desc, one per line>

## Scenarios failed
For each:
- **Scenario:** <which step>
- **Command:** <exact>
- **Actual output:** <exact, trimmed if huge>
- **Expected behavior:** <what should have happened>

## Surprises
<anything unexpected that isn't a regression per se — deprecation warnings, perf changes, etc.>
```

## Final report message

Your final assistant message must be the terminal report above. End with the report path and verdict.
