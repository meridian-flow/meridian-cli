# Troubleshooting

## `meridian` not found

Run `uv tool update-shell` and restart your shell. If using a virtual environment, activate it first.

## Harness not found

`meridian doctor` reports missing harnesses when the harness binary is not on `$PATH`.

Install the missing harness:
- Claude Code: [docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code)
- Codex CLI: [github.com/openai/codex](https://github.com/openai/codex)
- OpenCode: [opencode.ai](https://opencode.ai)

Then confirm with `meridian doctor`.

## Model routes to wrong harness

Harness routing is determined by model prefix patterns. Check what's resolved:

```bash
meridian models list           # see available models and their harnesses
meridian models show MODEL     # see routing for a specific model
meridian config show           # see harness defaults and overrides
```

Override harness patterns in `.meridian/models.toml`:

```toml
[harness_patterns]
codex = ["gpt-*", "o*", "codex*"]
opencode = ["gemini*", "opencode-*"]
```

## Spawn disconnected from earlier work

To resume a prior spawn:
```bash
meridian spawn --continue ID -p "continue from where you left off"
```

To start a new spawn with the prior conversation as context:
```bash
meridian spawn --from ID -p "next task"
```

To find which spawns belong to a work item:
```bash
meridian work                      # dashboard with attached spawns
meridian report search "keyword"   # search across all spawn reports
```

## Spawn shows as orphaned

Orphan state usually means the harness process died without finalizing. Run:

```bash
meridian doctor
```

This detects and reconciles orphaned state. The spawn record is updated to reflect the actual outcome. Relaunch the spawn if it did not complete.

## Spawn exited with code 143 or 137

The process was killed externally (SIGTERM/SIGKILL). Check `meridian spawn show ID` — if status is `succeeded`, the signal hit during cleanup and no retry is needed. Otherwise check for OOM or external kill, then retry.

## Config not taking effect

Config resolution precedence: CLI flag > ENV var > YAML profile > project config > user config > harness default.

Verify what's actually resolved for a field:
```bash
meridian config show
```

A CLI `-m MODEL` override must also drive harness selection — a profile-level harness default cannot win over a CLI model override.

## Spawn artifacts

Each spawn writes to `.meridian/spawns/<spawn_id>/`:

| File | Contents |
| ---- | -------- |
| `report.md` | Agent's final report |
| `output.jsonl` | Raw harness output (use `meridian spawn log`) |
| `stderr.log` | Harness stderr, warnings, errors |
| `prompt.md` | Materialized prompt sent to the harness |

If a spawn directory is missing entirely, the harness crashed before artifacts stabilized — relaunch.
