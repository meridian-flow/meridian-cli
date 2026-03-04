# Bundled Default Skills

**Status:** completed (2026-03-04)

## Implementation Snapshot

- Bundled skills shipped: `orchestrate`, `meridian-spawn-agent` (later renamed/expanded via `a7ccecf`).
- Bundled agent profiles (`primary.md`, `agent.md`) include default skills.
- Harness materialization copies agents/skills into harness-native dirs.
- Key commits: `b1d859d`, `77cffef`, `d434984`, `e8a5816`, `731d972`, `a7ccecf`.

## Goal

Make meridian useful out-of-the-box for any domain. A user who installs meridian and loads `meridian-run` into their agent gets multi-agent coordination without domain-specific setup. `orchestrate` adds opinionated workflow patterns on top.

## Design Principles

- **Generic by default** — no coding, writing, or domain assumptions in bundled content
- **`meridian-run` is the core** — teaches any agent the CLI; alone gives ~90% of value
- **`orchestrate` is opinionated** — structured supervisor patterns (plan → execute → review → rework), references `meridian-run` for mechanics
- **Customizable** — users add domain skills on top, or replace bundled ones

## Bundled Skills

### 1. `meridian-run` (core)

Teaches any agent how to use the meridian CLI for multi-agent coordination.

Content:
- `meridian run spawn` — launching subagents (model, skills, prompt, context files, template vars)
- `meridian run show/list/wait/continue/stats` — tracking and managing runs
- Model selection guidance (loaded from references/)
- How to compose good prompts and pass context
- Error handling (what exit codes mean, when to retry vs escalate)
- Background vs blocking runs
- Session grouping

This is a **rewrite** of the current `.claude/skills/run-agent/SKILL.md` but:
- Stripped of shell-script specifics (run-agent.sh, run-index.sh) — uses `meridian run` CLI directly
- Generic, not dev-focused
- No references to `.orchestrate/` runtime directory

### 2. `orchestrate` (opinionated workflow)

Structured supervisor pattern for complex multi-step tasks.

Content:
- **Planning**: how to break work into steps, which models for which task types, review fan-out strategy
- **Core loop**: understand → plan → execute → review → rework → commit
- **Model diversity**: use different model families for independent perspectives
- **Review cycles**: scale reviewer count to risk, use tiebreakers on disagreement, bound rework loops
- **Parallel execution**: when to fan out, how to manage dependencies
- **Escalation**: when to stop and ask the user
- References `meridian-run` skill for the actual CLI mechanics
- Includes planning methodology (no separate `plan` skill needed)

This is a **rewrite** of the current `.claude/skills/orchestrate/SKILL.md` but:
- Generic, not dev-focused (no git commit patterns, no test/lint specifics)
- Planning guidance embedded (not a separate skill reference)
- References `meridian-run` for mechanics

## Bundled Agent Profiles

Already exist, minor updates:

### `agent.md` (default for `run spawn`)
- Comment out `mcp-tools` by default (user enables what they need)
- Keep generic prompt

### `primary.md` (default for `meridian start`)
- Comment out `mcp-tools` by default
- Reference `orchestrate` + `meridian-run` as default skills
- Keep generic prompt

## Resource Resolution (already works)

Skills are already resolved from:
1. Repo-local `.agents/skills/` directories
2. Bundled `meridian.resources/.agents/skills/` (via `bundled_agents_root()`)

Same for agent profiles. **No new seeding/copy mechanism needed** — the bundled resources are used directly from the package. Users override by creating same-named skills in their repo's `.agents/skills/`.

If we later want `meridian doctor` to copy bundled resources into the repo for discoverability, that's a separate enhancement.

## File Changes

### New files
- `src/meridian/resources/.agents/skills/meridian-run/SKILL.md` — core CLI skill
- `src/meridian/resources/.agents/skills/orchestrate/SKILL.md` — supervisor workflow skill

### Modified files
- `src/meridian/resources/.agents/agents/agent.md` — comment out mcp-tools
- `src/meridian/resources/.agents/agents/primary.md` — comment out mcp-tools, add default skills

## Implementation Steps

1. Write `meridian-run` skill (rewrite run-agent SKILL.md for CLI-native usage)
2. Write `orchestrate` skill (rewrite orchestrate SKILL.md, embed planning, make generic)
3. Update agent profiles (comment out mcp-tools, add skill references)
4. Verify skill resolution works (skills show up in `meridian skills list`)
5. Test that `meridian run spawn` with default agent picks up bundled skills

## Open Questions

- Should the bundled `orchestrate` skill reference model guidance files, or embed model selection heuristics inline?
- Should `mcp-tools` be commented out or just empty `[]`? (commented = more discoverable, but YAML frontmatter doesn't support comments)
- Do we need a `meridian init` or `meridian doctor` step to copy bundled resources into `.agents/` for discoverability?
