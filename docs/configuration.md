# Configuration

Meridian works without config files, but you can override defaults in project
`meridian.toml` and user `~/.meridian/config.toml`.

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

Meridian splits state across two roots: repo-tracked files that belong in version control, and per-machine runtime state that does not.

### Repo-tracked (`.meridian/`)

```text
<repo-root>/
  meridian.toml              # project config
  .agents/
    agents/
    skills/
  workspace.local.toml       # local-only, gitignored via .git/info/exclude
  .meridian/
    .gitignore               # committed — controls what else is tracked
    models.toml              # committed — model catalog overrides
    fs/                      # committed — shared filesystem mirror
    work/                    # committed — active work-item scratch dirs
    work-archive/            # committed — scratch for completed work items
    id                       # gitignored — project UUID (created on first write)
    .migrations.json         # gitignored — migration state
```

Read-only commands (`meridian spawn list`, `meridian config show`, `meridian doctor`, etc.) do not create `.meridian/id` or any runtime state.

### User runtime (`~/.meridian/projects/<uuid>/`)

High-churn runtime state lives outside the repo, keyed by project UUID so the repo can be moved or renamed without losing history.

```text
~/.meridian/                       # Unix/macOS default (see MERIDIAN_HOME)
%LOCALAPPDATA%\meridian\           # Windows default
  projects/
    <uuid>/                        # one dir per project
      spawns.jsonl
      sessions.jsonl
      session-id-counter
      sessions/
      spawns/
        <spawn-id>/
      artifacts/
      cache/
      config.toml
      .migrations.json
```

The UUID is stored in `.meridian/id` (gitignored). Because state is keyed by UUID rather than path, renaming or moving the repo does not orphan runtime state.

`work/` and `work-archive/` stay repo-side so work-item scratch files are visible to all collaborators and survive across machines.

## `meridian.toml` Keys

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

## Workspace

`workspace.local.toml` injects sibling-repo context into harness launches. Local-only — `workspace init` covers it with `.git/info/exclude` rather than committing a `.gitignore` entry.

### File Location

`<state-root-parent>/workspace.local.toml` — defaults to the repo root. Follows `MERIDIAN_STATE_ROOT` if overridden.

### Schema

Only `[[context-roots]]` entries are recognized.

| Key | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `path` | str | yes | — | Path to sibling repo; absolute or relative to the workspace file |
| `enabled` | bool | no | `true` | Set to `false` to disable without removing the entry |

Unknown keys at any level produce `workspace_unknown_key` doctor findings but do not block launches.

### Example

```toml
[[context-roots]]
path = "../sibling-api"

[[context-roots]]
path = "/absolute/path/to/another-repo"
enabled = false   # disabled — not projected
```

### Projection per Harness

Each enabled, existing root is projected at launch time. Roots that don't exist on disk are skipped (reported by `doctor`):

| Harness | Mechanism |
|---|---|
| Claude Code | `--add-dir <path>` flag per root |
| OpenCode | `OPENCODE_CONFIG_CONTENT` env with `permission.external_directory` |
| Codex | Not supported (requires config generation — deferred) |

### `config show` Workspace Output

```
workspace.status = present
workspace.path = /your/repo/workspace.local.toml
workspace.roots.count = 2
workspace.roots.enabled = 1
workspace.roots.missing = 0
workspace.applicability.claude = active
workspace.applicability.codex = unsupported:requires_config_generation
workspace.applicability.opencode = active
```

Status values: `none` (no file), `present` (parsed OK), `invalid` (parse or schema error).
Workspace findings, when present, render as separate `warning:` lines.

### Setup

```bash
meridian workspace init   # creates workspace.local.toml, adds .git/info/exclude coverage
```

Idempotent — safe to rerun on an existing file.

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
| `MERIDIAN_HOME` | Override user state root (default `~/.meridian/` on Unix/macOS, `%LOCALAPPDATA%\meridian\` on Windows) |
| `MERIDIAN_STATE_ROOT` | Override the runtime state root. Absolute path = use as-is; relative path = resolve relative to repo root. Repo-owned paths (`fs/`, `work/`, `work-archive/`) always stay in `.meridian/` regardless of this setting. |
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
