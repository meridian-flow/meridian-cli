---
name: meridian-spawn-agent
description: Multi-agent coordination via the meridian CLI. Teaches how to spawn, track, and manage subagent spawns.
---

# meridian-spawn-agent

You have the `meridian` CLI for multi-agent coordination. Use it to spawn subagents, track progress, and inspect results.
In agent mode, all CLI output is JSON.

## Core Loop: Spawn → Wait → Show

```bash
# Launch a spawn (returns immediately with spawn_id)
SID=$(meridian spawn -m MODEL -p "task description" | jq -r .spawn_id)

# Wait for completion (blocks, returns report by default)
meridian spawn wait "$SID"

# Inspect result details (includes report by default)
meridian spawn show "$SID"
```

State lives under `.meridian/` — spawns.jsonl for events, `spawns/<id>/` for artifacts, `fs/` for shared files between spawns.

## Composing Spawns

```bash
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

Start minimal, then add context only when needed. Use `meridian models list` to discover available models.

## Parallel Spawns

Launch independent spawns in the background, then wait for all:

```bash
SID_A=$(meridian spawn -m MODEL -p "Step A" | jq -r .spawn_id)
SID_B=$(meridian spawn -m MODEL -p "Step B" | jq -r .spawn_id)
meridian spawn wait "$SID_A" "$SID_B"
```

## Checking Status

Always track spawns by their ID. Use `spawn list` only for situational awareness.

```bash
# What's currently running?
meridian spawn list

# Quick overview (all active + most recent 5)
meridian spawn list --all

# If output says there are more, increase the limit
meridian spawn list --all --limit 20
```

## Beyond the Basics

For continue/fork, cancel, stats, debugging logs, shared filesystem, model discovery, and permission tiers, see [`resources/advanced-commands.md`](resources/advanced-commands.md).
