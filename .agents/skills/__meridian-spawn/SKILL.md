---
name: __meridian-spawn
description: >
  Multi-agent coordination via the meridian CLI. Use this skill whenever you
  need to delegate work to another agent, run tasks in parallel, check on
  spawn progress, coordinate multiple agents, or inspect spawn outputs. Also
  use when you want to route work to a specific model or provider.
---

# __meridian-spawn

## Core Loop

All CLI output is JSON in agent mode — parse `spawn_id` and `status` programmatically from responses.

Spawns run in the **foreground** by default — the command blocks until the spawn completes, then returns the result.

```bash
meridian spawn -a agent -p "task description"
# → blocks until done, returns terminal status with spawn_id

meridian spawn show p107
# → full report + metadata (re-inspect a past spawn)
```

## Spawning

Two ways to spawn, depending on whether you want a reusable configuration or a one-off:

**`-a` (agent profile)** — use when a profile exists for the role. The profile encodes model, system prompt, skills, and permissions, so you don't repeat yourself across spawns:

```bash
meridian spawn -a reviewer -p "Review this change"
```

**`-m` (direct model)** — use for one-off tasks where no profile fits, or when you want a specific model without the rest of a profile's configuration:

```bash
meridian spawn -m MODEL -p "Implement the fix"
```

You can combine both to override a profile's default model — useful for budget constraints or when fanning out the same task across different models for diverse perspectives:

```bash
meridian spawn -a reviewer -m sonnet -p "Quick review"
```

Pass reference files with `-f` so the spawned agent starts with the context it needs instead of exploring from scratch:

```bash
meridian spawn -a agent -p "Implement fix" \
  -f plans/step.md \
  -f src/module.py
```

Run `meridian models list` to see available models and aliases. Run `mars list` to see available agent profiles and skills — useful when your harness doesn't show agents natively. Model and agent preferences belong in your project's agent profiles, `meridian config`, or project docs (CLAUDE.md, AGENTS.md) — hardcoding them into spawn commands makes them invisible to `meridian config show`, impossible to change project-wide, and silently divergent from profile defaults.

To create your own agent profiles, see [`resources/creating-agents.md`](resources/creating-agents.md).

## Work Items

Attach spawns to a work item so they're grouped on the dashboard and traceable later. Without a work item, spawns are orphaned IDs that are hard to find or make sense of after the fact.

```bash
# Spawns automatically inherit the active work item
meridian spawn -a agent --desc "Implement step 2" -p "..."

# Or attach explicitly (useful for automation or cross-cutting tasks)
meridian spawn -a reviewer --work auth-refactor --desc "Review step 1" -p "..."
```

Use `--desc` to give spawns a human-readable label — it shows up in `meridian work` and `spawn list`, so you're not staring at bare spawn IDs.

For work item lifecycle (creating, switching, updating, completing, and dashboard), see the `/__meridian-work-coordination` skill.

## Parallel Spawns

Use your harness's native background execution to run multiple spawns concurrently. Each spawn runs in foreground (blocking), but your harness runs them in parallel:

```bash
# Launch these concurrently using your harness's background/parallel execution
meridian spawn -a agent -p "Step A" --desc "Step A"
meridian spawn -a agent -p "Step B" --desc "Step B"
# Each blocks until its spawn completes, then returns results.
```

## Checking Status

Track spawns by their ID. For situational awareness, use the work dashboard — it shows active work items with their attached spawns:

```bash
meridian work
```

Stuck spawns auto-recover: if a spawn's process dies or goes stale, the next read (`show`) detects it and marks it failed. No manual cleanup needed — just check the status and move on.

To reattach to a spawn still running from a previous session, use `meridian spawn wait <spawn_id>`.

To see what a spawn spawned, use `spawn children`:

```bash
meridian spawn children p107   # list direct children of p107
```

`spawn show` also displays the parent ID when a spawn was created by another spawn.

## When a Spawn Fails

If a spawn returns `"status": "failed"`, read the report via `spawn show SPAWN_ID` — it usually contains the error or the agent's last output. For deeper investigation, see [`resources/debugging.md`](resources/debugging.md) for log inspection.

## Shared Filesystem

Spawns share two directories for exchanging data. This is how spawns pass artifacts to each other without relying on conversation context (which doesn't survive across spawn boundaries):

- **`$MERIDIAN_FS_DIR`** — long-lived project reference material that persists across work items
- **`$MERIDIAN_WORK_DIR`** — active work scratch, scoped to the current work item

See the `/__meridian-work-coordination` skill for when to use which.

## Committing Spawn Changes

Use `spawn files` to stage exactly what a spawn changed — this avoids accidentally staging unrelated files that happened to be modified:

```bash
meridian spawn files p107 | xargs git add
meridian spawn files p107 -0 | xargs -0 git add   # paths with spaces
```

## Template Variables

Use `{{KEY}}` placeholders in prompts, replaced at launch time with `--prompt-var`. This keeps variable content visible in prompt logs and `--dry-run` output, where inline string interpolation would already be resolved:

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
