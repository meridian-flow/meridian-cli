# Spawn Lifecycle Testing

Use this reference when validating `meridian spawn` beyond dry-run command construction.

## Harness Resolution

`meridian spawn` picks a harness adapter via model metadata. The flow:

1. CLI receives `--model` (or defaults from agent profile)
2. `HarnessRegistry.route()` calls `resolve_model()` which maps the model string to a `HarnessId`
3. The registry returns the matching adapter: `ClaudeAdapter`, `CodexAdapter`, `OpenCodeAdapter`, or `DirectAdapter`

Key file: `src/meridian/lib/harness/registry.py` — `HarnessRegistry.with_defaults()` registers all built-in adapters.

## Dry-Run vs Real Spawn

**Dry-run** (`--dry-run`) exercises:
- Model resolution and harness routing
- Skill materialization and prompt composition
- Command building via the adapter's `build_command()`
- Writes no state, launches no subprocess

**Real spawn** additionally:
- Launches the harness subprocess via `spawn_and_stream()`
- Captures stdout/stderr to artifact files in real time
- Writes `spawns.jsonl` entries (start + finalize)
- Extracts usage, session IDs, and reports from artifacts
- Runs guardrails on success, retries on transient failure

## Minimum Working Config for a Real Spawn

To run a real spawn you need:
- A registered adapter whose `build_command()` produces a valid shell command
- The harness binary available on `$PATH` (e.g. `claude`, `codex`, `opencode`)
- Proper env vars: `MERIDIAN_REPO_ROOT` and `MERIDIAN_STATE_ROOT` pointing to valid directories
- A `.meridian/` state root (created by `meridian config init` or on first write)

## State Files to Verify After Spawn

| File | What to check |
|------|---------------|
| `.meridian/spawns.jsonl` | Has both `started` and `finalized` events for the spawn ID |
| `.meridian/artifacts/pN/output.jsonl` | Contains harness stdout (JSONL stream events) |
| `.meridian/artifacts/pN/stderr.log` | Contains harness stderr (may be empty on success) |
| `.meridian/artifacts/pN/tokens.json` | Token usage if the harness reported it |
| `.meridian/artifacts/pN/report.md` | Agent report if the harness supports `-o` |
| `.meridian/sessions.jsonl` | Session tracking entry if session detection succeeded |

## Exit Code Mapping

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Recoverable failure (bad output, guardrail fail, empty output) |
| 2 | Infrastructure error (harness crash, budget exceeded) |
| 3 | Timeout |
| 130 | Cancelled (SIGINT/task cancellation) |

Source: `map_process_exit_code()` in `src/meridian/lib/launch/signals.py` and the retry/finalization logic in `src/meridian/lib/launch/runner.py`.

## Testing Without a Live Harness

If you don't have a working harness binary configured:

1. **Use `--dry-run`** to validate command construction and prompt composition. This covers model resolution, skill materialization, and the full `build_command()` path.
2. **Read default profiles** at `src/meridian/resources/.agents/agents/meridian-primary.md` to understand what a spawn would configure.
3. **Inspect existing artifacts** — if prior spawns exist in `.meridian/artifacts/`, you can verify the state layer without launching a new process.

For full lifecycle coverage, you need a real harness. The `tests/smoke/spawn/lifecycle.md` guide documents the expected flow.
