# hooks/ — Hook System and Git-Autosync

## What This Is

The hook system fires user-defined scripts or built-in handlers at lifecycle
events (spawn created/running/finalized, work started/done). Config is layered
across builtin < context < user < project < local sources. The git-autosync
builtin is the primary built-in hook — it keeps a git-backed remote in sync with
local changes.

## Event Taxonomy

```python
HookEventName = Literal[
    "spawn.created",    # spawn row written
    "spawn.running",    # harness process started
    "spawn.start",      # alias for spawn.running (used by builtins)
    "spawn.finalized",  # spawn reached terminal state
    "work.start",       # work item opened/switched to
    "work.started",     # alias
    "work.done",        # work item marked done
]
```

## Config Shape

Hooks are configured in TOML files under `[[hooks]]` arrays. Each row produces
one `Hook` per event (multi-event expansion for builtins with `default_events`).

```toml
# Builtin hook (git-autosync)
[[hooks]]
builtin = "git-autosync"
remote  = "git@github.com:org/meridian-context.git"
# event omitted → expands to all 4 default events

# Custom shell hook
[[hooks]]
name    = "notify"
event   = "spawn.finalized"
command = "scripts/notify.sh"
failure_policy = "warn"   # "fail" | "warn" | "ignore"
```

### Hook fields

| Field            | Type                | Notes |
|------------------|---------------------|-------|
| `builtin`        | str \| null         | Name of a registered builtin. Mutually exclusive with `command`. |
| `command`        | str \| null         | Shell command string. Mutually exclusive with `builtin`. |
| `name`           | str                 | Defaults to `builtin` name for builtins. Required for command hooks. |
| `event`          | HookEventName \| null | If omitted, uses builtin's `default_events`. |
| `remote`         | str \| null         | Git remote URL (primary field; see deprecation note below). |
| `repo`           | str \| null         | **Deprecated alias** for `remote`. Emits `DeprecationWarning`. |
| `enabled`        | bool                | Default `true`. |
| `priority`       | int                 | Default `0`. Lower runs first. |
| `require_serial` | bool                | Default `false`. If true, hook waits for previous hooks. |
| `exclude`        | list[str]           | Glob patterns for files to exclude (git-autosync only). |
| `failure_policy` | str \| null         | `"fail"` \| `"warn"` \| `"ignore"`. |
| `timeout_secs`   | int \| null         | Per-hook timeout. |
| `interval`       | str \| null         | Throttle interval: `"30s"`, `"5m"`, etc. |
| `options`        | table               | Builtin-specific options dict. |
| `when.status`    | list[SpawnStatus]   | Filter by spawn outcome (finalized hooks only). |
| `when.agent`     | str \| null         | Filter by agent profile name. |

### `repo` → `remote` rename

The `remote` field replaced `repo` for precision. The loader in
`src/meridian/lib/hooks/config.py` accepts `repo` as a deprecated alias:
reads it, emits `DeprecationWarning`, then copies the value to `remote`.
The resolved `Hook` dataclass carries `remote` as the canonical field.

## Config Layering

Precedence (lower wins / overrides higher):

```
builtin < context < user < project < local
```

Source files:
- `user` — `~/.meridian/config.toml` (or `$MERIDIAN_HOME/config.toml`)
- `project` — `meridian.toml` at repo root
- `local` — `meridian.local.toml` at repo root (gitignored; machine-local overrides)

Override semantics: a later-source hook with the same `(name, event)` key
replaces the earlier one. Builtins with `auto_registered=True` are superseded
by any explicit config row for the same builtin name.

## Hook Data Flow

```
event fires
  → dispatch.py:dispatch_event()
  → runner.py:run_hooks()
  → for each Hook matching event:
      - interval check (skip if within interval)
      - when.status / when.agent filter
      - command hook: subprocess with MERIDIAN_* env vars
      - builtin hook: builtin_registry lookup → execute(context, config)
      → HookResult
```

Context passed to hooks:

- `HookContext` fields: `event_name`, `event_id`, `timestamp`, `project_root`,
  `runtime_root`, `spawn_id`, `spawn_status`, `spawn_agent`, `spawn_model`,
  `spawn_duration_secs`, `spawn_cost_usd`, `spawn_error`, `work_id`, `work_dir`
- Command hooks receive context as `MERIDIAN_*` env vars (via `HookContext.to_env()`)
  and as JSON on stdin (via `HookContext.to_json()`)

## Module Layout

```
lib/hooks/
  config.py           load_hooks_config() — TOML loading, layering, normalization
  types.py            Hook, HookContext, HookResult, HookEventName, HookWhen (internal)
  dispatch.py         dispatch_event() entry point
  runner.py           run_hooks() — interval, filter, execute loop
  interval.py         Interval throttle state
  registry.py         HookRegistry — runtime registration
  builtin_registry.py BUILTIN_HOOK_REGISTRY — maps name → builtin class
  builtin/
    base.py           BuiltinHook protocol
    git_autosync.py   GitAutosync implementation → GIT_AUTOSYNC singleton
    __init__.py
```

## Git-Autosync Builtin

**Builtin name:** `git-autosync`

**Purpose:** Keep a git-backed context repository synced across agents. On each
lifecycle event, it stages all changes, commits if needed, fetches, rebases if
behind, and pushes local commits.

### Default events

```python
("spawn.start", "spawn.finalized", "work.start", "work.done")
```

All four fire by default when no `event` is specified in config. To restrict to
a single event, specify `event = "spawn.finalized"`.

### Remote resolution

The hook resolves the remote URL from two places (in priority order):

1. `options.remote` — plugin-style config inside the `[options]` table
2. `config.remote` — top-level `remote` field on the Hook dataclass

`config.repo` (deprecated) is mapped to `config.remote` by the config loader
before the hook ever sees it.

### Clone management

- Clone location: `~/.meridian/git/<slug>/` where slug is computed by
  `plugin_api.generate_repo_slug(remote_url)`
- Per-clone file lock: `~/.meridian/locks/clone-<hash>.lock` — ensures only
  one sync runs at a time per clone target, even across concurrent agents
- Lock timeout: 60 seconds; lock timeout results in `skipped/lock_timeout`
- Auto-clone on first run: if clone path does not exist, runs `git clone`
- Remote mismatch: if clone exists but `origin` URL differs after normalization,
  logs and skips (`skipped/clone_failed`)

### Sync workflow (commit-first)

```
1. git add -A
2. Apply exclude patterns (git reset -- <excluded>)
3. git diff --cached --quiet  → check if anything staged
4. If staged: git commit -m "autosync: <ISO timestamp>"   ← commit BEFORE pull
5. git fetch origin
6. git rev-list --left-right --count HEAD...@{upstream}  → ahead/behind
7. If behind: git pull --rebase
     - Rebase conflict: detect via repo state (rebase-merge / rebase-apply dirs)
     - On conflict: git rebase --abort; return skipped/rebase_conflict
     - Local commit is preserved; no data loss
8. If ahead (or just committed): git push
```

**Why commit-first?** Rebasing with uncommitted local changes can cause conflicts
or lose edits when the stash interacts with the rebase. Committing first ensures
local edits are a real commit before any remote history is integrated. The
alternative (stash → pull → pop) is error-prone and interacts badly with merge
conflicts in the stash.

### Exclude patterns

`exclude` is a list of gitignore-style glob patterns. Files matching any
pattern are unstaged (`git reset --`) before the commit step.

- Directory patterns (`dir/`) match the prefix `dir/` or `dir` itself
- Simple patterns (no `/`) are matched against both the full relative path and
  the basename
- Cross-platform: paths are normalized to POSIX before matching

### Failure modes

All errors result in `skipped` (not `failure`) with a `skip_reason` string.
This is intentional: sync failures are non-fatal — the agent session continues.

| `skip_reason`         | Cause |
|-----------------------|-------|
| `missing_repo`        | No `remote` configured |
| `lock_timeout`        | Could not acquire clone lock within 60s |
| `clone_failed`        | `git clone` failed or remote mismatch |
| `add_failed`          | `git add -A` non-zero |
| `exclude_scan_failed` | `git diff --cached --name-only` failed |
| `exclude_reset_failed`| `git reset -- <paths>` failed |
| `staged_check_failed` | `git diff --cached --quiet` failed unexpectedly |
| `commit_failed`       | `git commit` failed (non-"nothing to commit" error) |
| `fetch_failed`        | `git fetch origin` failed |
| `pull_failed`         | `git pull --rebase` failed (non-rebase-conflict) |
| `rebase_conflict`     | Pull resulted in conflict; abort succeeded |
| `rebase_abort_failed` | Pull resulted in conflict AND abort failed (logged as error) |
| `push_failed`         | `git push` failed |
| `nothing_to_sync`     | No staged changes and not behind upstream |
| `git_runtime_error`   | OSError or SubprocessError during sync |

### Example config

```toml
[[hooks]]
builtin = "git-autosync"
remote  = "git@github.com:org/meridian-context.git"
exclude = ["*.log", "tmp/"]

# Restrict to finalized events only:
[[hooks]]
builtin = "git-autosync"
remote  = "git@github.com:org/meridian-context.git"
event   = "spawn.finalized"
```

## Implementation Constraint: Plugin API Only

`git_autosync.py` imports **only** from `meridian.plugin_api` — zero imports
from `meridian.lib.*`. This enforces the plugin boundary: builtins must be
writable as external plugins using only the stable API surface. Violating this
would couple builtins to internal implementation details.

## Related Docs

- `plugin-api/overview.md` — plugin API surface used by git-autosync
- `context/overview.md` — git-backed context stores that git-autosync keeps synced
