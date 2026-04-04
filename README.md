# meridian

[![PyPI](https://img.shields.io/pypi/v/meridian-channel)](https://pypi.org/project/meridian-channel/)
[![Python](https://img.shields.io/pypi/pyversions/meridian-channel)](https://pypi.org/project/meridian-channel/)
[![License](https://img.shields.io/github/license/haowjy/meridian-channel)](LICENSE)
[![CI](https://github.com/haowjy/meridian-channel/actions/workflows/meridian-ci.yml/badge.svg)](https://github.com/haowjy/meridian-channel/actions)

> **Alpha** — API may change between releases.

A coordination layer for AI agents. One agent spawns others, routes them to the
right model, and reads their results — across Claude, Codex, and OpenCode.

You talk to one agent. It delegates the rest.

## What This Looks Like

You say: *"Refactor the auth module to use JWT tokens."*

The orchestrator agent — running inside Claude, Codex, or any supported
harness — autonomously runs commands like these:

```bash
# Spawn a researcher on a fast model to explore the codebase
meridian spawn -a researcher -p "Map the auth module — token handling, session management, middleware"
# → {"spawn_id": "p1", "status": "running", "model": "gpt-5.3-codex"}

# Wait for it, then read what it found
meridian spawn wait p1
meridian spawn show p1

# Spawn coders in parallel on Codex, passing the researcher's findings
meridian spawn -a coder --from p1 -p "Phase 1: Replace session tokens with JWT" -f src/auth/tokens.py
# → {"spawn_id": "p2", "model": "gpt-5.3-codex"}
meridian spawn -a coder --from p1 -p "Phase 2: Update middleware validation" -f src/auth/middleware.py
# → {"spawn_id": "p3", "model": "gpt-5.3-codex"}
meridian spawn wait p2 p3

# Fan out reviewers with different focus areas
meridian spawn -a reviewer --from p2 -p "Review phase 1 — focus on token expiry edge cases"
# → {"spawn_id": "p4", "model": "gpt-5.4"}
meridian spawn show p4

# Pick up context from a prior session
meridian session search "auth refactor"
meridian report search "JWT decision"
```

Every spawn writes logs, reports, and metadata to shared state under `.meridian/`.
The orchestrator reads those reports, decides what to do next, and keeps going.
If the session gets compacted or resumed later, the state is still there.

**The human doesn't run these commands.** The agent does — meridian is the CLI
that agents use to coordinate other agents.

## Agent Packages

[**meridian-dev-workflow**](https://github.com/haowjy/meridian-dev-workflow) — A full dev team: architects, coders, reviewers, testers, researchers, documenters, and the orchestrators that coordinate them. Includes skills for design methodology, implementation planning, code review, and structural hygiene. This is what most users want.

[**meridian-base**](https://github.com/haowjy/meridian-base) — Core coordination primitives: the base orchestrator, subagent, and skills for spawning, state tracking, and session context. Included as a dependency of meridian-dev-workflow.

Packages are managed by [**mars**](https://github.com/haowjy/mars-agents), an agent package manager that installs agent profiles and skills from git sources into your project's `.agents/` directory.

## Install

```bash
uv tool install meridian-channel
```

Verify:

```bash
meridian --version
meridian doctor
```

<details>
<summary>Alternative install methods</summary>

```bash
pipx install meridian-channel    # if you prefer pipx
pip install meridian-channel     # into a Python environment
```

From source:

```bash
git clone https://github.com/haowjy/meridian-channel.git
cd meridian-channel
uv tool install --force . --no-cache --reinstall
```

Development environment (no tool install):

```bash
uv sync --extra dev
uv run meridian --help
```

If `meridian` is not on your PATH: `uv tool update-shell`

</details>

## Set Up a Project

```bash
cd your-project
meridian init --link .claude
meridian mars add haowjy/meridian-dev-workflow
```

This initializes `.meridian/`, links `.agents/` into `.claude/` so Claude Code
discovers your agents and skills, and installs the full dev team (coder,
reviewers, testers, architect, etc.) plus core coordination primitives.

For just the core primitives:

```bash
meridian mars add haowjy/meridian-base
```

To link into other tool directories (e.g. Cursor):

```bash
meridian mars link .cursor
```

### Prerequisites

**Platforms:** macOS and Linux. Windows is supported via
[WSL](https://learn.microsoft.com/en-us/windows/wsl/) (native Windows is not
supported).

You need at least one harness CLI installed and authenticated:

| Harness | Model prefixes | Install |
|---|---|---|
| Claude Code | `claude-*`, `sonnet*`, `opus*` | [docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code) |
| Codex CLI | `gpt-*`, `codex*`, `o3*`, `o4*` | [github.com/openai/codex](https://github.com/openai/codex) |
| OpenCode | anything else | [opencode.ai](https://opencode.ai) |

Claude and Codex are the most exercised paths today. OpenCode has adapter
support but lighter day-to-day coverage.

**Primary session:** Only Claude Code supports system prompt injection
(`--append-system-prompt`), which is how Meridian loads agent skills into the
primary session. Codex and OpenCode work well as **spawn targets** but aren't
as suited as the primary harness.

### Tool integration (Claude Code, Cursor, etc.)

If you didn't pass `--link .claude` during `meridian init`, you can link later:

```bash
meridian mars link .claude
```

This symlinks `.agents/` into `.claude/` so Claude Code auto-discovers your
installed agents and skills. Without linking, `meridian spawn` still works
(it injects context directly), but interactive sessions won't auto-discover
agents and skills.

To unlink: `meridian mars link --unlink .claude`

## Quick Start

```bash
meridian                  # Launch a primary agent session
```

That's it. The agent gets meridian's coordination skills injected automatically
and can start spawning work. In a separate shell, you can also drive spawns
directly:

```bash
meridian spawn -m codex -p "Fix the flaky test in tests/auth/"
meridian spawn list
meridian spawn wait p1
meridian spawn show p1
```

## Architecture

```mermaid
graph TB
    User([You]) --> Primary["meridian<br/>(primary session)"]

    subgraph Packages
        Sources["git sources"] -->|"meridian mars add/sync"| Mars["mars"]
        Mars --> Agents[".agents/"]
        Agents -->|"meridian mars link"| Tool[".claude/ · .cursor/"]
    end

    subgraph Runtime
        Primary -->|"meridian spawn"| Router{"Model router"}
        Router --> Claude["Claude Code"]
        Router --> Codex["Codex CLI"]
        Router --> OpenCode["OpenCode"]
    end

    subgraph State[".meridian/"]
        Spawns["spawns + reports"]
        Sessions["sessions"]
        Work["work items + fs"]
    end

    Agents --> Primary
    Primary --> State
    Claude & Codex & OpenCode -->|"meridian CLI"| State
```

## Commands

**Spawning & monitoring:**

| Command | Description |
|---|---|
| `meridian` | Launch the primary agent session |
| `meridian spawn -a AGENT -p "task"` | Delegate work to a routed model |
| `meridian spawn list` | See running and recent spawns |
| `meridian spawn wait ID` | Block until a spawn completes |
| `meridian spawn show ID` | Read a spawn's report |
| `meridian spawn --continue ID -p "more"` | Continue a prior spawn |
| `meridian spawn --from ID -p "next"` | Start new spawn with prior context |

**Reports & sessions:**

| Command | Description |
|---|---|
| `meridian report search "query"` | Search across all spawn reports |
| `meridian session search "query"` | Search session transcripts |

**Configuration & diagnostics:**

| Command | Description |
|---|---|
| `meridian init [--link DIR]` | Initialize project (`.meridian/`, `mars.toml`, optional tool linking) |
| `meridian config show` | Show resolved config and bootstrap `.meridian/` on first run |
| `meridian config set KEY VALUE` | Set a config value |
| `meridian models config show` | Show `.meridian/models.toml` policy overrides |
| `meridian models list` | Inspect the model catalog |
| `meridian doctor` | Run diagnostics |
| `meridian serve` | Start the MCP server |

**Package management (mars):**

| Command | Description |
|---|---|
| `meridian mars add SOURCE` | Add an agent/skill package source |
| `meridian mars sync` | Resolve and install packages into `.agents/` |
| `meridian mars link DIR` | Symlink `.agents/` into a tool directory |
| `meridian mars list` | Show installed agents and skills |
| `meridian mars upgrade` | Fetch latest versions and sync |

## State Layout

All state is files under `.meridian/` — no databases, no services. If it's not
on disk, it doesn't exist.

```
.meridian/
  .gitignore            # Tracks shared repo state, ignores machine-local state
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
  models.toml           # Model aliases, routing, and visibility overrides
```

Writes use `fcntl.flock` plus atomic tmp+rename. If meridian is killed
mid-spawn, the next read detects and reports the orphaned state.

## Troubleshooting

**`meridian` not found** — Run `uv tool update-shell` and restart your shell.

**`meridian doctor` reports missing harnesses** — Install and authenticate at
least one harness CLI (see Prerequisites).

**Model routes to wrong harness** — Check `meridian models list` and
`meridian config show`.

**Spawn feels disconnected from earlier work** — Use `--continue ID` for
session continuity, `--from ID` for context injection, or search past work
with `meridian report search`.

## Documentation

- [Configuration](docs/configuration.md) — config keys, overrides, environment variables
- [MCP Tools](docs/mcp-tools.md) — FastMCP tool surface and payload examples
- [INSTALL.md](INSTALL.md) — agent-friendly install guide (give this URL to your LLM)

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run pytest-llm
uv run pyright
```

See [DEVELOPMENT.md](DEVELOPMENT.md) for full dev setup.

## License

[MIT](LICENSE)
