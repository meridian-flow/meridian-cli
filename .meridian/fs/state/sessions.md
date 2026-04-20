# Session Store

Source: `src/meridian/lib/state/session_store.py`

## What Sessions Track

A "session" in Meridian is a running harness instance (Claude Code, Codex, OpenCode) — typically a primary interactive launch. Sessions are distinct from spawns: spawns track individual task executions; sessions track the ongoing agent conversation context.

Meridian session IDs (`chat_id`) are `c1`, `c2`, `c3`, ... — allocated from a monotonic counter file (`.meridian/session-id-counter`). Harness session IDs are the native IDs from the underlying harness (e.g., a Claude UUID or Codex rollout UUID).

## Event Model

Events in `.meridian/sessions.jsonl`:

**`start`** — written when a session begins. Fields:
- `chat_id`, `harness`, `harness_session_id`, `execution_cwd`
- `model`, `agent`, `agent_path`, `skills`, `skill_paths`, `params`
- `session_instance_id` — generation token (random UUID per session start)
- `started_at`, `forked_from_chat_id`

**`stop`** — written when session ends. Fields: `chat_id`, `session_instance_id`, `stopped_at`.

**`update`** — non-terminal state change. Fields: `chat_id`, `harness_session_id`, `session_instance_id`, `active_work_id`.

`SessionRecord` is the projection: derived by replaying all events for a `chat_id`. The `harness_session_ids` tuple accumulates all harness IDs seen across updates (for tracking sessions that got new harness IDs during continuation).

## ID Allocation

`reserve_chat_id()` acquires `session_id_counter_flock` via `platform.locking.lock_file()`, reads the counter file, increments, and writes back atomically. Returns `c<N>`. The counter is seeded from the **highest existing `c<N>` chat ID** found in `sessions.jsonl` (via `_seed_counter_from_events()`) if the counter file doesn't exist (upgrade path) — not from the count of start events.

## Locking and Leases

Sessions hold two artifacts while active:

**Lock file** (`.meridian/sessions/<chat_id>.lock`): held for the session's lifetime by a dedicated helper in `session_store.py` (not `platform.locking.lock_file()`). Platform dispatch:
- **POSIX** (`_posix_acquire_session_lock()`): `fcntl.flock(fileno, LOCK_EX)` (blocking). Wraps in an inode-rematch loop — after acquiring the lock, verifies the handle's inode matches the path's current inode; retries if the file was unlinked between open and lock.
- **Windows** (`_win_acquire_session_lock()`): `msvcrt.locking(fileno, LK_LOCK, 1)` (blocking, 1-byte region). Same inode-rematch loop.
- Release: `_release_session_lock_handle()` dispatches to `LOCK_UN` (POSIX) or `LK_UNLCK` (Windows).

This is distinct from the **sessions flock** (`.meridian/sessions.flock`), which is acquired via `platform.locking.lock_file()` around all `append_event` + lease writes to serialize concurrent access to the JSONL store.

**Lease file** (`.meridian/sessions/<chat_id>.lease.json`): Written atomically alongside the start event. Contains:
- `owner_pid` — the PID of the process holding the session
- `session_instance_id` — random UUID, changes each time the session starts (generation token)

`start_session()`: acquires persistent lock (`_acquire_session_lock()`) first → then, under the sessions flock: appends `start` event and writes lease file. Registers the lock handle in `_SESSION_LOCK_HANDLES`.
`stop_session()`: under the sessions flock: appends `stop` event and unlinks lease file → then releases the persistent lock.

## Stale Session Cleanup

`cleanup_stale_sessions()` (called by `doctor`):
1. Collect stale candidates by attempting a non-blocking lock on each `<chat_id>.lock` (`_try_lock_nonblocking()` — POSIX `LOCK_EX|LOCK_NB`, Windows `LK_NBLCK`). Success means nobody is holding the lifetime lock → stale candidate. A live process keeps its lock held, so this is the primary liveness signal (no PID-alive check).
2. Under the sessions flock: for each candidate, read the lease and compare its `session_instance_id` against the event-projected record via `_generation_matches()`. Emit a `SessionStopEvent` for sessions with no `stopped_at` whose generation matches (or whose lease is absent). Decide which IDs to clean.
3. **Release all lock handles first** (separate pass before any file deletion) — Windows forbids deleting a file while an open handle to it exists.
4. Unlink `*.lock` and `*.lease.json` files for cleaned IDs.

`doctor --repair-orphans` also triggers orphan spawn repair at depth=0.

## Session Reference Resolution

`resolve_session_ref()` resolves several ref formats to a `SessionRecord`:
- Meridian chat ID: `c1`, `c2`, etc.
- Harness session ID: native UUID or opaque string (searched across all records)
- Spawn ID: `p1`, `p2`, etc. — resolved via the spawn's `chat_id`
- Untracked: if no match found, delegates to each harness's `owns_untracked_session()` to detect sessions not recorded in Meridian's own store

## Session Log (`ops/session_log.py`)

Reads harness-specific session/conversation files (e.g., Claude's JSONL transcript files in `~/.claude/projects/`). Compaction-aware:
- `-c 0` = latest compaction segment, `-c 1` = previous, etc.
- `-n <N>` = last N messages, `--offset` for paging
- Reports whether earlier/later segments exist

## Session Search (`ops/session_search.py`)

Scans all compaction segments for a session, highlights matches, emits navigation commands pointing to surrounding context segments.

## Work Attachment

`active_work_id` in session update events tracks which work item the session is currently attached to. Updated via `update_session_work_id()` when work context changes.
