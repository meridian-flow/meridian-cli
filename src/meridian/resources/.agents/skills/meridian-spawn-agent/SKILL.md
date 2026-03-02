---
name: meridian-spawn-agent
description: Multi-agent coordination via the meridian CLI. Teaches how to spawn, track, and manage subagent spawns.
---

# meridian-spawn-agent

You have the `meridian` CLI for multi-agent coordination. Use it to spawn subagents, track progress, and inspect results.
In agent mode, all CLI output is JSON.

## Spawn Composition

Compose each spawn from `model + prompt + context`:
- `model`: model id or alias
- `prompt`: task instructions
- `context`: reference files, template vars, and agent profile defaults

Start minimal, then add context only when needed.

```bash
# Basic
meridian spawn -m MODEL -p "PROMPT"

# With reference files (repeat -f)
meridian spawn -m MODEL -p "Implement fix" \
  -f plans/step.md \
  -f src/module.py

# With an agent profile
meridian spawn -a reviewer -m MODEL -p "Review this change"

# With template vars (use {{KEY}} in prompt, no spaces)
meridian spawn -m MODEL \
  -p "Implement {{TASK}} with {{CONSTRAINT}}" \
  --prompt-var TASK=auth-refactor \
  --prompt-var CONSTRAINT=no-db

# Dry-run preview (no execution)
meridian spawn --dry-run -m MODEL -p "Plan the migration"
```

## Key Flags (`meridian spawn`)

| Flag | Purpose | Notes |
| --- | --- | --- |
| `--model`, `-m` | Select model id or alias | Optional if agent/defaults provide one |
| `--prompt`, `-p` | Prompt text | Primary spawn instructions |
| `--file`, `-f` | Add reference files | Repeatable |
| `--agent`, `-a` | Use an agent profile | Applies profile model/skills/sandbox defaults |
| `--prompt-var` | Template vars (`KEY=VALUE`) | Repeatable; replaces `{{KEY}}` |
| `--background` | Return immediately with spawn id | Use with `meridian spawn wait` |
| `--dry-run` | Preview composed spawn | No harness execution |
| `--timeout-secs` | Runtime timeout | Float seconds |
| `--permission` | Override permission tier | Example: `read-only`, `workspace-write` |
| `--report-path` | Relative report output path | Default `report.md` |

## Parallel Execution

Launch independent spawns in the background, then wait for all:
```bash
R1=$(meridian spawn --background -m MODEL -p "Step A")
R2=$(meridian spawn --background -m MODEL -p "Step B")
meridian spawn wait $R1 $R2
```

## Spawn Inspection

```bash
# List spawns
meridian spawn list
meridian spawn list --failed
meridian spawn list --model MODEL
meridian spawn list --status STATUS

# Inspect one spawn
meridian spawn show SPAWN_ID
meridian spawn show SPAWN_ID --report
meridian spawn show SPAWN_ID --include-files

# Wait for completion
meridian spawn wait SPAWN_ID
meridian spawn wait SPAWN_ID --report

# Continue an existing spawn
meridian spawn continue SPAWN_ID -p "Follow up instruction"
meridian spawn continue SPAWN_ID -p "Try alternate approach" --fork

# Aggregate stats
meridian spawn stats
meridian spawn stats --session ID
```

## Model Selection

Use model discovery commands before creating spawns:

```bash
meridian models list
meridian models show MODEL
```

The CLI routes each model to the correct harness automatically.
