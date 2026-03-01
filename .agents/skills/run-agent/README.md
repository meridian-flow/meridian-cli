# Run-Agent — Execution Engine

Single entry point for agent execution. A run is `model + skills + prompt`, optionally fronted by an agent profile for defaults and permissions. Routes to the correct CLI tool, logs each run, and writes structured index entries.

Skills source: sibling skills (`../`). Runtime artifacts: `.orchestrate/` from the repo root.

No environment variables control runtime behavior — all configuration is via explicit flags.

## Runner

```bash
RUNNER=scripts/run-agent.sh
INDEX=scripts/run-index.sh
```

## Quick Start

```bash
# Model + skills + prompt
"$RUNNER" --model gpt-5.3-codex --skills reviewing -p "Review these changes"

# Kill a hung harness run (default: 15 minutes)
"$RUNNER" --model claude-sonnet-4-6 --timeout 15 -p "Review these changes"

# With an agent profile
"$RUNNER" --agent reviewer -p "Review these changes"

# With labels and session grouping
"$RUNNER" --model gpt-5.3-codex --skills scratchpad \
    --session my-session --label ticket=PAY-123 \
    -p "Implement the feature"

# Dry run — see composed prompt without executing
"$RUNNER" --model gpt-5.3-codex --skills reviewing --dry-run -p "Review auth"

# Inspect runs
"$INDEX" list
"$INDEX" show @latest
"$INDEX" stats
```

## How It Works

1. Parse model, skills, prompt, labels, session, and context flags
2. Route model to the correct CLI (`claude`, `codex`, `opencode`)
3. List selected skills by name (harnesses load skill content natively)
4. Compose the final prompt (task prompt + reference files + skill names)
5. Write start index row (crash visibility)
6. Execute the CLI command
7. Write finalize index row with exit code, duration, git metadata, token usage
8. Log artifacts to `.orchestrate/runs/agent-runs/<run-id>/`

Notes:
- `--timeout` is in minutes (supports fractional minutes) and applies to the harness subprocess; a timed-out run exits with code `3`.
- Some harnesses can exit `0` while producing unusable output; run-agent treats empty output (Claude/OpenCode) or OpenCode error events as failures.

## Output Artifacts

Each run writes to `.orchestrate/runs/agent-runs/<run-id>/`:
- `params.json` — run parameters and metadata
- `input.md` — composed prompt
- `output.jsonl` — raw CLI output (stream-json or JSONL)
- `stderr.log` — CLI diagnostics
- `report.md` — written by the subagent (or extracted as fallback)
- `files-touched.nul` — NUL-delimited file paths (canonical format)
- `files-touched.txt` — newline-delimited file paths (human-readable)

Index: `.orchestrate/index/runs.jsonl` (two rows per run: start + finalize)

## Helper Scripts

| Script | Purpose |
|--------|---------|
| `run-index.sh` | Run explorer CLI (list, show, report, logs, files, stats, continue, retry, maintain) |
| `log-inspect.sh` | Inspect run logs without loading full output |
| `extract-files-touched.sh` | Parse touched files from a run log |
| `extract-harness-session-id.sh` | Extract harness session/thread ID from output |
| `extract-report-fallback.sh` | Extract last assistant message as report fallback |
| `load-model-guidance.sh` | Load model guidance with override precedence |

## Tests

```bash
tests/run-agent-unit.sh
```
