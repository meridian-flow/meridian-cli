# Creating Agent Profiles

Agent profiles define reusable spawn configurations — model, system prompt, skills, and permissions in one file. Use them when you find yourself repeating the same `-m MODEL` + prompt preamble across spawns.

## File Format

Agent profiles are markdown files with YAML frontmatter. Place them in `.agents/agents/`:

```
.agents/agents/
  reviewer.md
  implementer.md
  qa.md
```

### Example: reviewer

```markdown
---
name: reviewer
description: Code reviewer focused on correctness and simplicity
model: gpt-5.4
skills: []
tools: [Bash(git diff *), Bash(git log *), Bash(git show *)]
sandbox: read-only
---

You are a code reviewer. Focus on:

- Correctness — does the code do what it claims?
- Simplicity — is there unnecessary complexity?
- Consistency — does it match the surrounding codebase style?

Write a structured review with specific file/line references.
```

### Example: implementer

```markdown
---
name: implementer
description: Task execution agent for implementation work
model: gpt-5.3-codex
skills: []
tools: [Bash, Write, Edit]
sandbox: workspace-write
---

You are an implementation agent. Execute the task described in your prompt.
Run tests and type checks after making changes. Commit after each passing step.
```

## Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Profile identifier, used with `-a` |
| `description` | string | yes | Short description of the agent's role |
| `model` | string | no | Default model (can be overridden with `-m`) |
| `skills` | string[] | no | Skills to load for this agent |
| `sandbox` | string | no | Permission tier: `read-only`, `workspace-write`, `full-access`, `unrestricted` |
| `tools` | string[] | no | Explicit tool allowlist (permission-required tools for Claude/OpenCode `-p` mode) |
| `mcp_tools` | string[] | no | MCP tools to expose |

## Body

The markdown body below the frontmatter is the agent's system prompt — instructions, persona, constraints. Keep it focused on what the agent should do and how it should report results.

## Usage

```bash
# Use the profile as-is
meridian spawn -a reviewer -p "Review the auth changes"

# Override the profile's model
meridian spawn -a reviewer -m sonnet -p "Quick review"

# List available profiles
meridian sources list   # shows installed agents and skills
```

## Search Paths

Meridian looks for agent profiles in this order:

1. `.agents/agents/` (repo-local)
2. Meridian's bundled defaults (`__meridian-orchestrator`, `__meridian-subagent`)

Repo-local profiles take precedence over bundled ones with the same name.

## Tips

- **One role per profile.** A reviewer shouldn't also be an implementer. Keep agents focused.
- **Model choice matters.** Strong reasoning models (opus, gpt-5.4) for review and architecture. Fast models (codex, sonnet) for implementation and bulk work.
- **Permissions scope risk.** Use `read-only` for analysis, `workspace-write` for implementation, `full-access` only when needed.
- **Tools enable `-p` mode.** Without `tools:`, Claude agents can't use permission-required tools (Bash, Write, Edit, WebSearch, etc.) in non-interactive mode. Only list tools that need permission — Read, Glob, Grep, and Agent are always available.
- **Skills are optional.** Most task agents don't need skills — they get their instructions from the prompt. Skills are for agents that need to coordinate (orchestrators) or follow specific workflows.
