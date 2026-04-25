# Configuration

Meridian works without config files, but you can override defaults in:

- `~/.meridian/config.toml` (user defaults)
- `meridian.toml` (project defaults)
- `meridian.local.toml` (local personal overrides, not committed)

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
  meridian.local.toml        # local personal overrides (gitignored)
  .agents/
    agents/
    skills/
  workspace.local.toml       # local-only, gitignored via .git/info/exclude
  .meridian/
    .gitignore               # committed — controls what else is tracked
    id                       # committed — project UUID (stable across renames)
    kb/                      # committed — knowledge base directory
    work/                    # committed — active work-item scratch dirs
    archive/work/            # committed — scratch for completed work items
```

Read-only commands (`meridian spawn list`, `meridian config show`, etc.) do not create `.meridian/id` or any runtime state. `meridian doctor` skips bootstrap at startup but calls `ensure_runtime_state_bootstrap_sync` internally, so it **does** create the UUID and runtime dir when run.

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
      .migrations.json
```

The UUID is stored in `.meridian/id` (gitignored). Because state is keyed by UUID rather than path, renaming or moving the repo does not orphan runtime state.

`work/` and `work-archive/` stay repo-side so work-item scratch files are visible to all collaborators and survive across machines.

## `meridian.toml` Keys

Canonical keys accepted by `meridian config set/get/reset`:

| Key | Type | Purpose |
|---|---|---|
| `defaults.max_depth` | int | Max zero-based delegated spawn depth |
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
| `state.retention_days` | int | TTL for stale state pruning (`-1` = never, `0` = immediate, default `30`) |

Agent profiles are opt-in. When `--agent/-a` is omitted and `primary.agent` is unset, Meridian runs without a predefined profile.

Scaffolded but not exposed via `config set` shorthand keys:

- `[primary] autocompact_pct`

## Config Precedence

For config-file resolution, Meridian layers sources in this order:

1. `~/.meridian/config.toml` (lowest)
2. `meridian.toml`
3. `meridian.local.toml` (highest file precedence)

Environment variables still override all file values.

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

[state]
retention_days = 30   # -1 = never prune, 0 = prune immediately
```

## Workspace

`workspace.local.toml` injects sibling-repo context into harness launches. Local-only — `workspace init` covers it with `.git/info/exclude` rather than committing a `.gitignore` entry.

### File Location

`<state-root-parent>/workspace.local.toml` — defaults to the repo root. Follows `MERIDIAN_RUNTIME_DIR` if overridden.

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

## Hooks

Hooks are configured in any Meridian config file. Multiple sources layer in precedence order: `builtin < context < user < project < local`.

```toml
# meridian.toml or ~/.meridian/config.toml

[[hooks]]
builtin = "git-autosync"
remote  = "git@github.com:team/docs.git"

[[hooks]]
name    = "lint"
command = "make lint"
event   = "spawn.finalized"
failure_policy = "warn"
```

See [hooks.md](hooks.md) for the full hook schema, event names, and builtin reference.

### `repo` → `remote`

`repo` is a deprecated alias for `remote`. Meridian accepts it with a warning. Replace `repo` with `remote` in your config:

```toml
# deprecated
[[hooks]]
builtin = "git-autosync"
repo = "git@github.com:team/docs.git"

# correct
[[hooks]]
builtin = "git-autosync"
remote = "git@github.com:team/docs.git"
```

## Context

Context paths point Meridian at directories for active work, knowledge bases, and work archives. They can be backed by a local path (default) or a remote Git repo that Meridian clones and resolves at runtime.

Configure in `meridian.toml` or `~/.meridian/config.toml`:

```toml
[context.work]
source  = "git"
remote  = "git@github.com:team/docs.git"
path    = "project/work"
archive = "project/archive/work"

[context.kb]
source = "git"
remote = "git@github.com:team/kb.git"
path   = "knowledge"

[context.strategy]
source = "git"
remote = "git@github.com:team/docs.git"
path   = "project/strategy"
```

### Schema

#### `[context.work]`

| Key | Type | Default | Purpose |
| --- | ---- | ------- | ------- |
| `source` | str | `"local"` | `"local"` or `"git"` |
| `remote` | str | — | Git remote URL (required when `source = "git"`) |
| `path` | str | `".meridian/work"` | Path to the work directory, relative to repo or clone root |
| `archive` | str | `".meridian/archive/work"` | Path to the work archive directory |

#### `[context.kb]`

| Key | Type | Default | Purpose |
| --- | ---- | ------- | ------- |
| `source` | str | `"local"` | `"local"` or `"git"` |
| `remote` | str | — | Git remote URL (required when `source = "git"`) |
| `path` | str | `".meridian/kb"` | Path to the knowledge base directory |

#### `[context.NAME]`

Arbitrary named context tables are allowed alongside the built-in `work` and `kb` contexts. They support:

| Key | Type | Default | Purpose |
| --- | ---- | ------- | ------- |
| `source` | str | `"local"` | `"local"` or `"git"` |
| `remote` | str | — | Git remote URL (required when `source = "git"`) |
| `path` | str | — | Path to the context directory, relative to repo or clone root |

When `source = "git"`, Meridian clones the remote into a local cache and resolves paths relative to the clone root. Use `meridian context` to inspect the resolved paths.

## Model Catalog

`meridian mars models list` shows the current model catalog. Use `--all` to include hidden/superseded models, or `--show-superseded` to see older lineage variants.

Builtin aliases (`opus`, `sonnet`, `haiku`, `codex`, `gpt`, `gemini`) auto-resolve to the latest model per family. The default list filters aggressively:

- Date-suffixed variants hidden when base model exists
- Superseded models hidden when a newer lineage successor exists
- Models older than ~120 days hidden by default
- High-cost models (≥$10/M input tokens) hidden by default

Use `meridian models refresh` to force a cache refresh from the models.dev catalog.

## Environment Variables

### Core

| Variable | Purpose |
|---|---|
| `MERIDIAN_PROJECT_DIR` | Force repo root resolution |
| `MERIDIAN_CONFIG` | User config overlay path |
| `MERIDIAN_HOME` | Override user state root (default `~/.meridian/` on Unix/macOS, `%LOCALAPPDATA%\meridian\` on Windows) |
| `MERIDIAN_RUNTIME_DIR` | Override the runtime state root. Absolute path = use as-is; relative path = resolve relative to repo root. Repo-owned paths (`fs/`, `work/`, `work-archive/`) always stay in `.meridian/` regardless of this setting. |
| `MERIDIAN_FS_DIR` | Resolved shared filesystem path for the current repo state root |
| `MERIDIAN_WORK_ID` | Active attached work item slug, when one exists |
| `MERIDIAN_WORK_DIR` | Scratch/docs directory for the active work item, when one exists |
| `MERIDIAN_SPAWN_ID` | Current run/spawn ID for primary and delegated execution |
| `MERIDIAN_CHAT_ID` | Top-level chat/session id inherited across the spawn tree |
| `MERIDIAN_DEPTH` | Zero-based delegation depth (`0` = primary/root, `1` = first delegated spawn) |
| `MERIDIAN_MAX_DEPTH` | Max zero-based delegated spawn depth override |
| `MERIDIAN_PARENT_SPAWN_ID` | Immediate parent spawn ID for nested execution |
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
- `MERIDIAN_STATE_RETENTION_DAYS`

### Guardrails and Secrets

| Variable | Purpose |
|---|---|
| `MERIDIAN_GUARDRAIL_RUN_ID` | Spawn id passed to guardrail scripts |
| `MERIDIAN_GUARDRAIL_OUTPUT_LOG` | Path to `output.jsonl` |
| `MERIDIAN_GUARDRAIL_REPORT_PATH` | Path to `report.md` when a report exists |
| `MERIDIAN_SECRET_<KEY>` | Secret injection/redaction channel |

## Permission Naming

Use `workspace-write` (not `space-write`) as the writable middle tier.
