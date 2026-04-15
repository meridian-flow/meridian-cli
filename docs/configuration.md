# Configuration

Meridian works without config files, but you can override defaults in `.meridian/config.toml`.

By default Meridian discovers agents and skills from repo-local `.agents/` only.
Harness-specific compatibility paths such as `.claude/` are runtime concerns, not
Meridian discovery roots.

## Quick Start

```bash
meridian
meridian config show
meridian config init
meridian config set defaults.max_retries 5
meridian config get defaults.max_retries
meridian config reset defaults.max_retries
meridian models config show
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
    fs/
    work-items/
    work/
    work-archive/
    spawns/
      <spawn-id>/
    spawns.jsonl
    sessions.jsonl
```

File state under `.meridian/` is authoritative for spawns, sessions, shared filesystem state, and work-item metadata.
`work-items/` stores Meridian-owned coordination metadata. `work/` holds active work-scoped scratch files, and `work-archive/` holds scratch for completed work items.

## `config.toml` Keys

Canonical keys accepted by `meridian config set/get/reset`:

| Key | Type | Purpose |
|---|---|---|
| `defaults.max_depth` | int | Max nested agent depth |
| `defaults.max_retries` | int | Retry attempts per run |
| `defaults.retry_backoff_seconds` | float | Retry backoff multiplier |
| `defaults.model` | str | Default model for spawn when unset |
| `timeouts.kill_grace_minutes` | float | Grace before force-kill (minutes) |
| `timeouts.guardrail_minutes` | float | Guardrail timeout (minutes) |
| `timeouts.wait_minutes` | float | Default `spawn wait` timeout (minutes) |
| `harness.claude` | str | Default model for Claude harness |
| `harness.codex` | str | Default model for Codex harness |
| `harness.opencode` | str | Default model for OpenCode harness |
| `output.show` | array[str] | Stream categories shown |
| `output.verbosity` | str\|null | `quiet\|normal\|verbose\|debug` |

Agent profiles are opt-in. When `--agent/-a` is omitted and `primary.agent` is unset, Meridian runs without a predefined profile.

Scaffolded but not exposed via `config set` shorthand keys:

- `[primary] autocompact_pct`

## Example

```toml
[defaults]
max_depth = 4
model = "gpt-5.3-codex"

[harness]
claude = "claude-opus-4-6"
codex = "gpt-5.3-codex"
opencode = "gemini-3.1-pro"

[output]
show = ["lifecycle", "error"]
verbosity = "verbose"

[primary]
autocompact_pct = 70
```

## Model Catalog Overrides

Customize aliases, harness routing, and default list visibility in `.meridian/models.toml`:

```toml
[models]
fast = "gpt-5.4"                      # pinned alias shorthand

[models.coder]                        # auto-resolve: picks latest match
provider = "openai"
include = "codex"
exclude = ["-mini", "-spark", "-max"]
description = "Optimized for code editing."

[models."gpt-5.4-mini"]              # key is model ID when no model_id field
description = "Quick and cheap for simple tasks."
pinned = true                         # always show regardless of filters

[harness_patterns]
codex = ["gpt-*", "o*", "codex*"]
opencode = ["gemini*", "opencode-*"]

[model_visibility]
exclude = ["gemini-live-*", "*-latest"]
hide_date_variants = true
hide_superseded = true
max_age_days = 120
```

Builtin aliases (`opus`, `sonnet`, `haiku`, `codex`, `gpt`, `gemini`) auto-resolve to the latest model per family from the models.dev catalog. Pin an alias to a specific version by setting it as a string value under `[models]`. Add `description` to any model entry — descriptions show as sub-lines in `meridian models list`. Set `pinned = true` to keep a model visible regardless of filters.

### Visibility Defaults

The default model list filters aggressively to show only current, relevant models:

| Setting | Default | Effect |
|---|---|---|
| `exclude` | `*-latest`, `*-deep-research`, `gemini-live-*`, `o1*`, `o3*`, `o4*` | Hide by glob pattern |
| `hide_date_variants` | `true` | Hide date-suffixed variants when base exists |
| `hide_superseded` | `true` | Hide older models when a newer model in the same lineage exists |
| `max_age_days` | `120` | Hide models older than 120 days |
| `max_input_cost` | `10.0` | Hide models costing ≥$10/M input tokens |

Aliased and pinned models always pass through all visibility filters. Use `--show-superseded` or `--all` to see hidden models.

Use `meridian models config init/show/get/set/reset` to manage this file from the CLI.

## Environment Variables

### Core

| Variable | Purpose |
|---|---|
| `MERIDIAN_REPO_ROOT` | Force repo root resolution |
| `MERIDIAN_CONFIG` | User config overlay path |
| `MERIDIAN_STATE_ROOT` | Override state root (default `.meridian`) |
| `MERIDIAN_FS_DIR` | Resolved shared filesystem path for the current repo state root |
| `MERIDIAN_WORK_ID` | Active attached work item slug, when one exists |
| `MERIDIAN_WORK_DIR` | Scratch/docs directory for the active work item, when one exists |
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
