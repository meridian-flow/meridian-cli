---
name: meridian-spawn-agent
description: Multi-agent coordination via the meridian CLI. Teaches how to spawn, track, and manage subagent spawns.
---

# meridian-spawn-agent

You have the `meridian` CLI for multi-agent coordination. Use it to spawn subagents, track progress, and inspect results.
In agent mode, all CLI output is JSON.

## Setup

Before spawning, ensure you have a space:

```bash
# First spawn auto-creates a space and returns immediately by default.
# Capture/export the returned space_id for subsequent commands.
meridian spawn -m MODEL -p "first task"
# JSON output includes spawn_id and a warning with the auto-created space hint
export MERIDIAN_SPACE_ID=s1
```

## Spawn Composition

Compose each spawn from `model + prompt + context`:
- `model`: model id or alias
- `prompt`: task instructions
- `context`: reference files, template vars, and agent profile defaults

Start minimal, then add context only when needed.

```bash
# Basic (meridian spawn is shorthand for meridian spawn create)
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
| `--file`, `-f` | Add reference files | Repeatable; content included in prompt context |
| `--agent`, `-a` | Use an agent profile | Applies profile model/skills/sandbox defaults |
| `--prompt-var` | Template vars (`KEY=VALUE`) | Repeatable; replaces `{{KEY}}` in prompt |
| `--foreground` | Run spawn in foreground | Spawns run in background by default; use this to block |
| `--dry-run` | Preview composed spawn | No harness execution |
| `--permission` | Override permission tier | Example: `read-only`, `workspace-write` |
| `--space-id` | Spawn within a specific space | Also `--space` |

## Parallel Execution

Launch independent spawns in the background, then wait for all:
```bash
# Each spawn returns JSON with a spawn_id field
meridian spawn -m MODEL -p "Step A"
meridian spawn -m MODEL -p "Step B"

# Wait for specific spawns by ID
meridian spawn wait SPAWN_ID_A SPAWN_ID_B

# Or extract spawn_id from JSON output programmatically
SID=$(meridian spawn -m MODEL -p "Task" | jq -r .spawn_id)
meridian spawn wait "$SID"
```

## Shared Filesystem

Each space has a shared filesystem at `$MERIDIAN_SPACE_FS`. Use it to pass data between spawns:

```bash
# Write output for other spawns to consume
mkdir -p "$MERIDIAN_SPACE_FS"
echo "result data" > "$MERIDIAN_SPACE_FS/step-a-output.txt"

# Read another spawn's output
cat "$MERIDIAN_SPACE_FS/step-a-output.txt"
```

Agents organize this directory however they want — meridian provides the container only.

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
meridian spawn wait SPAWN_ID

# Continue an existing spawn
meridian spawn --continue SPAWN_ID -p "Follow up instruction"
meridian spawn --continue SPAWN_ID --fork -p "Try alternate approach"

# Cancel a running spawn
meridian spawn cancel SPAWN_ID

# Aggregate stats
meridian spawn stats
meridian spawn stats --session ID
```

## Debugging & Logs

Each spawn writes logs to `.meridian/.spaces/<space-id>/spawns/<spawn-id>/`. The `log_path` field in `spawn show` output points to the stderr log:

```bash
# Get the log path for a spawn
meridian spawn show SPAWN_ID
# → look for "log_path" in the JSON output

# Read the full harness stderr log directly
cat ".meridian/.spaces/$MERIDIAN_SPACE_ID/spawns/SPAWN_ID/stderr.log"

# Tail a running spawn's log
tail -f ".meridian/.spaces/$MERIDIAN_SPACE_ID/spawns/SPAWN_ID/stderr.log"
```

The stderr log contains the full harness session trace — every tool call, exec command, and reasoning step. Use it to diagnose stuck, slow, or failed spawns.
## Model Selection

Use model discovery commands before creating spawns:

```bash
meridian models list
meridian models show MODEL
```

The CLI routes each model to the correct harness automatically.
