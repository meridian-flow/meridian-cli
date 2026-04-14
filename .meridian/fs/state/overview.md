# State Domain Overview

## What It Is

All Meridian state lives as files under `.meridian/`. No database, no service, no hidden in-memory state. The design guarantees that `cat spawns.jsonl | jq` is sufficient to understand the system state.

Source: `src/meridian/lib/state/`

## Directory Layout

```
.meridian/
  spawns.jsonl         # all spawn events (start/update/exited/finalize), append-only
  spawns.jsonl.flock   # fcntl lock file for spawns.jsonl writes
  sessions.jsonl       # all session events (start/stop/update), append-only
  sessions.jsonl.flock # fcntl lock file for sessions.jsonl writes
  session-id-counter   # monotonic counter for allocating c1, c2, ... IDs
  sessions/            # per-session lock files and lease files
    <chat_id>.lock
    <chat_id>.lease.json
  spawns/              # per-spawn artifact directories
    <spawn_id>/
      prompt.md
      report.md
      output.jsonl
      stderr.log
      params.json
      tokens.json
      heartbeat        # touched every 30s by runner; reaper liveness signal
      ...
  work-items/          # per-work-item metadata JSON files
    <work_id>.json
    work-items.rename.intent.json  # crash-safe rename intent (transient)
  work/                # per-work-item scratch directories (active)
    <work_id>/
  work-archive/        # per-work-item scratch directories (done/archived)
    <work_id>/
  artifacts/           # artifact blob store for spawn outputs (LocalStore)
  cache/
    models.json        # model list cache (24h TTL)
  config.toml          # project config overrides
  .gitignore           # seeded and maintained non-destructively
```

Override root via `MERIDIAN_STATE_ROOT` env var.

## Storage Patterns

**JSONL event stores** (spawns, sessions): append-only, crash-tolerant. Reads skip malformed lines (`json.JSONDecodeError` → skip). Writes go through `append_event()` under `fcntl.flock`. State is derived by replaying events from the beginning.

**Per-file mutable JSON** (work items): one `<slug>.json` per item. Atomic overwrites via `tmp + os.replace()`. Better for mutable records correlated with a directory that moves on rename.

**Artifact directories** (spawns): one directory per spawn under `.meridian/spawns/<id>/`. Contains durable artifacts (stdout capture, stderr, report, params, tokens) plus the `heartbeat` coordination file touched every 30s by the runner. No PID files; PID and status transitions live in the event stream. The `heartbeat` file is the exception — it is a live coordination artifact read by the reaper for liveness.

## Crash Tolerance

Crash-only design: every write path is designed to be safely restartable.
- JSONL appends: truncated lines are skipped on read. Missing lines don't corrupt earlier lines.
- Work item renames: a `work-items.rename.intent.json` file is written before any renames begin. On startup/reconciliation, any leftover intent is replayed to completion.
- Atomic writes: any file that needs to be replaced goes through `tmp + os.replace()` (via `atomic_write_text()` in `state/atomic.py`).
- Spawn reconciliation: active spawns are auto-finalized on every read path (list, show, wait, dashboard). The reaper skips nested invocations (`MERIDIAN_DEPTH > 0`), checks heartbeat file recency as the primary liveness signal, and consults `runner_pid` psutil liveness for non-`finalizing` rows. No separate GC command. See `state/spawns.md` for full reaper logic.

## Locking

- JSONL stores: `fcntl.flock(LOCK_EX)` on the `.flock` sidecar file. Reentrant within a thread (tracked via thread-local depth counter).
- Session locks: per-session lock file (`<chat_id>.lock`) held for the duration of an active session. Lease file (`<chat_id>.lease.json`) carries PID + generation token for staleness detection.

## Path Resolution (`paths.py`)

`StateRootPaths.from_root_dir(root)` resolves all standard paths relative to a state root. Used everywhere in state code to avoid hardcoded path construction.

The `.gitignore` is seeded on first init and updated non-destructively — only adds new required entries, never removes entries added by users.
