# Getting Started

## Prerequisites

Meridian is a coordination layer — it needs at least one harness installed to run agents.

| Harness     | Model prefixes                  | Install                                                              |
| ----------- | ------------------------------- | -------------------------------------------------------------------- |
| Claude Code | `claude-*`, `sonnet*`, `opus*`  | [docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code) |
| Codex CLI   | `gpt-*`, `codex*`, `o3*`, `o4*` | [github.com/openai/codex](https://github.com/openai/codex) |
| OpenCode    | anything else                   | [opencode.ai](https://opencode.ai) |

**Claude Code** is the most mature primary-session harness. Codex also supports managed primary TUI passthrough, including hidden instruction routing and managed session tracking. See [codex-tui-passthrough.md](codex-tui-passthrough.md).

**Platform**: macOS, Linux, Windows, WSL.

## Install

```bash
uv tool install meridian-cli
```

If `meridian` is not found after install, run `uv tool update-shell` and restart your shell.

## Initialize a Project

```bash
cd your-repo
meridian init
```

This creates `.meridian/` with a project UUID and default `.gitignore`. The `.gitignore` inside `.meridian/` is managed automatically — it tracks `id`, `kb/`, `work/`, and `archive/` and ignores everything else. Spawn history and session state live at the user level (`~/.meridian/projects/<uuid>/`) and are never committed.

## Tool Integration

To expose installed agent packages to a harness tool directory (`.claude/`, `.cursor/`, etc.), use the top-level convenience flag:

```bash
meridian init --link .claude
```

`meridian init --link` keeps config/bootstrap at the top level and delegates package-link wiring to mars:
- no `mars.toml` yet: runs `meridian mars init --link .claude`
- existing mars project: runs `meridian mars link .claude`

You can also call mars directly:

```bash
meridian mars init --link .claude
```

After `mars.toml` exists, additional link targets use:

```bash
meridian mars link .claude
```

This symlinks `.agents/` into the target directory so harnesses discover the agents and skills without duplication.

## Verify Setup

```bash
meridian config show   # confirm resolved config
meridian mars models list   # confirm available models
meridian doctor        # check harness connectivity
```

## Multi-Repo Workspace (optional)

If you work across multiple repos and want agents to see sibling directories, set up a local workspace file:

```bash
meridian workspace init   # creates workspace.local.toml, adds .git/info/exclude coverage
```

Edit `workspace.local.toml` to declare which repos to include:

```toml
[[context-roots]]
path = "../sibling-repo"
```

Each enabled, existing root is projected to harness launches automatically — `--add-dir` for Claude Code, `OPENCODE_CONFIG_CONTENT` for OpenCode. See [configuration.md](configuration.md#workspace) for full schema and per-harness details.

## Next Steps

- [commands.md](commands.md) — full CLI reference
- [configuration.md](configuration.md) — config keys, model routing, environment variables
- [codex-tui-passthrough.md](codex-tui-passthrough.md) — managed Codex startup, bootstrap, and attach behavior
- [hooks.md](hooks.md) — hook events, builtin hooks, and `git-autosync`
- [plugin-api.md](plugin-api.md) — stable API for hook and plugin authors
