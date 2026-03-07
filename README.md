# meridian-channel

NOTE THIS IS POTENTIALLY UNSTABLE RIGHT NOW

[![PyPI](https://img.shields.io/pypi/v/meridian-channel)](https://pypi.org/project/meridian-channel/)
[![Python](https://img.shields.io/pypi/pyversions/meridian-channel)](https://pypi.org/project/meridian-channel/)
[![License](https://img.shields.io/github/license/haowjy/meridian-channel)](LICENSE)
[![CI](https://github.com/haowjy/meridian-channel/actions/workflows/meridian-ci.yml/badge.svg)](https://github.com/haowjy/meridian-channel/actions)

Multi-model agent orchestrator with one primary agent per space and portable run tooling across Claude, Codex, and OpenCode harnesses.

## What it does

`meridian` provides one interface for:

- Spawning model runs (`meridian run spawn`)
- Managing space lifecycle (`meridian space start/resume/close/...`)
- Serving the same operations over MCP (`meridian serve`)
- Tracking state in files under `.meridian/.spaces/<space-id>/` (no SQLite authority)

## Install

Requires **Python 3.12+** and at least one harness CLI:
[Claude CLI](https://docs.anthropic.com/en/docs/claude-code),
[Codex CLI](https://github.com/openai/codex), or
[OpenCode](https://opencode.ai).

```bash
uv tool install meridian-channel
# or: pipx install meridian-channel
# or: pip install meridian-channel
```

### From source

```bash
git clone https://github.com/haowjy/meridian-channel.git
cd meridian-channel
uv sync --extra dev
uv run meridian --help
```

## Usage


### Run in background + inspect

```bash
RUN_ID=$(meridian run spawn -p "Refactor auth module" -m gpt-5.3-codex)
meridian run wait "$RUN_ID"
meridian run show "$RUN_ID" --report
```

### Run a in the forground

```bash
meridian run spawn --foreground -p "Fix the failing test" -m claude-sonnet-4-6
```

### Use skills and references

```bash
meridian run spawn -p "Review this code" -m claude-opus-4-6 -s review -f src/main.py
```

### Continue a run

```bash
meridian run continue @latest -p "Also add tests"
```

### Spaces

```bash
meridian space start --name auth-refactor
export MERIDIAN_SPACE_ID=s1
meridian run spawn -p "Research current implementation" -s research
meridian run spawn -p "Implement changes" -m gpt-5.3-codex
meridian space close s1
```

### Search state files

```bash
meridian grep "ERROR \[SPACE_REQUIRED\]"
meridian grep "run.spawn" --space s1 --type runs
```

### Config

```bash
meridian config init
meridian config set defaults.max_retries 5
meridian config show
```

### MCP server

```bash
meridian serve
```

## State Layout

All authoritative run/space/session state is file-backed:

```text
.meridian/
  .spaces/
    <space-id>/
      space.json
      runs.jsonl
      sessions.jsonl
      runs/<run-id>/
        output.jsonl
        stderr.log
        report.md
      fs/
        space-summary.md
  active-spaces/<space-id>.lock
  config.toml
  models.toml
```

Writes use lock files plus atomic tmp+rename semantics in the state layer.

## Docs

- [CLI Reference](docs/cli-reference.md)
- [Development Install](docs/development-install.md)
- [Developer Terminology (Spawn vs Run)](docs/developer-terminology.md)
- [Agent CLI Spec (Target)](_docs/cli-spec-agent.md)
- [Human CLI Spec (Target)](_docs/cli-spec-human.md)
- [Spaces](docs/spaces.md)
- [Configuration](docs/configuration.md)
- [Safety](docs/safety.md)
- [MCP Tools](docs/mcp-tools.md)
- [Harness Adapters](docs/harness-adapters.md)

## Development

```bash
uv sync --extra dev
uv run pytest-llm
uv run pyright
```

## License

MIT
