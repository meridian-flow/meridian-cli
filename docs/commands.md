# CLI Reference

Full command surface. Use `--help` on any command for flags and options.

## Spawning & Monitoring

| Command | Description |
| ------- | ----------- |
| `meridian` | Launch the primary agent session with startup context, including the installed agent catalog |
| `meridian spawn -a AGENT -p "task"` | Delegate work to a routed agent/model |
| `meridian spawn list` | See running and recent spawns |
| `meridian spawn list --primary` | Show only primary spawns (top-level sessions) |
| `meridian spawn wait ID` | Block until a spawn completes |
| `meridian spawn show ID` | Read a spawn's report and status |
| `meridian spawn --continue ID -p "more"` | Resume a prior spawn with new input |
| `meridian spawn --from REF -p "next"` | Start a new spawn with prior spawn or chat/session context |
| `meridian spawn cancel ID` | Cancel a running spawn |
| `meridian spawn inject ID --message "text"` | Inject a message into a running streaming spawn |
| `meridian spawn stats` | Aggregate spawn statistics |
| `meridian spawn children ID` | List direct child spawns |
| `meridian spawn files ID` | List files changed by a spawn |

Common `spawn` flags:

| Flag | Description |
| ---- | ----------- |
| `-a AGENT` | Agent profile to use |
| `-m MODEL` | Model override |
| `-p "prompt"` | Inline prompt |
| `--prompt-file PATH` | Read prompt from file |
| `-f FILE` | Attach context file (repeatable) |
| `--from REF` | Attach prior context from a spawn ref (`p123`) or chat/session ref (`c123`) |
| `--desc "label"` | Human-readable label in dashboards |
| `--work SLUG` | Attach to a specific work item |
| `--primary` | `spawn list` only: include only `kind=primary` spawns |
| `--approval MODE` | `default` \| `confirm` \| `auto` \| `yolo` |

`spawn show` includes primary-session metadata when available from `primary_meta.json`:
`kind`, `activity`, `managed_backend`, `backend_pid`, `tui_pid`, `backend_port`,
and `harness_session_id`.

For managed Codex primary startup behavior, see [codex-tui-passthrough.md](codex-tui-passthrough.md).

## Reports & Sessions

| Command | Description |
| ------- | ----------- |
| `meridian spawn report show ID` | Show one spawn's report |
| `meridian spawn report search "query"` | Search across all spawn reports |
| `meridian session log REF` | Read conversation/progress logs for a chat, spawn, or harness session |
| `meridian session search "query" REF` | Search session transcripts |

## Work Items

| Command | Description |
| ------- | ----------- |
| `meridian work` | Dashboard — active work items and spawns |
| `meridian work start LABEL` | Create a work item if missing, or switch to it |
| `meridian work list` | List all work items |
| `meridian work show SLUG` | Show one work item, its directory, and attached spawns |
| `meridian work switch SLUG` | Set active work item |
| `meridian work done SLUG` | Mark a work item done and archive its scratch directory |
| `meridian work sessions SLUG` | List sessions attached to a work item |

## Hooks

| Command | Description |
| ------- | ----------- |
| `meridian hooks list` | Show all registered hooks |
| `meridian hooks check` | Validate hook configuration |
| `meridian hooks run NAME` | Execute a hook manually, bypassing interval throttling |
| `meridian hooks run NAME --event EVENT` | Execute with a specific event context |

See [hooks.md](hooks.md) for event names, builtin hooks, and hook configuration schema.

## Context

| Command | Description |
| ------- | ----------- |
| `meridian context` | Show all resolved context paths |
| `meridian context work` | Print the absolute path for the `work` context |
| `meridian context kb` | Print the absolute path for the `kb` context |
| `meridian context work.archive` | Print the absolute path for the `work.archive` context |
| `meridian context --verbose` | Show source, path, and resolved details for each context |

```bash
meridian context           # show all resolved context paths
meridian context work      # print just the work path
meridian context --verbose # show source and resolution details
```

Context paths can be backed by a local directory (default) or a remote Git repo (cloned and resolved at runtime). Configure in `meridian.toml`:

```toml
[context.work]
source = "git"
remote = "git@github.com:team/docs.git"
path   = "project/work"
archive = "project/archive/work"

[context.kb]
source = "git"
remote = "git@github.com:team/kb.git"
path   = "knowledge"
```

See [configuration.md](configuration.md#context) for the full schema.

## Extensions

| Command | Description |
| ------- | ----------- |
| `meridian ext list` | List registered extensions grouped by namespace |
| `meridian ext show EXT_ID` | Show commands in one extension |
| `meridian ext commands` | List all extension commands; `--json` for stable agent output |
| `meridian ext run FQID` | Invoke an extension command via app server |

`FQID` is `extension_id.command_id`, e.g. `meridian.sessions.getSpawnStats`.

`ext list`, `ext show`, and `ext commands` work with no app server running. `ext run` runs in-process for commands with `requires_app_server: false`; commands with `requires_app_server: true` need a running app server (`meridian app`).

Common `ext run` flags:

| Flag | Description |
| ---- | ----------- |
| `--args JSON` | JSON object of args for the command (default `{}`) |
| `--work-id ID` | Work item context |
| `--spawn-id ID` | Spawn context |
| `--request-id ID` | Tracing request ID |
| `--json` | Output as JSON (alias for `--format json`) |

Exit codes for `ext run`: `2` = no server, `3` = stale endpoint, `4` = wrong project, `5` = unreachable, `7` = invalid `--args`.

See [extensions.md](extensions.md) for HTTP API and MCP tool details.

## Configuration & Diagnostics

| Command | Description |
| ------- | ----------- |
| `meridian init [--link DIR]` | Initialize project config/runtime state; optional convenience link wiring via mars |
| `meridian workspace init` | Create local workspace topology file |
| `meridian config show` | Show resolved configuration |
| `meridian config set KEY VALUE` | Set a config value |
| `meridian config get KEY` | Read a config value |
| `meridian config reset KEY` | Reset a config value to default |
| `meridian mars models list` | Inspect the model catalog |
| `meridian models refresh` | Force-refresh the models.dev cache |
| `meridian doctor` | Run diagnostics and reconcile orphan state |
| `meridian serve` | Start the MCP server |
| `meridian app` | Start the app web UI server (HTTP extension API endpoint) |

## Package Management (mars)

| Command | Description |
| ------- | ----------- |
| `meridian mars init [--link DIR]` | Initialize mars project (`mars.toml`) and optionally create the initial link target in the same command |
| `meridian mars add SOURCE` | Add an agent/skill package source |
| `meridian mars sync` | Resolve and install packages into `.agents/` |
| `meridian mars link DIR` | Symlink `.agents/` into a tool directory |
| `meridian mars list` | Show installed agents and skills |
| `meridian mars upgrade` | Fetch latest versions and sync |
| `meridian mars doctor` | Check for drift and integrity issues |

`meridian init --link DIR` is the top-level convenience path:
- without `mars.toml`, it shells through `meridian mars init --link DIR`
- with `mars.toml`, it shells through `meridian mars link DIR`

## Spawn Statuses

| Status | Meaning |
| ------ | ------- |
| `queued` | Registered but harness not yet started |
| `running` | Harness process is active |
| `finalizing` | All post-exit work is done; runner is committing the terminal state — no new work will happen, but the spawn is not yet terminal |
| `succeeded` | Completed successfully |
| `failed` | Completed with an error |
| `cancelled` | Cancelled before or during execution |

`queued`, `running`, and `finalizing` are active (in-flight) statuses. They all count toward active spawn counts in `spawn list` and the `work` dashboard. `finalizing` is typically brief — a few seconds at most — but is visible between harness exit and final persistence.

## Spawn References

Several commands accept symbolic spawn references in addition to literal IDs:

| Reference | Resolves to |
| --------- | ----------- |
| `@latest` | Most recently created spawn |
| `@last-failed` | Most recent spawn with status `failed` |
| `@last-completed` | Most recent spawn with status `succeeded` |
