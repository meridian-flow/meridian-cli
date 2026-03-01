---
name: run-agent
description: Agent execution engine that composes prompts, routes models, and writes run artifacts. Use when launching subagent runs.
---

# Run-Agent — Execution Engine

Single entry point for agent execution. A run is `model + agent (opt) + skills (opt) + prompt`. Routes to the correct CLI (`claude`, `codex`, `opencode`) based on the model, logs everything, and writes structured index entries.

Skills source: sibling skills (`../`). Runtime artifacts: `.orchestrate/`.

Runner scripts (relative to this skill directory):
- `scripts/run-agent.sh` — launch a subagent run
- `scripts/run-index.sh` — inspect and manage runs

## Run Composition

Compose runs dynamically by specifying model, skills, and prompt:

```bash
# Model + skills + prompt
scripts/run-agent.sh --model MODEL --skills SKILL1,SKILL2 -p "PROMPT"

# Model + prompt (no skills)
scripts/run-agent.sh --model MODEL -p "PROMPT"

# With labels and session grouping
scripts/run-agent.sh --model MODEL --skills SKILLS \
    --session SESSION_ID --label KEY=VALUE -p "PROMPT"

# With template variables
scripts/run-agent.sh --model MODEL \
    -v KEY1=path/to/file1 -v KEY2=path/to/file2 \
    -p "Task using {{KEY1}} and {{KEY2}}"

# Dry run — see composed prompt + CLI command without executing
scripts/run-agent.sh --model MODEL --skills SKILLS --dry-run -p "PROMPT"
```

## Key Flags

| Flag | Description |
|------|-------------|
| `--model MODEL` / `-m` | Model to use (auto-routes to correct CLI) |
| `--agent NAME` | Agent profile for defaults + permissions |
| `--skills a,b,c` | Skills to compose into the prompt |
| `--strict-skills` | Fail fast when any listed skill is unknown |
| `-p "prompt"` | Task prompt |
| `-f path/to/file` | Reference file appended to prompt |
| `-v KEY=VALUE` | Template variable substitution (repeatable) |
| `--session ID` | Session ID for grouping related runs |
| `--label KEY=VALUE` | Run metadata label (repeatable) |
| `-D brief\|standard\|detailed` | Report detail level (default: `standard`) |
| `--continue-run REF` | Continue a previous run's harness session |
| `--fork` | Fork the session on continuation (default where supported) |
| `--in-place` | Resume without forking (always for Codex) |
| `--dry-run` | Show composed prompt without executing |
| `-C DIR` | Working directory for subprocess |

## Runtime Config (`.orchestrate/config.toml`)

On first run in a workspace, `run-agent.sh` auto-creates `.orchestrate/config.toml` with commented examples.

Use this file to pin skills that should be auto-added on every run:

```toml
[skills]
pinned = ["orchestrate", "run-agent", "mermaid"]
```

Notes:
- Pinned skills are merged with agent-profile skills and CLI `--skills` (deduplicated by name).
- Default template is fully commented; uncomment/edit to enable.

## Output Artifacts

Each run writes to `.orchestrate/runs/agent-runs/<run-id>/`:

- `params.json` — run parameters and metadata
- `input.md` — composed prompt
- `prompt.raw.md` — composed prompt before runtime-generated output/report sections
- `output.jsonl` — raw CLI output (stream-json or JSONL)
- `stderr.log` — CLI diagnostics (also streamed to terminal)
- `report.md` — written by the subagent (or extracted as fallback)
- `files-touched.nul` — NUL-delimited file paths (canonical machine format)
- `files-touched.txt` — newline-delimited file paths (human-readable)

## Run Index

Two-row append-only index at `.orchestrate/index/runs.jsonl`:
- **Start row** (written before execution): `status: "running"` — provides crash visibility.
- **Finalize row** (written after execution): `status: "completed"|"failed"` with exit code, duration, token usage, git metadata.

A start row with no matching finalize row means the run crashed or is still in progress.

## Structured Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Agent/model error (bad output, task failure) |
| 2 | Infrastructure error (CLI not found, harness crash) |
| 3 | Timeout |
| 130 | Interrupted (SIGINT / user cancel) |
| 143 | Terminated (SIGTERM) |

## Model Routing

| Pattern | CLI |
|---------|-----|
| `claude-*`, `opus*`, `sonnet*`, `haiku*` | Claude (`claude -p`) |
| `gpt-*`, `o1*`, `o3*`, `o4*`, `codex*` | Codex (`codex exec`) |
| `opencode-*`, `provider/model` | OpenCode (`opencode run`) |

Routing is automatic from the selected model.

## Run Explorer CLI

`scripts/run-index.sh` provides index-based run inspection:

```bash
scripts/run-index.sh list                          # List recent runs
scripts/run-index.sh list --failed --json          # Failed runs as JSON
scripts/run-index.sh show @latest                  # Show last run details
scripts/run-index.sh report @latest                # Read last run's report
scripts/run-index.sh logs @latest --tools          # Tool call summary
scripts/run-index.sh files @latest                 # Files touched
scripts/run-index.sh stats                         # Aggregate statistics
scripts/run-index.sh continue @latest -p "PROMPT"  # Continue a run's session
scripts/run-index.sh retry @last-failed            # Retry a failed run
scripts/run-index.sh maintain --compact            # Archive old index entries
```

Run references: full ID, unique prefix (8+ chars), `@latest`, `@last-failed`, `@last-completed`.

## Helper Scripts

| Script | Purpose |
|--------|---------|
| `run-index.sh` | Run explorer CLI (list, show, report, logs, files, stats, continue, retry, maintain) |
| `log-inspect.sh` | Inspect run logs (summary, tools, errors, files, search) |
| `extract-files-touched.sh` | Extract file paths from run output |
| `extract-harness-session-id.sh` | Extract harness session/thread ID from output |
| `extract-report-fallback.sh` | Extract last assistant message as report fallback |
| `load-model-guidance.sh` | Load model guidance with override precedence |
