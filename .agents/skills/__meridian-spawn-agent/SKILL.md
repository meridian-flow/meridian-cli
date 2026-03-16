---
name: __meridian-spawn-agent
description: Multi-agent coordination via meridian CLI. Spawning subagents, monitoring status, and inspecting outputs. IMPORTANT — always use `meridian spawn` instead of harness-native agent tools (Claude Code's Agent tool, Codex subprocesses). Harness-native tools bypass meridian's tracking and agent profiles.
---

# __meridian-spawn-agent

You have the `meridian` CLI for multi-agent coordination. **Always use `meridian spawn` to delegate work — never use your harness's built-in agent or subagent tools.** Harness-native tools (like Claude Code's Agent tool) bypass meridian's tracking, agent profiles, and state management — spawns created that way are invisible to the dashboard, other agents, and future sessions. Use `meridian spawn` for everything: coding, reviewing, testing, investigating.

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

Run `meridian models list` to see available models and aliases. Use `meridian models refresh` to update the model cache from configured providers. Model and agent preferences belong in your project's agent profiles, `meridian config`, or project docs (CLAUDE.md, AGENTS.md) — not hardcoded into spawn commands.

To create your own agent profiles, see [`resources/creating-agents.md`](resources/creating-agents.md).

## Work Items

Work items group spawns by purpose. Use `--work` and `--desc` on `meridian spawn` to connect spawns to an effort:

```bash
# Spawns automatically inherit the active work item
meridian spawn -a agent --desc "Implement step 2" -p "..."
# → spawn gets work_id from the current session's active work item

# Or attach explicitly (useful for automation or cross-cutting tasks)
meridian spawn -a reviewer --work auth-refactor --desc "Review step 1" -p "..."
```

See the `__meridian-work-coordination` skill for full work item lifecycle (creating, switching, updating, completing work items, and artifact placement).

## Parallel Spawns

Use your harness's native background execution to run multiple spawns concurrently. Each spawn runs in foreground (blocking), but your harness runs them in parallel:

```bash
# Launch these concurrently using your harness's background/parallel feature
meridian spawn -a agent -p "Step A" --desc "Step A"
meridian spawn -a agent -p "Step B" --desc "Step B"

# Each returns when its spawn completes — no need for spawn wait.
```

If your harness doesn't support parallel execution, use `--background` and `spawn wait`:

```bash
meridian spawn --background -a agent -p "Step A" --desc "Step A"
meridian spawn --background -a agent -p "Step B" --desc "Step B"
# Read spawn_ids from JSON results, then wait for both
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

Use `spawn files` to get the files a spawn touched and pipe them to git:

```bash
meridian spawn files p107 | xargs git add
meridian spawn files p107 -0 | xargs -0 git add   # paths with spaces
```

## Reports

Reports are how spawn output is recorded and retrieved. Every spawn can have a report — typically written by the spawn itself, but you can also create or update one externally.

```bash
# View a spawn's report
meridian report show --spawn p107

# Search across all spawn reports by text
meridian report search "auth refactor" --limit 10

# Scope search to a single spawn
meridian report search "error" --spawn p107

# Create or update a report for a spawn
meridian report create "Summary of findings..." --spawn p107

# Pipe report content from stdin
echo "Report content" | meridian report create --spawn p107 --stdin
```

## Beyond the Basics

For continue/fork, cancel, stats, permission tiers, template vars, and dry-run, see [`resources/advanced-commands.md`](resources/advanced-commands.md).
For troubleshooting strange behavior, see [`resources/debugging.md`](resources/debugging.md).
For writing your own agent profiles, see [`resources/creating-agents.md`](resources/creating-agents.md).
For project defaults (model, agent, permissions, timeouts), see [`resources/configuration.md`](resources/configuration.md).
