# Concurrency Model

## Problem

When several spawns start at once (e.g. a parent orchestrator fanning out
five coders in parallel) and the cache is stale, without coordination each
spawn independently hits the models.dev API. That's wasteful at best and
rate-limited at worst.

## Solution

`ensure_fresh` wraps the fetch step in an exclusive `flock` on
`.mars/.models-cache.lock`. The lock file is created on demand and never
removed — it's a stable coordination file, not a state file.

Mars already has a `FileLock` primitive in `src/fs/mod.rs`:

```rust
pub struct FileLock { /* ... */ }
impl FileLock {
    pub fn acquire(path: &Path) -> Result<FileLock, MarsError>;
    pub fn try_acquire(path: &Path) -> Result<Option<FileLock>, MarsError>;
}
```

`ensure_fresh` uses the blocking `acquire` — a late caller waits for the
first caller's fetch to complete, then re-reads a fresh file and returns
without fetching. This matches the behavior callers expect: "when I come
back from `ensure_fresh`, the cache is fresh."

## The Double-Check

```rust
// Outside the lock:
let (cache, is_fresh) = read_and_check_freshness()?;
if is_fresh && mode == Auto { return Ok(cache); }

// Acquire lock:
let _guard = FileLock::acquire(&lock_path)?;

// Re-check freshness under the lock:
let (cache, is_fresh) = read_and_check_freshness()?;
if is_fresh && mode == Auto {
    // Another process refreshed while we were waiting. Done.
    return Ok(cache);
}

// We're the first. Fetch.
let fresh = fetch_models()?;
write_cache(fresh)?;
```

Without the double-check, N waiting callers would each fetch after
acquiring the lock in sequence. With the double-check, only the first
caller fetches; everyone else inherits the result.

## Lock File Location

`.mars/.models-cache.lock` — dotfile prefix so it doesn't clutter `ls`.
Created next to `models-cache.json` so it shares filesystem semantics (both
live on the same volume; no cross-device renames).

The lock file content is irrelevant; its presence is the lock. Mars's
existing `FileLock::acquire` opens the file with `O_CREAT` and grabs an
exclusive `LOCK_EX`.

## Failure Modes

- **Lock acquisition fails** (I/O error creating the lock file): return
  the error. Callers surface it as a normal `MarsError::Io`. Rare; usually
  means `.mars/` isn't writable.
- **Process dies holding the lock**: kernel releases the fd on exit →
  `flock` is released automatically. No stale lock files.
- **NFS / network filesystems**: `flock` semantics are not guaranteed
  across NFS clients. Mars already accepts this constraint for its sync
  lock; we inherit the same trade-off. A comment on `FileLock::acquire`
  should note this.

## What We Are Not Protecting

- **Read races**: `read_cache` outside the lock is safe because
  `write_cache` uses `tmp+rename`, so readers either see the old full file
  or the new full file, never a torn write. The lock protects against
  *duplicate fetches*, not torn reads.
- **Different `mars_dir` paths**: each project has its own lock file. No
  cross-project contention.
