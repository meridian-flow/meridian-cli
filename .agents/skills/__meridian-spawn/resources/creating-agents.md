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

Focus on:

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

Execute the task described in your prompt. Run tests and type checks after
making changes. Commit after each passing step.
```

## Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Profile identifier, used with `-a` |
| `description` | string | yes | Short description of the agent's role |
| `model` | string | no | Default model (can be overridden with `-m`) |
| `effort` | string | no | Effort level for reasoning: low, medium, high, xhigh |
| `skills` | string[] | no | Skills to load for this agent |
| `sandbox` | string | no | Permission tier: `read-only`, `workspace-write`, `full-access`, `unrestricted` |
| `tools` | string[] | no | Explicit tool allowlist (permission-required tools for Claude/OpenCode `-p` mode) |
| `mcp-tools` | string[] | no | MCP tools to expose |

Example frontmatter field:

```yaml
mcp-tools: [fetch, filesystem]
```

## Body

The markdown body below the frontmatter is the agent's system prompt. Describe behaviors directly — what the agent should do, how it should report results, and what constraints it operates under. Avoid assigning roles or personas ("You are a..."); the frontmatter already identifies the agent's purpose, so the body should focus on actionable instructions and reasoning.

## Usage

```bash
# Use the profile as-is
meridian spawn -a reviewer -p "Review the auth changes"

# Override the profile's model
meridian spawn -a reviewer -m sonnet -p "Quick review"

# List available profiles
mars list               # shows installed agents and skills
```

## Search Paths

At runtime, Meridian reads agent profiles from `.agents/agents/` only.

Bundled agents are installed/bootstrapped into that directory (for example via `mars sync`), so they appear as normal local profiles.

## Design Principles

For guidance on writing effective agent prompts and skills — no role identity, explaining why constraints exist, right altitude, progressive disclosure, tool restrictions — read [`resources/agent-design-principles.md`](resources/agent-design-principles.md).

## Tips

- **One role per profile.** Mixing review and implementation in one agent creates conflicts of interest and bloats the system prompt, diluting both sets of instructions.
- **Model choice matters.** Match model strength to task value — strong reasoning models for review and architecture, fast models for implementation and bulk work. Run `meridian models list` for current options.
- **Permissions scope risk.** Use `read-only` for analysis, `workspace-write` for implementation, `full-access` only when needed.
- **Tools enable `-p` mode.** Without `tools:`, Claude agents can't use permission-required tools (Bash, Write, Edit, WebSearch, etc.) in non-interactive mode. Only list tools that need permission — Read, Glob, Grep, and Agent are always available.
- **Skills are optional.** Most task agents don't need skills — they get their instructions from the prompt. Skills are for agents that need to coordinate (orchestrators) or follow specific workflows.
