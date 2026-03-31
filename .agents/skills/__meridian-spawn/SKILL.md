---
name: __meridian-spawn
description: Multi-agent coordination via the meridian CLI — spawning subagents, waiting for results, checking status, and inspecting outputs. Prefer `meridian spawn` over harness-native agent tools for substantive work (coding, reviewing, testing) because it enables model routing across providers. Use this skill whenever you need to delegate work to another agent, run tasks in parallel, check on spawn progress, or coordinate multiple agents.
---

# __meridian-spawn

You have the `meridian` CLI for multi-agent coordination.

`meridian spawn` is your delegation tool. It routes each task to the best model for the job across providers — a fast model for implementation, a strong reasoning model for review, a different model family for a second opinion. This cross-provider routing is what makes meridian agent profiles effective.

Use `meridian spawn` for all delegated work: coding, reviewing, testing, research, investigation. Use harness-native tools (Read, Grep, Glob, Bash) and lightweight agent types (Explore, Plan) for quick lookups you handle yourself.

In agent mode, all CLI output is JSON.

## Core Loop

Spawns run in **foreground** (blocking) by default — the command blocks until the spawn completes and returns status only (`spawn_id`, `status`, `duration`). Use your harness's background execution to avoid blocking yourself:

```bash
# Run via your harness's background feature (e.g., Bash run_in_background, parallel tool calls)
meridian spawn -a agent -p "task description"
# → harness notifies you when done, result includes spawn_id + status
```

Your harness handles the notification — no need to poll or wait. Use `spawn show` to read report content.

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

Attach spawns to a work item for dashboard grouping and project-level visibility:

```bash
# Spawns automatically inherit the active work item
meridian spawn -a agent --desc "Implement step 2" -p "..."

# Or attach explicitly (useful for automation or cross-cutting tasks)
meridian spawn -a reviewer --work auth-refactor --desc "Review step 1" -p "..."
```

For work item lifecycle (creating, switching, updating, completing, and dashboard), see the `/__meridian-work-coordination` skill.

## Parallel Spawns

Spawns run in foreground (blocking) by default. To run multiple spawns concurrently, use your harness's built-in background execution:

```bash
# Launch these concurrently using your harness's background/parallel feature
# (e.g., Claude Code's parallel tool calls, or Bash run_in_background)
meridian spawn -a agent -p "Step A" --desc "Step A"
meridian spawn -a agent -p "Step B" --desc "Step B"

# Each returns when its spawn completes — no need for spawn wait.
```

## Checking Status

Track spawns by their ID. For situational awareness, use the work dashboard — it shows active work items with their attached spawns:

```bash
meridian work
```

Stuck spawns auto-recover: if a spawn's process dies or goes stale, the next read (`show`, `wait`) detects it and marks it failed. You don't need to manually clean up — just check the status and move on.

## When a Spawn Fails

If `spawn wait` returns `"status": "failed"`, read the report via `spawn show SPAWN_ID` first — it usually contains the error or the agent's last output. For deeper investigation, see [`resources/debugging.md`](resources/debugging.md) for log inspection.

## Shared Filesystem

Spawns share two directories for exchanging data — `$MERIDIAN_FS_DIR` for long-lived project reference material and `$MERIDIAN_WORK_DIR` for active work scratch. See the `/__meridian-work-coordination` skill for when to use which.

## Committing Spawn Changes

Use `spawn files` to get the files a spawn touched and pipe them to git:

```bash
meridian spawn files p107 | xargs git add
meridian spawn files p107 -0 | xargs -0 git add   # paths with spaces
```

## Template Variables

Use `{{KEY}}` placeholders in prompts, replaced at launch time with `--prompt-var`:

```bash
meridian spawn -a coder \
  -p "Implement {{TASK}} following {{CONSTRAINT}}" \
  --prompt-var TASK=auth-refactor \
  --prompt-var CONSTRAINT="no direct DB access"
```

## Beyond the Basics

For continue/fork, cancel, stats, permission tiers, reports, and dry-run, see [`resources/advanced-commands.md`](resources/advanced-commands.md).
For troubleshooting strange behavior, see [`resources/debugging.md`](resources/debugging.md).
For writing your own agent profiles, see [`resources/creating-agents.md`](resources/creating-agents.md).
For project defaults (model, agent, permissions, timeouts), see [`resources/configuration.md`](resources/configuration.md).
