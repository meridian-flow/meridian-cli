# agents.toml Manifest Reference

The manifest at `.meridian/agents.toml` declares external sources for agents and skills. Each `[[sources]]` block is one source — a git repo or local directory to sync from.

## Source Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique identifier (alphanumeric, hyphens, underscores) |
| `kind` | `"git"` or `"path"` | Yes | Source type |
| `url` | string | git only | Full git URL (https or ssh) |
| `path` | string | path only | Local path (absolute, relative to repo root, or `~`) |
| `ref` | string | Optional | Branch, tag, or commit SHA (git only) |
| `agents` | array of strings | Optional | Agent include filter — only install these agents |
| `skills` | array of strings | Optional | Skill include filter — only install these skills |
| `exclude_items` | array | Optional | Exclude filter — install everything except these |
| `rename` | table | Optional | Rename items at install time |

### Validation

- `kind = "git"` requires `url`, must not have `path`
- `kind = "path"` requires `path`, must not have `url` or `ref`
- Source names must be unique across the manifest

## Item Filtering

By default, every agent and skill discovered in a source is installed. Filters narrow the selection:

- **`agents` / `skills` only**: install only listed items (selective sync)
- **`exclude_items` only**: install everything except listed items
- **Both**: `agents`/`skills` defines the initial set, `exclude_items` removes from it

Use selective sync when a source contains many items but you only need a few — it keeps `.agents/` focused and avoids name collisions.

Agent/skill format: `agents = ["name1", "name2"]` / `skills = ["name1"]`
Exclude format: `exclude_items = [{ kind = "agent", name = "..." }]`

### Skill Dependency Resolution

When agents are explicitly selected with `agents = [...]`, the engine automatically reads each agent's YAML frontmatter to find `skills: [...]` dependencies. Matching skills from the same source are auto-included — no need to manually list them.

For example, if `__meridian-orchestrator` declares `skills: [__meridian-orchestration, __meridian-spawn]`, installing just the agent will auto-install both skills.

## Renames

Rename items to avoid collisions or customize names for your project. Keys use canonical `kind:name` format:

```toml
rename = { "agent:reviewer" = "team-reviewer", "skill:design" = "team-design" }
```

Renames apply after filtering — the `name` in `agents`/`skills` uses the source name, not the renamed name.

## Addressing

Three explicit forms for specifying sources:

```bash
meridian sources install ./local-agents              # Local path
meridian sources install @haowjy/meridian-core       # GitHub shorthand (@owner/repo)
meridian sources install https://github.com/org/repo.git  # Full URL
```

`@owner/repo` expands to `https://github.com/owner/repo.git`. The source name is auto-derived from the repo name (e.g., `meridian-core`).

## Example Manifest

```toml
# Core Meridian agents and skills from the official repo.
# Selective sync — only the items needed for orchestration.
# Skill deps (__meridian-orchestration, __meridian-spawn) are
# auto-resolved from agent frontmatter.
[[sources]]
name = "meridian-base"
kind = "git"
url = "https://github.com/haowjy/meridian-base.git"
ref = "main"
agents = ["__meridian-orchestrator", "__meridian-subagent"]
skills = ["__meridian-orchestration", "__meridian-spawn", "__meridian-install"]

# Team-shared agents pinned to a release tag.
[[sources]]
name = "team-agents"
kind = "git"
url = "https://github.com/myorg/team-agents.git"
ref = "v1.2.0"
rename = { "agent:reviewer" = "team-reviewer" }

# Local development drafts — path sources re-read on every update.
[[sources]]
name = "local-dev"
kind = "path"
path = "./my-local-agents"
exclude_items = [{ kind = "agent", name = "experimental" }]
```

## Additive Install

Running `meridian sources install` against an existing source **merges** new items into the existing selection instead of erroring:

```bash
meridian sources install @haowjy/meridian-core --agents __meridian-orchestrator
meridian sources install @haowjy/meridian-core --agents __meridian-subagent
# Result: agents = ["__meridian-orchestrator", "__meridian-subagent"]
```

The merge rule: `None` (all) + specific → stays `None`. Specific + more → union. Specific + `None` → `None`.

## Source Layout Convention

The install engine discovers items by conventional directory structure. Sources should be organized as:

```
source-root/
  agents/
    agent-name.md          # One markdown file per agent profile
  skills/
    skill-name/
      SKILL.md             # Required entry point for each skill
      resources/           # Optional supporting files
        reference.md
```

Discovery scans for `agents/*.md` and `skills/*/SKILL.md` relative to the source root. Files outside this convention are ignored.
