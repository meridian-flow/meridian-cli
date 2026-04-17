# CLI Reference

Full command surface. Use `--help` on any command for flags and options.

## Spawning & Monitoring

| Command | Description |
| ------- | ----------- |
| `meridian` | Launch the primary agent session with startup context, including the installed agent catalog |
| `meridian spawn -a AGENT -p "task"` | Delegate work to a routed agent/model |
| `meridian spawn list` | See running and recent spawns |
| `meridian spawn wait ID` | Block until a spawn completes |
| `meridian spawn show ID` | Read a spawn's report and status |
| `meridian spawn log ID` | Stream raw spawn output |
| `meridian spawn --continue ID -p "more"` | Resume a prior spawn with new input |
| `meridian spawn --from ID -p "next"` | Start a new spawn inheriting prior context |
| `meridian spawn cancel ID` | Cancel a running spawn |
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
| `--desc "label"` | Human-readable label in dashboards |
| `--work SLUG` | Attach to a specific work item |
| `--approval MODE` | `default` \| `confirm` \| `auto` \| `yolo` |

## Reports & Sessions

| Command | Description |
| ------- | ----------- |
| `meridian report search "query"` | Search across all spawn reports |
| `meridian session log REF` | Read a session transcript |
| `meridian session search "query" REF` | Search session transcripts |

## Work Items

| Command | Description |
| ------- | ----------- |
| `meridian work` | Dashboard — active work items and spawns |
| `meridian work create SLUG` | Create a new work item |
| `meridian work switch SLUG` | Set active work item |
| `meridian work sessions SLUG` | List sessions attached to a work item |

## Configuration & Diagnostics

| Command | Description |
| ------- | ----------- |
| `meridian init [--link DIR]` | Initialize project config/runtime state; optional convenience link wiring via mars |
| `meridian workspace init` | Create local workspace topology file |
| `meridian config show` | Show resolved configuration |
| `meridian config set KEY VALUE` | Set a config value |
| `meridian config get KEY` | Read a config value |
| `meridian config reset KEY` | Reset a config value to default |
| `meridian models list` | Inspect the model catalog |
| `meridian models show MODEL` | Show details for a specific model |
| `meridian models config show` | Show model catalog overrides |
| `meridian doctor` | Run diagnostics and reconcile orphan state |
| `meridian serve` | Start the MCP server |

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
