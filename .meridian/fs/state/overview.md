# State Domain Overview

## What It Is

Meridian state splits across two roots: repo-local `.meridian/` (committed scaffolding) and a user-level runtime directory keyed by project UUID (high-churn JSONL, artifacts). No database, no service, no hidden in-memory state. Both roots are files — `cat .meridian/spawns.jsonl | jq` still tells you everything on a machine that has the runtime state.

Source: `src/meridian/lib/state/` (paths, user_paths, atomic, locks, reaper, spawn store, session store)

## Split State Layout

### Repo `.meridian/` — committed scaffolding

```
.meridian/
  id                       # project UUID (36-char v4, no trailing newline; gitignored)
  id.lock                  # exclusive lock used during UUID generation
  .migrations.json         # repo-side migration tracking (gitignored)
  .gitignore               # seeded/maintained non-destructively
  fs/                      # agent-facing codebase mirror (committed)
  work/                    # active work scratch dirs (committed)
  work-archive/            # archived work scratch dirs (committed)
  work-items/              # mutable JSON per work item (committed)
    <work_id>.json
    work-items.rename.intent.json  # crash-safe rename intent (transient)
```

### User runtime `~/.meridian/projects/<uuid>/` — local, gitignored

```
~/.meridian/projects/<uuid>/
  spawns.jsonl             # all spawn events, append-only
  spawns.jsonl.flock       # fcntl lock for spawns.jsonl writes
  sessions.jsonl           # all session events, append-only
  sessions.jsonl.flock     # fcntl lock for sessions.jsonl writes
  session-id-counter       # monotonic counter for c1, c2, ...
  session-id-counter.flock
  sessions/                # per-session lock + lease files
    <chat_id>.lock
    <chat_id>.lease.json
  spawns/                  # per-spawn artifact dirs
    <spawn_id>/
      prompt.md
      report.md
      output.jsonl
      stderr.log
      params.json
      tokens.json
      heartbeat            # touched every 30s; reaper liveness signal
  artifacts/               # LocalStore blob store for spawn outputs
  cache/
    models.json            # model list cache (24h TTL)
  config.toml              # project config overrides
  .migrations.json         # user-side migration tracking
```

The split means projects can be moved, renamed, or duplicated without losing runtime history (runtime is keyed by UUID, not path). Repo state stays committable; runtime state stays local.

## User Root Resolution

`get_user_state_root()` in `user_paths.py` resolves the user root:

1. `MERIDIAN_HOME` env var (if set)
2. Platform default:
   - Unix/macOS: `~/.meridian/`
   - Windows: `%LOCALAPPDATA%\meridian\` (fallback: `%USERPROFILE%\AppData\Local\meridian\`)

## Runtime Override Precedence

`MERIDIAN_STATE_ROOT` overrides the runtime root entirely (bypasses UUID lookup):
- Absolute path → treated as the runtime root directly
- Relative path → resolved relative to repo root

`MERIDIAN_HOME` only affects the user root default (step 2 above). It does not override an absolute `MERIDIAN_STATE_ROOT`.

## Read vs Write Resolution

Bootstrap (UUID creation + runtime dir setup) is **skipped for read-only commands**. This prevents diagnostic/list commands from creating a UUID and runtime dir in untouched checkouts (CI, first-time tool runs, etc.).

| Resolver | Creates UUID? | Use when |
|----------|--------------|----------|
| `resolve_runtime_state_root(repo_root)` | No | Read paths; falls back to repo `.meridian/` if no UUID yet |
| `resolve_runtime_state_root_or_none(repo_root)` | No | Read paths where caller needs to know if uninitialized |
| `resolve_runtime_state_root_for_write(repo_root)` | Yes (under lock) | Write paths; creates UUID + runtime dir on first write |

UUID generation in `get_or_create_project_uuid()` is double-checked under `id.lock` (cross-process exclusive lock) so concurrent first-writes converge to the same UUID.

## Path Resolution (`paths.py`)

Two path model classes:

**`StatePaths`** — repo-owned paths only (`root_dir`, `id_file`, `fs_dir`, `work_dir`, `work_archive_dir`). Built by `StatePaths.from_root_dir()`.

**`StateRootPaths`** — runtime state paths (spawn/session indexes, per-spawn artifact dirs). Built by `StateRootPaths.from_root_dir()`. Still carries `fs_dir`, `work_dir`, `work_archive_dir` fields for transitional callers — these will be removed when all callers migrate to `StatePaths`. The authoritative repo paths come through `StatePaths`.

Convenience resolvers:

- `resolve_repo_state_paths(repo_root)` → `StatePaths` for repo `.meridian/` (ignores runtime overrides)
- `resolve_state_paths(repo_root)` → `StatePaths` honoring `MERIDIAN_STATE_ROOT`
- `resolve_cache_dir(repo_root)` → runtime `cache/` directory
- `resolve_fs_dir(repo_root)` → repo `fs/` directory
- `resolve_spawn_log_dir(repo_root, spawn_id)` → per-spawn artifact dir under runtime root

## Storage Patterns

**JSONL event stores** (spawns, sessions): append-only, crash-tolerant. Reads skip malformed lines. Writes go through `append_event()` under `fcntl.flock`. State is derived by replaying from the beginning. See `spawns.md` and `sessions.md` for store-specific detail.

**Per-file mutable JSON** (work items): one `<slug>.json` per item under `work-items/`. Atomic overwrites via `tmp + os.replace()`. Better for mutable records correlated with a directory that moves on rename.

**Artifact directories** (spawns): one directory per spawn under `spawns/<id>/`. Contains durable artifacts (stdout, stderr, report, params, tokens) plus the `heartbeat` coordination file touched every 30s. No PID files in artifact dirs — PID and status transitions live in the event stream. `heartbeat` is a live coordination artifact read by the reaper.

## Crash Tolerance

Crash-only design: every write path is safely restartable.
- JSONL appends: truncated lines skipped on read; earlier lines unaffected.
- Work item renames: `work-items.rename.intent.json` written before any rename begins; leftover intent replayed on startup/reconciliation.
- Atomic writes: any replaced file goes through `tmp + os.replace()` (via `atomic_write_text()` in `state/atomic.py`).
- Spawn reconciliation: active spawns auto-finalized on every read path (list, show, wait, dashboard). Reaper skips nested invocations (`MERIDIAN_DEPTH > 0`), checks heartbeat recency (primary), `runner_pid` psutil liveness (secondary, skipped for `finalizing`). See `spawns.md` for full reaper logic.

## Locking

- JSONL stores: `fcntl.flock(LOCK_EX)` on `.flock` sidecar. Reentrant within a thread (thread-local depth counter).
- Session locks: per-session lock file (`<chat_id>.lock`) held for active session duration. Lease file (`<chat_id>.lease.json`) carries PID + generation token for staleness detection.
- UUID creation: `id.lock` exclusive lock; double-checked read inside lock.

## Migrations

State transformation scripts live in top-level `migrations/`, completely decoupled from runtime code. Each migration is a versioned directory (`vNNN_short_name/`) containing `README.md`, `check.py`, `migrate.py`, and optional `rollback.py`. `registry.toml` lists migrations with status `stub` (not yet implemented) or `ready` (implemented).

Tracking splits across two files, mirroring the state split:
- `.meridian/.migrations.json` — repo-side (gitignored)
- `~/.meridian/projects/<uuid>/.migrations.json` — user-side

Migrations run manually via `python migrations/vNNN/migrate.py <repo_root>`. No auto-run; no CLI integration yet. See `migrations/README.md` for the framework, `migrations/registry.toml` for the current migration list.

**v001 `uuid_state_split`** (introduced 0.0.34) — moves legacy runtime state from repo `.meridian/` to user `~/.meridian/projects/<uuid>/`. Currently a stub; not yet implemented.
