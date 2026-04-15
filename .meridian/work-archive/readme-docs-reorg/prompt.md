# Meridian Docs Reorganization

The meridian-cli README was just rewritten to be concise (following the uv/ripgrep/bun pattern: one-liner → why → install → show → links). Several sections were cut from the README that need to land in `docs/`.

## Content to migrate into docs/

The following content was in the old README and has no home in `docs/` yet. Create appropriate doc files for them.

### 1. Getting Started / Prerequisites (new file: docs/getting-started.md)

Detailed harness prerequisites with the table:

| Harness     | Model prefixes                  | Install                                                              |
| ----------- | ------------------------------- | -------------------------------------------------------------------- |
| Claude Code | `claude-`*, `sonnet*`, `opus*`  | docs.anthropic.com |
| Codex CLI   | `gpt-*`, `codex*`, `o3*`, `o4*` | github.com/openai/codex |
| OpenCode    | anything else                   | opencode.ai |

Plus the notes about:
- Claude Code being the primary session harness (supports system prompt injection)
- Codex and OpenCode working well as spawn targets
- The `--link` setup for tool integration (.claude/, .cursor/)
- Platform requirements (macOS, Linux, WSL)

### 2. CLI Reference (new file: docs/commands.md)

Full commands table — spawning, reports/sessions, configuration, package management. Currently no CLI reference doc exists.

**Spawning & monitoring:**

| Command                                  | Description                        |
| ---------------------------------------- | ---------------------------------- |
| `meridian`                               | Launch the primary agent session   |
| `meridian spawn -a AGENT -p "task"`      | Delegate work to a routed model    |
| `meridian spawn list`                    | See running and recent spawns      |
| `meridian spawn wait ID`                 | Block until a spawn completes      |
| `meridian spawn show ID`                 | Read a spawn's report              |
| `meridian spawn --continue ID -p "more"` | Continue a prior spawn             |
| `meridian spawn --from ID -p "next"`     | Start new spawn with prior context |

**Reports & sessions:**

| Command                           | Description                     |
| --------------------------------- | ------------------------------- |
| `meridian report search "query"`  | Search across all spawn reports |
| `meridian session search "query"` | Search session transcripts      |

**Configuration & diagnostics:**

| Command                         | Description                                                           |
| ------------------------------- | --------------------------------------------------------------------- |
| `meridian init [--link DIR]`    | Initialize project                                                    |
| `meridian config show`          | Show resolved config                                                  |
| `meridian config set KEY VALUE` | Set a config value                                                    |
| `meridian models list`          | Inspect the model catalog                                             |
| `meridian doctor`               | Run diagnostics                                                       |
| `meridian serve`                | Start the MCP server                                                  |

**Package management (mars):**

| Command                    | Description                                  |
| -------------------------- | -------------------------------------------- |
| `meridian mars add SOURCE` | Add an agent/skill package source            |
| `meridian mars sync`       | Resolve and install packages                 |
| `meridian mars link DIR`   | Symlink .agents/ into a tool directory       |
| `meridian mars list`       | Show installed agents and skills             |
| `meridian mars upgrade`    | Fetch latest versions and sync               |

### 3. State Layout (add to docs/configuration.md or new file)

The `.meridian/` directory structure:

```
.meridian/
  .gitignore
  spawns.jsonl          # Spawn event log
  sessions.jsonl        # Session event log
  spawns/
    p1/
      output.jsonl      # Spawn output
      stderr.log        # Stderr capture
      report.md         # Agent's report
  fs/                   # Shared filesystem between spawns
  work-items/           # Work item metadata
  work/                 # Work item directories
  work-archive/         # Completed work item scratch/docs
  config.toml           # Repo configuration
  models.toml           # Model aliases and routing overrides
```

### 4. Troubleshooting (new file: docs/troubleshooting.md)

- `meridian` not found → `uv tool update-shell`
- `meridian doctor` reports missing harnesses → install harness
- Model routes to wrong harness → check `meridian models list` and `meridian config show`
- Spawn disconnected from earlier work → `--continue ID`, `--from ID`, `meridian report search`

## Important notes

- DO NOT touch the README.md — it was just rewritten intentionally.
- Read the current `docs/` files (configuration.md, mcp-tools.md) first so you don't duplicate.
- Write for developers who already installed meridian and want reference material. The README handles the pitch and quick start.
- Keep it concise — reference docs, not tutorials.
- Update the README's Docs section links if you create new files.
