---
name: __meridian-diagnostics
description: "Diagnostic and troubleshooting guide for meridian problems. Use when spawns fail unexpectedly, state seems corrupt, the CLI behaves strangely, or you need to run `meridian doctor`."
---

# Troubleshoot

Dormant skill — use only when something goes wrong.

## Debugging Sequence

Stop as soon as you find the cause.

1. **Check spawn status** — `meridian spawn show SPAWN_ID`. Read `status`, `error`, `report` fields.
2. **Read the conversation** — `meridian spawn log SPAWN_ID` shows the last 3 assistant messages as plain text. Use `-n 10` for more, `--offset N` to paginate backward.
3. **Inspect the session** — `meridian session log SPAWN_ID` reads the harness's native session file. Defaults to content since the last compaction (`-c 0`). Use `-c 1` for the previous segment, or `--file PATH` to read any session JSONL directly.
4. **Check stderr** — `meridian spawn show SPAWN_ID` includes `log_path`. Read `stderr.log` there for harness errors.
5. **Run doctor** — `meridian doctor` reconciles stale state and reports warnings.
6. **Inspect state files** — last resort. Read `spawns.jsonl` with `jq`.

## `meridian doctor`

Health check and auto-repair. Cleans stale session locks, reconciles orphan spawns (dead PIDs, stale output, missing directories), and warns about missing configuration.

```bash
meridian doctor
# ok: ok, runs_checked: 12, repaired: orphan_runs
```

## Common Failure Patterns

| Error | Cause | Fix |
|-------|-------|-----|
| `orphan_run` / `orphan_stale_harness` | Harness died without finalizing | Auto-recovered on next read. Relaunch. |
| `missing_spawn_dir` | Crash during launch | Relaunch. |
| `missing_wrapper_pid` / `missing_worker_pid` | Harness crashed on startup | Check `which claude`/`which codex`, install if missing. |
| Exit code 127 or 2 | Harness not on `$PATH` | Install the harness and ensure it's on `$PATH`. |
| Exit code 143 (SIGTERM) | Process killed | If status is `succeeded`, no action. If `failed`, check OOM killer (`dmesg`) or manual kill. |
| Exit code 137 (SIGKILL) | Force killed | Same as 143. |
| Timeout | Exceeded time limit | Increase timeout in config or break task into smaller steps. |
| Model errors in `stderr.log` | API rejected model | Run `meridian models list`. Check API keys and billing. |

## Spawn Artifacts

Each spawn has a directory at `.meridian/spawns/<SPAWN_ID>/`:

| File | Contents |
|------|----------|
| `stderr.log` | Harness stderr — errors, warnings, debug traces |
| `output.jsonl` | Raw harness stdout (use `spawn log` instead of reading directly) |
| `report.md` | Final report (if spawn completed far enough) |
| `prompt.md` | The prompt sent to the harness |
| `harness.pid` | PID file for the harness process |
| `heartbeat` | Touched periodically while spawn is alive |

## State Recovery

Meridian uses crash-only design: atomic writes (tmp + rename), truncation-tolerant reads, recovery IS startup. The reaper runs on every read-path command and auto-reconciles orphaned spawns.

If state looks corrupt:

1. `meridian doctor` — reconciles orphans, cleans stale locks.
2. Check `spawns.jsonl` with `jq` — look for spawns stuck in `queued`/`running` with no live process.
3. Truncated JSONL files self-heal — malformed trailing lines are skipped.

Never manually edit `spawns.jsonl` or `sessions.jsonl`.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `MERIDIAN_STATE_ROOT` | Override `.meridian/` location |
| `MERIDIAN_DEPTH` | Nesting depth (>0 = inside a spawn) |
| `MERIDIAN_FS_DIR` | Shared filesystem directory |
| `MERIDIAN_WORK_DIR` | Work item scratch directory |
