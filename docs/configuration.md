# Configuration

Meridian works without config files, but you can override defaults in `.meridian/config.toml`.

By default Meridian searches repo-local `.agents`, `.claude`, `.codex`,
`.opencode`, `.cursor`, plus user-level `~/.claude`, `~/.codex`, and
`~/.opencode` agent/skill directories.

## Quick Start

```bash
meridian config init
meridian config show
meridian config set defaults.max_retries 5
meridian config get defaults.max_retries
meridian config reset defaults.max_retries
```

## Repository Layout

```text
<repo-root>/
  .agents/
    agents/
    skills/
  .meridian/
    config.toml
    models.toml
    active-spaces/
    .spaces/
      <space-id>/
        space.json
        spawns.jsonl
        sessions.jsonl
        spawns/<spawn-id>/
        fs/
```

File state under `.meridian/.spaces/*` is authoritative for spaces/spawns/sessions.

## `config.toml` Keys

Canonical keys accepted by `meridian config set/get/reset`:

| Key | Type | Purpose |
|---|---|---|
| `defaults.max_depth` | int | Max nested agent depth |
| `defaults.max_retries` | int | Retry attempts per run |
| `defaults.retry_backoff_seconds` | float | Retry backoff multiplier |
| `defaults.default_primary_agent` | str | Primary profile name |
| `defaults.agent` | str | Default non-primary profile |
| `defaults.model` | str | Default model for spawn when unset |
| `timeouts.kill_grace_minutes` | float | Grace before force-kill (minutes) |
| `timeouts.guardrail_minutes` | float | Guardrail timeout (minutes) |
| `timeouts.wait_minutes` | float | Default `spawn wait` timeout (minutes) |
| `permissions.default_tier` | str | Default non-primary permission tier |
| `harness.claude` | str | Default model for Claude harness |
| `harness.codex` | str | Default model for Codex harness |
| `harness.opencode` | str | Default model for OpenCode harness |
| `output.show` | array[str] | Stream categories shown |
| `output.verbosity` | str\|null | `quiet\|normal\|verbose\|debug` |

Scaffolded but not exposed via `config set` shorthand keys:

- `[primary] autocompact_pct`, `permission_tier`
- `[search_paths] agents`, `skills`, `global_agents`, `global_skills`

## Example

```toml
[defaults]
max_depth = 4
agent = "coder"
model = "gpt-5.3-codex"

[permissions]
default_tier = "workspace-write"

[harness]
claude = "claude-opus-4-6"
codex = "gpt-5.3-codex"
opencode = "gemini-3.1-pro"

[output]
show = ["lifecycle", "error"]
verbosity = "verbose"

[primary]
autocompact_pct = 70
permission_tier = "full-access"

[search_paths]
agents = [".agents/agents", ".claude/agents", ".codex/agents", ".opencode/agents"]
skills = [".agents/skills", ".claude/skills", ".codex/skills", ".opencode/skills"]
global_agents = ["~/.claude/agents", "~/.codex/agents", "~/.opencode/agents"]
global_skills = ["~/.claude/skills", "~/.codex/skills", "~/.opencode/skills"]
```

## Model Catalog Overrides

Override or add models in `.meridian/models.toml`:

```toml
[[models]]
model_id = "my-custom-model-v1"
aliases = ["mymodel", "mm"]
harness = "opencode"
role = "Custom"
strengths = "Domain-specific"
cost_tier = "$$"
```

## Environment Variables

### Core

| Variable | Purpose |
|---|---|
| `MERIDIAN_REPO_ROOT` | Force repo root resolution |
| `MERIDIAN_CONFIG` | User config overlay path |
| `MERIDIAN_STATE_ROOT` | Override state root (default `.meridian`) |
| `MERIDIAN_SPACE_ID` | Optional default space scope for spawn operations |
| `MERIDIAN_SPACE_FS_DIR` | Resolved shared filesystem path for the current space |
| `MERIDIAN_SPAWN_ID` | Current spawn ID in nested execution |
| `MERIDIAN_CHAT_ID` | Current chat/session id in nested execution |
| `MERIDIAN_DEPTH` | Current nesting depth |
| `MERIDIAN_MAX_DEPTH` | Max nesting depth override |
| `MERIDIAN_PARENT_SPAWN_ID` | Parent spawn linkage for nested execution |
| `MERIDIAN_HARNESS_COMMAND` | Override harness command resolution |

### Config Overrides

- `MERIDIAN_MAX_RETRIES`
- `MERIDIAN_RETRY_BACKOFF_SECONDS`
- `MERIDIAN_KILL_GRACE_MINUTES`
- `MERIDIAN_GUARDRAIL_TIMEOUT_MINUTES`
- `MERIDIAN_WAIT_TIMEOUT_MINUTES`
- `MERIDIAN_DEFAULT_PERMISSION_TIER`
- `MERIDIAN_DEFAULT_PRIMARY_AGENT`
- `MERIDIAN_DEFAULT_AGENT`
- `MERIDIAN_DEFAULT_MODEL`
- `MERIDIAN_HARNESS_MODEL_CLAUDE`
- `MERIDIAN_HARNESS_MODEL_CODEX`
- `MERIDIAN_HARNESS_MODEL_OPENCODE`

### Guardrails and Secrets

| Variable | Purpose |
|---|---|
| `MERIDIAN_GUARDRAIL_RUN_ID` | Spawn id passed to guardrail scripts |
| `MERIDIAN_GUARDRAIL_OUTPUT_LOG` | Path to `output.jsonl` |
| `MERIDIAN_GUARDRAIL_REPORT_PATH` | Path to `report.md` when a report exists |
| `MERIDIAN_SECRET_<KEY>` | Secret injection/redaction channel |

## Permission Naming

Use `workspace-write` (not `space-write`) as the writable middle tier.
