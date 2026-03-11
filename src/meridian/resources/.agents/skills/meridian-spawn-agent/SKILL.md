---
name: meridian-spawn-agent
description: Multi-agent coordination via the meridian CLI — spawning subagents, waiting for results, checking status, and inspecting outputs. Use this skill whenever you need to delegate work to another agent, run tasks in parallel, check on spawn progress, or coordinate multiple agents. Also use when working with `meridian spawn`, `meridian work`, `meridian models`, shared filesystems, or any multi-agent workflow.
---

# meridian-spawn-agent

You have the `meridian` CLI for multi-agent coordination. Use it to spawn subagents, track progress, and inspect results.
In agent mode, all CLI output is JSON.

## Core Loop: Spawn → Wait → Show

```bash
meridian spawn -a agent -p "task description"
# → {"spawn_id": "p107", "status": "running"}

meridian spawn wait p107
# → {"spawn_id": "p107", "status": "succeeded", "report": "..."}

meridian spawn show p107
# → Full details including report, tokens, cost
```

**Capturing spawn IDs:** Agent harnesses often sandbox shell execution, so command substitution like `ID=$(meridian spawn ...)` may silently fail. Always read the `spawn_id` from the JSON output and pass it literally to `spawn wait` or `spawn show`.

## Spawning

Use `-a` to spawn with an agent profile (encodes model, system prompt, permissions) or `-m` to target a model directly. Both are first-class:

```bash
# Agent profile — uses the profile's model, prompt, and permissions
meridian spawn -a reviewer -p "Review this change"

# Direct model — when you want a specific model without a profile
meridian spawn -m MODEL -p "Implement the fix"

# Override a profile's model (e.g. budget constraints, fan-out)
meridian spawn -a reviewer -m sonnet -p "Quick review"

# With reference files (repeat -f)
meridian spawn -a agent -p "Implement fix" \
  -f plans/step.md \
  -f src/module.py
```

Run `meridian models list` to see available models and aliases. Model and agent preferences belong in your project's agent profiles, `meridian config`, or project docs (CLAUDE.md, AGENTS.md) — not hardcoded into spawn commands.

To create your own agent profiles, see [`resources/creating-agents.md`](resources/creating-agents.md).

## Work Items

Work items group spawns by purpose and give project-level visibility. Use `--work` and `--desc` to connect spawns to an effort:

```bash
# Set active work item for your session
meridian work start "auth refactor"

# Spawns automatically inherit the active work item
meridian spawn -a agent --desc "Implement step 2" -p "..."
# → spawn gets work_id: "auth-refactor"

# Or attach explicitly (useful for automation)
meridian spawn -a reviewer --work auth-refactor --desc "Review step 1" -p "..."
```

### Dashboard

`meridian work` shows what's happening, grouped by effort:

```bash
meridian work                    # dashboard — what's in flight
meridian work list               # list all work items
meridian work list --active      # hide done items
meridian work show auth-refactor # drill into one work item
```

Dashboard output groups spawns by work item:

```
ACTIVE
  auth-refactor          implementing step 2
    p5  model-a  running   Implement step 2
    p6  model-b  running   Review step 1

  (no work)
    p12 model-a  running   Fix off-by-one
```

### Managing Work Items

```bash
meridian work start "auth refactor"              # create + set active
meridian work switch auth-refactor               # change active for this session
meridian work clear                              # unset active
meridian work update auth-refactor --status "step 2"
meridian work done auth-refactor                 # mark complete
```

Work items are directories under `.meridian/work/<slug>/` — they can hold design docs, plans, diagrams. Spawns snapshot `work_id` at creation time, so changing your active work item later doesn't move old spawns.

## Parallel Spawns

Launch independent spawns in the background, then wait for all:

```bash
meridian spawn -a agent -p "Step A" --desc "Step A"
meridian spawn -a agent -p "Step B" --desc "Step B"

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

## Shared Filesystem

Spawns can exchange data through `$MERIDIAN_FS_DIR`:

```bash
echo "result" > "$MERIDIAN_FS_DIR/step-a-output.txt"
```

Meridian provides the directory — agents organize it however they want.

## Committing Spawn Changes

After a spawn finishes, use `spawn files` to get the list of touched files and pipe it to git:

```bash
# Stage all files the spawn touched
meridian spawn files p107 | xargs git add

# Null-delimited for paths with spaces
meridian spawn files p107 -0 | xargs -0 git add

# Review what changed before staging
meridian spawn files p107
```

## Beyond the Basics

For continue/fork, cancel, stats, permission tiers, template vars, and dry-run, see [`resources/advanced-commands.md`](resources/advanced-commands.md).
For troubleshooting strange behavior, see [`resources/debugging.md`](resources/debugging.md).
For writing your own agent profiles, see [`resources/creating-agents.md`](resources/creating-agents.md).
For project defaults (model, agent, permissions, timeouts), see [`resources/configuration.md`](resources/configuration.md).
