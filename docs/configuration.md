# Configuration

Meridian works without config files, but you can override defaults in `.meridian/config.toml`.

Developer note:
- Canonical domain term is `spawn` (see [Developer Terminology](developer-terminology.md)).
- This page includes current `run` names where they reflect active config keys or env vars.

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
        spawns/<run-id>/
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
| `defaults.primary_agent` | str | Primary profile name |
| `defaults.agent` | str | Default non-primary profile |
| `timeouts.kill_grace_seconds` | float | Grace before force-kill |
| `timeouts.guardrail_seconds` | float | Guardrail timeout |
| `timeouts.wait_seconds` | float | Default `run wait` timeout |
| `permissions.default_tier` | str | Default non-primary permission tier |
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

[permissions]
default_tier = "workspace-write"

[output]
show = ["lifecycle", "error"]
verbosity = "verbose"

[primary]
autocompact_pct = 70
permission_tier = "full-access"

[search_paths]
agents = [".agents/agents", ".claude/agents"]
skills = [".agents/skills", ".claude/skills"]
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
| `MERIDIAN_SPACE_ID` | Default space scope for run/spawn operations |
| `MERIDIAN_CHAT_ID` | Current chat/session id in nested execution |
| `MERIDIAN_DEPTH` | Current nesting depth |
| `MERIDIAN_MAX_DEPTH` | Max nesting depth override |
| `MERIDIAN_PARENT_RUN_ID` | Parent run linkage for nested execution |

### Config Overrides

- `MERIDIAN_MAX_RETRIES`
- `MERIDIAN_RETRY_BACKOFF_SECONDS`
- `MERIDIAN_KILL_GRACE_SECONDS`
- `MERIDIAN_GUARDRAIL_TIMEOUT_SECONDS`
- `MERIDIAN_WAIT_TIMEOUT_SECONDS`
- `MERIDIAN_DEFAULT_PERMISSION_TIER`
- `MERIDIAN_PRIMARY_AGENT`
- `MERIDIAN_DEFAULT_AGENT`

### Guardrails and Secrets

| Variable | Purpose |
|---|---|
| `MERIDIAN_GUARDRAIL_RUN_ID` | Spawn id passed to guardrail scripts |
| `MERIDIAN_GUARDRAIL_OUTPUT_LOG` | Path to `output.jsonl` |
| `MERIDIAN_GUARDRAIL_REPORT_PATH` | Path to `report.md` |
| `MERIDIAN_SECRET_<KEY>` | Secret injection/redaction channel |

## Permission Naming

Use `workspace-write` (not `space-write`) as the writable middle tier.
