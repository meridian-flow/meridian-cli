# Hooks

Hooks let you run commands or builtins automatically when Meridian events fire — syncing a remote repo, running checks after a spawn finishes, or any custom script you want wired to the agent lifecycle.

## Commands

| Command | Description |
| ------- | ----------- |
| `meridian hooks list` | Show all registered hooks and their resolved configuration |
| `meridian hooks check` | Validate hook config and exit non-zero on errors |
| `meridian hooks run NAME` | Execute a hook manually, bypassing interval throttling |
| `meridian hooks run NAME --event EVENT` | Execute with a specific event context |

```bash
# See all hooks, including builtins and per-source registration
meridian hooks list

# Validate config before committing changes
meridian hooks check

# Manually trigger git-autosync
meridian hooks run git-autosync

# Trigger with a specific event context
meridian hooks run git-autosync --event work.done
```

`hooks run` bypasses interval throttling. Use it to test hooks or force a sync outside the normal lifecycle.

## Events

| Event | Class | Fires when |
| ----- | ----- | ---------- |
| `spawn.created` | observe | A spawn is registered in the database |
| `spawn.running` | observe | A spawn's harness process starts |
| `spawn.start` | observe | Alias for `spawn.running` |
| `spawn.finalized` | post | A spawn reaches a terminal state (`succeeded`, `failed`, or `cancelled`) |
| `work.start` | observe | A work item is switched to (becomes active) |
| `work.started` | observe | Alias for `work.start` |
| `work.done` | post | A work item is completed |

Event class affects default timeout and failure policy: `observe` events default to 30s / `warn`; `post` events default to 60s / `warn`.

A single hook row can register for multiple events. When a builtin supplies default events and no `event` field is set, one hook registration is created per default event. Setting `event` explicitly overrides this and registers for only that one event.

## Configuring Hooks

Hooks live in any Meridian config file. Precedence is: `builtin < context < user < project < local`.

```toml
# meridian.toml (project) or ~/.meridian/config.toml (user)

[[hooks]]
builtin = "git-autosync"
remote  = "git@github.com:team/docs.git"

[[hooks]]
name    = "run-tests"
command = "make test"
event   = "spawn.finalized"
```

### Hook Schema

| Field | Type | Required | Default | Purpose |
| ----- | ---- | -------- | ------- | ------- |
| `name` | str | yes (unless `builtin`) | builtin name | Unique identifier; used by `hooks run NAME` |
| `builtin` | str | one of `builtin`/`command` | — | Use a builtin hook |
| `command` | str | one of `builtin`/`command` | — | Shell command to run |
| `event` | str | yes (unless builtin supplies defaults) | builtin default | Event that triggers the hook |
| `remote` | str | required by `git-autosync` | — | Git remote URL for hooks that operate on a remote repo |
| `enabled` | bool | no | `true` | Set to `false` to disable without removing |
| `priority` | int | no | `0` | Lower values run first |
| `failure_policy` | str | no | builtin default | `fail` \| `warn` \| `ignore` |
| `timeout_secs` | int | no | builtin default | Max seconds before hook is killed |
| `interval` | str | no | builtin default | Minimum time between runs, e.g. `30s`, `5m`, `2h` |
| `require_serial` | bool | no | `false` | Block concurrent hook executions |
| `when.status` | array[str] | no | — | Only fire when spawn exits with one of these statuses |
| `when.agent` | str | no | — | Only fire for this agent profile |
| `exclude` | array[str] | no | — | Skip for these agent profiles |

`command` and `builtin` are mutually exclusive.

### `repo` → `remote` Migration

`repo` is accepted as a deprecated alias for `remote`. Meridian emits a warning when it sees `repo`. Update your config:

```toml
# Before (deprecated)
[[hooks]]
builtin = "git-autosync"
repo = "git@github.com:team/docs.git"

# After
[[hooks]]
builtin = "git-autosync"
remote = "git@github.com:team/docs.git"
```

## Builtin: `git-autosync`

`git-autosync` keeps a remote Git repo in sync with local changes. On each trigger it:

1. Stages and commits any uncommitted changes in the target repo
2. Fetches upstream
3. Rebases when behind remote
4. Pushes when ahead or after a local commit

**Required:** `remote` — the Git remote URL of the repo to sync.

**Default events:** `spawn.start`, `spawn.finalized`, `work.started`, `work.done`

```toml
[[hooks]]
builtin = "git-autosync"
remote  = "git@github.com:team/notes.git"
```

To register only for specific events, set `event` explicitly:

```toml
# Only sync when a work item completes
[[hooks]]
builtin = "git-autosync"
remote  = "git@github.com:team/notes.git"
event   = "work.done"
```

To run manually at any time:

```bash
meridian hooks run git-autosync --event work.done
```

## MCP

`hooks.resolve` is exposed as an MCP tool (`hooks_resolve`). `hooks list`, `hooks check`, and `hooks run` are CLI-only.

See [mcp-tools.md](mcp-tools.md) for the full MCP tool listing.
