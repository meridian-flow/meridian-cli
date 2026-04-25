# Troubleshooting

## `meridian` not found

Run `uv tool update-shell` and restart your shell. If using a virtual environment, activate it first.

## Harness not found

`meridian doctor` reports missing harnesses when the harness binary is not on `$PATH`.

Install the missing harness:
- Claude Code: [docs.anthropic.com](https://docs.anthropic.com/en/docs/claude-code)
- Codex CLI: [github.com/openai/codex](https://github.com/openai/codex)
- OpenCode: [opencode.ai](https://opencode.ai)

Then confirm with `meridian doctor`.

## Model routes to wrong harness

Harness routing is determined by model prefix patterns. Check what's resolved:

```bash
meridian models list      # see available models and their harnesses
meridian config show      # see harness defaults and overrides
```

To force a specific harness for a spawn, use `--harness`:

```bash
meridian spawn -m MODEL --harness claude -p "task"
```

Set a default harness for a model family in `meridian.toml`:

```toml
[harness]
claude = "claude-opus-4-6"
codex  = "gpt-5.3-codex"
```

## Spawn disconnected from earlier work

To resume a prior spawn:
```bash
meridian spawn --continue ID -p "continue from where you left off"
```

To start a new spawn with a prior spawn or chat/session as context:
```bash
meridian spawn --from REF -p "next task"
```

Use a spawn ref such as `p123` to include that spawn's report/files. Use a chat
ref such as `c123` to point at the exact session transcript and primary spawn.

To find which spawns belong to a work item:
```bash
meridian work                      # dashboard with attached spawns
meridian report search "keyword"   # search across all spawn reports
```

## Spawn shows as `finalizing`

`finalizing` is a normal, short-lived active status. It means the runner has finished its post-exit work (output drain, report extraction) and is committing the terminal state. You may briefly see it in `spawn list` or the `work` dashboard between harness exit and terminal persistence. No action needed — the spawn will move to `succeeded` or `failed` momentarily.

If a spawn stays in `finalizing` for more than a minute or two, the runner may have crashed in the finalization window. In that case `meridian doctor` will reclassify it (see below).

## Spawn shows as orphaned

Meridian classifies a spawn as orphaned when its runner process is gone and there has been no recent activity on the spawn's artifacts (heartbeat, output, stderr, or report) for 120 seconds. There are two distinct orphan errors:

- **`orphan_run`** — the spawn record was `status=running` (or `queued`) when reaped. The runner died before completing post-exit work; because output drain and report extraction happen while status is still `running`, a crash during drain also produces this error. The spawn likely produced partial or no output.
- **`orphan_finalization`** — the spawn record was `status=finalizing` when reaped, meaning the runner completed all post-exit work but crashed in the narrow window before persisting the terminal state. The spawn is likely to have a usable `report.md` on disk even though it was classified as failed.

To detect and reconcile orphaned state, run:

```bash
meridian doctor
```

After reconciliation, inspect the spawn:

```bash
meridian spawn show ID          # check status, report, and error field
```

If `report.md` exists and looks complete, the work product is likely usable even though the spawn is marked `failed`. Relaunch only if the work wasn't done.

### A spawn briefly showed orphaned but now shows `succeeded`

This is expected, not a bug. Meridian's read-path reconciler makes a best-effort assessment based on heartbeat and artifact recency. If the runner was slow (not dead) and later completed normally, its terminal status overwrites the reconciler's orphan stamp — the process that actually ran the work has final say. You can confirm by checking `meridian spawn show ID`.

## Spawn exited with code 143 or 137

The process was killed externally (SIGTERM/SIGKILL). Check `meridian spawn show ID` — if status is `succeeded`, the signal hit during cleanup and no retry is needed. Otherwise check for OOM or external kill, then retry.

## Config not taking effect

Config resolution precedence: CLI flag > ENV var > YAML profile > project config > user config > harness default.

Verify what's actually resolved for a field:
```bash
meridian config show
```

A CLI `-m MODEL` override must also drive harness selection — a profile-level harness default cannot win over a CLI model override.

## Workspace issues

`meridian doctor` surfaces workspace findings as distinct codes. Fix them by editing `workspace.local.toml` (run `meridian workspace init` to create it if missing).

### `workspace_invalid`

The workspace file is invalid. Causes: TOML syntax error, wrong type for `path` (must be a non-empty string), wrong type for `enabled` (must be a boolean), `context-roots` is not an array of tables, or the workspace file path itself points to a directory rather than a file.

Fix the TOML error in `workspace.local.toml`, then rerun `meridian doctor`.

**An invalid workspace blocks spawns.** Launches fail before contacting any harness until the file is fixed or removed.

### `workspace_unknown_key`

The file contains keys Meridian doesn't recognize. Forward-compatibility warning only — does not block launches. Safe to ignore if the key is intentional (written by a newer Meridian version). Otherwise, remove or rename the key.

### `workspace_missing_root`

An enabled root (`enabled = true` or omitted) points to a path that doesn't exist on disk. The root is skipped at launch time — missing roots don't block spawns, but they produce no projection.

Check the path in `workspace.local.toml`. Paths are resolved relative to the workspace file's location. Use absolute paths when the relative form is ambiguous.

### `workspace_unsupported_harness`

When workspace roots are declared, they cannot be projected to the Codex harness yet — Codex projection requires config generation that is not yet implemented. The spawn proceeds but Codex won't see the declared roots.

If multi-repo context is required, use Claude Code or OpenCode harnesses instead.

## Spawn artifacts

Each spawn writes artifacts to the user-level runtime directory, under `~/.meridian/projects/<uuid>/spawns/<spawn_id>/` on POSIX (or `%LOCALAPPDATA%\meridian\projects\<uuid>\spawns\<spawn_id>\` on Windows). Use `meridian spawn show ID` to read them without navigating the path directly.

| File | Contents |
| ---- | -------- |
| `report.md` | Agent's final report |
| `output.jsonl` | Raw harness output (surfaced through `meridian session log <spawn_id>`) |
| `stderr.log` | Harness stderr, warnings, errors |
| `system-prompt.md` | System instruction content as sent to the harness (Claude composed launches) |
| `starting-prompt.md` | Full user-turn content (prompt + prepended context) |
| `projection-manifest.json` | Harness ID and per-category channel routing decisions |

If a spawn directory is missing entirely, the harness crashed before artifacts stabilized — relaunch.

## Stale state accumulating in `~/.meridian/`

Over time, orphan project directories and old spawn artifacts accumulate under `~/.meridian/projects/`. Meridian runs a background health scan on app launch (every 24h) and warns on the next text-mode command if stale state is found.

To inspect what's stale:

```bash
meridian doctor --global          # scan current project + all projects
```

To clean up:

```bash
meridian doctor --prune           # prune stale spawn artifacts (current project)
meridian doctor --prune --global  # also prune orphan project dirs machine-wide
```

Pruning respects `state.retention_days` (default 30 days). Configure in `meridian.toml`:

```toml
[state]
retention_days = 30   # -1 = never prune, 0 = prune immediately
```

Or via environment variable: `MERIDIAN_STATE_RETENTION_DAYS=30`.

Active spawns are always protected — pruning never deletes state for running spawns regardless of age.
