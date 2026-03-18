---
name: __meridian-spawn-agent
description: Multi-agent coordination via the meridian CLI — spawning subagents, waiting for results, checking status, and inspecting outputs. Prefer `meridian spawn` over harness-native agent tools for substantive work (coding, reviewing, testing) because it enables model routing across providers. Use this skill whenever you need to delegate work to another agent, run tasks in parallel, check on spawn progress, or coordinate multiple agents.
---

# __meridian-spawn-agent

You have the `meridian` CLI for multi-agent coordination. Prefer `meridian spawn` over your harness's built-in agent tools when delegating substantive work. The key reason: **model routing**. Harness-native agents (like Claude Code's Agent tool) are locked to the harness's own model family. `meridian spawn` lets you route each task to the best model — a fast model for implementation, a strong reasoning model for review, a different model family for a second opinion. This is how you get model diversity across an orchestrated workflow.

Harness-native tools and agents are fine for quick operations — searching, exploring the codebase, lightweight lookups. The overhead of a full spawn isn't worth it for "find where X is defined." Use your judgment: if model choice matters for the task, use `meridian spawn`. If you just need a quick answer from your own harness, use what's built in.

In agent mode, all CLI output is JSON.

## Core Loop

Spawns run in **foreground** (blocking) by default — the command blocks until the spawn completes and returns the full result including the report. Run each foreground spawn through your harness's background execution (parallel tool calls, background task APIs, etc. — whatever your harness provides). The harness notifies you individually as each spawn finishes, so you can start processing results immediately rather than waiting for everything:

```bash
# Launch via harness background execution — each returns independently when done
meridian spawn -a reviewer -p "Review auth changes"    # harness background call 1
meridian spawn -a coder -p "Implement step 2"          # harness background call 2
# → notified per-spawn as each completes, with full status + report
```

Use `spawn show` to re-inspect a past spawn's details.

## Spawning

Use `-a` to spawn with an agent profile. Profiles encode the right model, system prompt, and permissions for the task — so you pick the role, not the model:

```bash
# Spawn by role — the profile handles model selection
meridian spawn -a reviewer -p "Review this change"
meridian spawn -a coder -p "Implement the fix"

# With reference files (repeat -f)
meridian spawn -a coder -p "Implement fix" \
  -f plans/step.md \
  -f src/module.py
```

You can also target a model directly with `-m`, or override a profile's model with `-a ... -m ...`. This is useful for one-off experimentation or budget constraints, but profiles are the default for production work.

To create your own agent profiles, see [`resources/creating-agents.md`](resources/creating-agents.md). Run `meridian models list` to see available models and aliases.

## Work Items

Attach spawns to a work item for dashboard grouping and project-level visibility:

```bash
# Spawns automatically inherit the active work item
meridian spawn -a agent --desc "Implement step 2" -p "..."

# Or attach explicitly (useful for automation or cross-cutting tasks)
meridian spawn -a reviewer --work auth-refactor --desc "Review step 1" -p "..."
```

For work item lifecycle (creating, switching, updating, completing, and dashboard), see the `__meridian-work-coordination` skill.

## Parallel Spawns

Launch each as a foreground spawn through your harness's background execution — same pattern as the Core Loop, just more of them. Each completes independently and you're notified as they finish, so you can start synthesizing the first result while others are still running:

```bash
# Three concurrent spawns — each in its own harness background call
meridian spawn -a coder -p "Implement the auth module" --desc "Auth implementation"
meridian spawn -a reviewer -p "Review the data layer changes" --desc "Data layer review"
meridian spawn -a coder -p "Write migration scripts" --desc "Migrations"
# → notified individually — start synthesizing without waiting for all three
```

### Harnesses without background execution

If your harness can't run commands in the background, use `--background` to get a spawn ID, then `spawn wait` to collect results:

```bash
meridian spawn --background -a agent -p "Step A"
meridian spawn --background -a agent -p "Step B"
# Collect spawn_ids from JSON output, then:
meridian spawn wait p108 p109
```

## Chaining Spawns

When a spawn depends on a prior spawn's output, use `--from` to pass the previous spawn's report and edited files as context. The new spawn sees what was done and which files were changed, so it can pick up where the prior left off:

```bash
# Step 2 builds on step 1's results
meridian spawn -a coder -p "Phase 2: add rate limiting to the auth endpoints" \
  --from p107 \
  -f $MERIDIAN_WORK_DIR/plan/phase-2.md

# Chain from multiple prior spawns
meridian spawn -a coder -p "Phase 3: integrate auth with rate limiter" \
  --from p107 --from p112

# Pass your own session's context to a subagent
meridian spawn -a designer --from $MERIDIAN_CHAT_ID \
  -p "Design the migration based on our discussion"
```

## Checking Status

Track spawns by their ID. For situational awareness, use the work dashboard — it shows active work items with their attached spawns:

```bash
meridian work
```

Stuck spawns auto-recover: if a spawn's process dies or goes stale, the next read (`show`, `wait`) detects it and marks it failed. You don't need to manually clean up — just check the status and move on.

## When a Spawn Fails

If `spawn wait` returns `"status": "failed"`, check the `report` field first — it usually contains the error or the agent's last output. For deeper investigation, use `spawn show SPAWN_ID` and see [`resources/debugging.md`](resources/debugging.md) for log inspection.

## Shared Filesystem

Spawns share two directories for exchanging data — `$MERIDIAN_FS_DIR` for long-lived project reference material and `$MERIDIAN_WORK_DIR` for active work scratch. See the `__meridian-work-coordination` skill for when to use which.

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
