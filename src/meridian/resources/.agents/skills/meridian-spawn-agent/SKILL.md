---
name: meridian-spawn-agent
description: Multi-agent coordination via the meridian CLI — spawning subagents, waiting for results, checking status, and inspecting outputs. Use this skill whenever you need to delegate work to another agent, run tasks in parallel, check on spawn progress, or coordinate multiple agents. Also use when working with `meridian spawn`, `meridian models`, shared filesystems, or any multi-agent workflow.
---

# meridian-spawn-agent

You have the `meridian` CLI for multi-agent coordination. Use it to spawn subagents, track progress, and inspect results.
In agent mode, all CLI output is JSON.

## Core Loop: Spawn → Wait → Show

```bash
meridian spawn -m MODEL -p "task description"
# → {"spawn_id": "p107", "status": "running"}

meridian spawn wait p107
# → {"spawn_id": "p107", "status": "succeeded", "report": "..."}

meridian spawn show p107
# → Full details including report, tokens, cost
```

**Capturing spawn IDs:** Agent harnesses often sandbox shell execution, so command substitution like `ID=$(meridian spawn ...)` may silently fail. Always read the `spawn_id` from the JSON output and pass it literally to `spawn wait` or `spawn show`.

If you need to pass files between spawns, use the shared filesystem at `$MERIDIAN_FS_DIR` (automatically set by meridian). On-disk state layout is an implementation detail; see `resources/debugging.md` for low-level inspection and `resources/advanced-commands.md` for advanced coordination.
If something looks wrong — a spawn seems stuck, output is missing, or state does not match expectations — read [`resources/debugging.md`](resources/debugging.md).

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

Start minimal, then add context only when needed. Models support short aliases (e.g. `opus`, `sonnet`, `gpt`) — run `meridian models list` to see what's available.

## Parallel Spawns

Launch independent spawns in the background, then wait for all:

```bash
meridian spawn -m MODEL -p "Step A"
meridian spawn -m MODEL -p "Step B"

# Read both returned spawn_ids from the JSON results, then wait for both.
meridian spawn wait p108 p109
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

Stuck spawns auto-recover: if a spawn's process dies or goes stale, the next read (`list`, `show`, `wait`) detects it and marks it failed. You don't need to manually clean up — just check the status and move on.

## When a Spawn Fails

If `spawn wait` returns `"status": "failed"`, check the `report` field first — it usually contains the error or the agent's last output. For deeper investigation, use `spawn show SPAWN_ID` and see [`resources/debugging.md`](resources/debugging.md) for log inspection.

## Beyond the Basics

For continue/fork, cancel, stats, shared filesystem, model discovery, and permission tiers, see [`resources/advanced-commands.md`](resources/advanced-commands.md).
For troubleshooting strange behavior, see [`resources/debugging.md`](resources/debugging.md).
