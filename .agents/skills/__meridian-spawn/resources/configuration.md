# Configuration

Meridian configuration controls defaults for models, agents, runtime behavior, and timeouts. Config lives in two locations: project-local (`.meridian/config.toml`) and user-level (`~/.config/meridian/config.toml` or `$MERIDIAN_USER_CONFIG`).

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

### Primary Session Overrides

These control the runtime behavior of the primary (top-level) agent session:

| Key | ENV var | Description |
|-----|---------|-------------|
| `primary.model` | `MERIDIAN_MODEL` | Model for the primary session |
| `primary.harness` | `MERIDIAN_HARNESS` | Harness for the primary session |
| `primary.thinking` | `MERIDIAN_THINKING` | Thinking budget: `low`, `medium`, `high`, `xhigh` |
| `primary.sandbox` | `MERIDIAN_SANDBOX` | Sandbox mode: `read-only`, `workspace-write`, `full-access`, `danger-full-access`, `unrestricted` |
| `primary.approval` | `MERIDIAN_APPROVAL` | Permission approval mode: `default`, `confirm`, `auto`, `yolo` |
| `primary.timeout` | `MERIDIAN_TIMEOUT` | Maximum runtime in minutes |
| `primary.autocompact` | `MERIDIAN_AUTOCOMPACT` | Autocompact threshold percentage (1–100) |

> **Deprecation note:** `primary.autocompact_pct` is a deprecated alias for `primary.autocompact`. Use `primary.autocompact` in new configs.

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

## Environment Variables

Environment variables override config file values. Available variables:

| Variable | Overrides |
|----------|-----------|
| `MERIDIAN_MODEL` | `primary.model` |
| `MERIDIAN_HARNESS` | `primary.harness` |
| `MERIDIAN_THINKING` | `primary.thinking` |
| `MERIDIAN_SANDBOX` | `primary.sandbox` |
| `MERIDIAN_APPROVAL` | `primary.approval` |
| `MERIDIAN_TIMEOUT` | `primary.timeout` |
| `MERIDIAN_AUTOCOMPACT` | `primary.autocompact` |

## Spawn CLI Flags

CLI flags on `meridian spawn` override everything — agent profiles, config, and environment:

| Flag | Description |
|------|-------------|
| `-m`, `--model` | Model id or alias |
| `--harness` | Harness to use |
| `--thinking` | Thinking budget: `low`, `medium`, `high`, `xhigh` |
| `--sandbox` | Sandbox mode: `read-only`, `workspace-write`, `full-access`, `danger-full-access`, `unrestricted` |
| `--approval` | Approval mode: `default`, `confirm`, `auto`, `yolo` |
| `--autocompact` | Autocompact threshold percentage (1–100) |
| `--timeout` | Maximum runtime in minutes |

## Config File Format

```toml
# .meridian/config.toml

[defaults]
model = "gpt-5.4"
agent = "my-custom-agent"

[primary]
thinking = "high"
sandbox = "workspace-write"
approval = "auto"
autocompact = 80

[timeouts]
wait_minutes = 60
```

## Resolution Order

Config values resolve in this order (first match wins):

1. CLI flags (`-m`, `--thinking`, `--sandbox`, `--approval`, `--autocompact`, `--timeout`, `--harness`)
2. Environment variables (`MERIDIAN_MODEL`, `MERIDIAN_THINKING`, etc.)
3. YAML agent profile (frontmatter fields: `model`, `thinking`, `sandbox`, `approval`, `autocompact`)
4. Project config (`.meridian/config.toml`)
5. User config (`~/.config/meridian/config.toml`)
6. Harness default

Project TOML wins over user TOML — project-specific settings always take precedence over user-level defaults.

Use `meridian config show` to see the resolved value and its source for every key.
