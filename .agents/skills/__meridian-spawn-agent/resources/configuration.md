# Configuration

Meridian configuration controls defaults for models, agents, and timeouts. All config is project-local under `.meridian/config.toml`.

## Quick Reference

```bash
meridian config init              # scaffold config.toml with commented defaults
meridian config show              # show all resolved values with sources
meridian config get defaults.model  # get one key
meridian config set defaults.model gpt-5.4  # set one key
meridian config reset defaults.model  # remove override, revert to builtin
```

## Key Settings

### Models and Agents

| Key | Description | Default |
|-----|-------------|---------|
| `defaults.model` | Default model for `meridian spawn` when no `-m` given | `gpt-5.3-codex` |
| `defaults.agent` | Default agent profile for spawns | `__meridian-subagent` |
| `defaults.primary_agent` | Agent profile for `meridian` primary sessions | `__meridian-orchestrator` |

### Per-Harness Model Defaults

| Key | Description | Default |
|-----|-------------|---------|
| `harness.claude` | Default model routed to Claude | `claude-opus-4-6` |
| `harness.codex` | Default model routed to Codex | `gpt-5.3-codex` |
| `harness.opencode` | Default model routed to OpenCode | `gemini-3.1-pro` |

### Timeouts

| Key | Description | Default |
|-----|-------------|---------|
| `timeouts.wait_minutes` | How long `spawn wait` blocks | `30` |
| `timeouts.guardrail_minutes` | Grace period before timeout warning | `0.5` |
| `timeouts.kill_grace_minutes` | Grace period after SIGINT before SIGKILL | `0.033` |

### Retries

| Key | Description | Default |
|-----|-------------|---------|
| `defaults.max_retries` | Max retry attempts for failed spawns | `3` |
| `defaults.retry_backoff_seconds` | Backoff between retries | `0.25` |

## Config File Format

```toml
# .meridian/config.toml

[defaults]
model = "gpt-5.4"
agent = "my-custom-agent"

[timeouts]
wait_minutes = 60
```

## Resolution Order

Config values resolve in this order (later wins):

1. Builtin defaults (hardcoded)
2. `.meridian/config.toml` (project-local overrides)
3. CLI flags (`-m`, `--permission`, `--timeout`)

Use `meridian config show` to see the resolved value and its source for every key.
