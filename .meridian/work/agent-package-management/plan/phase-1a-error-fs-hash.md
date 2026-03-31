# Phase 1a: Error Types + FS Primitives + Hash

## Scope

Implement three foundational modules that every other module depends on: structured error types (`error.rs`), atomic filesystem operations (`fs/`), and checksum computation (`hash/`). These are pure utilities with no business logic — the lowest layer of the dependency graph.

## Why This Order

Every module in the crate uses `MarsError` for error propagation. The `fs/` module provides atomic writes and file locking used by `config/`, `lock/`, `source/`, and `sync/apply.rs`. The `hash/` module provides checksum computation used by `merge/`, `sync/diff.rs`, and `lock/`. Implementing these first means Phase 1b and all Round 3 phases have stable primitives.

## Files to Modify

### `src/error.rs` — Structured Error Types

Implement the full `MarsError` enum from the architecture doc:

```rust
#[derive(Debug, thiserror::Error)]
pub enum MarsError {
    #[error("config error: {0}")]
    Config(#[from] ConfigError),

    #[error("lock error: {0}")]
    Lock(#[from] LockError),

    #[error("source error: {source_name}: {message}")]
    Source { source_name: String, message: String },

    #[error("resolution failed: {0}")]
    Resolution(#[from] ResolutionError),

    #[error("merge conflict in {path}")]
    Conflict { path: String },

    #[error("{item} is provided by both `{source_a}` and `{source_b}`")]
    Collision { item: String, source_a: String, source_b: String },

    #[error("validation: {0}")]
    Validation(#[from] ValidationError),

    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("git error: {0}")]
    Git(#[from] git2::Error),
}
```

Also define per-module error enums: `ConfigError`, `LockError`, `ResolutionError`, `ValidationError`. Each should have concrete variants (not just string wrappers) so the CLI can pattern-match for exit codes.

Define a `pub type Result<T> = std::result::Result<T, MarsError>;` convenience alias.

### `src/fs/mod.rs` — Atomic FS Operations

```rust
/// Atomic file write: write to temp file in same dir, fsync, rename
pub fn atomic_write(dest: &Path, content: &[u8]) -> Result<()>;

/// Atomic directory install: copy to temp dir in same parent, rename
pub fn atomic_install_dir(src: &Path, dest: &Path) -> Result<()>;

/// Remove a file or directory (skills are dirs)
pub fn remove_item(path: &Path, kind: ItemKind) -> Result<()>;

/// Advisory file lock via flock. Drop releases the lock.
pub struct FileLock { /* fd held open */ }
impl FileLock {
    pub fn acquire(lock_path: &Path) -> Result<Self>;
    pub fn try_acquire(lock_path: &Path) -> Result<Option<Self>>;
}
```

Implementation details:
- `atomic_write`: Use `tempfile::NamedTempFile` in the **same directory** as `dest` (same filesystem guarantees atomic rename). Write content → `fsync` → `persist()` (which does the rename).
- `atomic_install_dir`: Create temp dir in same parent via `tempfile::TempDir`, copy tree recursively, then `std::fs::rename`.
- `FileLock`: Use `std::fs::File::open` + `libc::flock(LOCK_EX)` on Unix. The `Drop` impl closes the fd (which releases the flock). Create parent dirs if needed.
- `remove_item`: `std::fs::remove_file` for Agent, `std::fs::remove_dir_all` for Skill.

### `src/hash/mod.rs` — Checksum Computation

```rust
/// Compute SHA-256 checksum as "sha256:<hex>" string
pub fn compute_hash(path: &Path, kind: ItemKind) -> Result<String>;

/// Compute SHA-256 of raw bytes
pub fn hash_bytes(content: &[u8]) -> String;
```

- For `ItemKind::Agent` (single file): SHA-256 of file content.
- For `ItemKind::Skill` (directory): Walk directory, collect `(relative_path, file_sha256)` pairs, sort lexicographically by path, concatenate `"path:hash\n"` strings, SHA-256 the result. Deterministic regardless of filesystem ordering.
- Output format: `"sha256:<64-char-hex>"`.

## Dependencies

- Requires: Phase 0 (compiling crate with stubs, `ItemKind` defined in `lock/mod.rs`)
- Produces: `MarsError`, `Result<T>`, `atomic_write`, `FileLock`, `compute_hash` — used by every subsequent phase
- Independent of: Phase 1b (can run in parallel)

## Interface Contract

Other modules import:
- `crate::error::{MarsError, Result, ConfigError, LockError, ...}`
- `crate::fs::{atomic_write, atomic_install_dir, remove_item, FileLock}`
- `crate::hash::{compute_hash, hash_bytes}`
- `crate::lock::ItemKind` (defined in Phase 0 stubs, used by hash and fs)

## Patterns to Follow

- Use `thiserror` derive macros exclusively — no manual `impl Display` or `impl Error`.
- `#[from]` for automatic conversions from sub-errors to `MarsError`.
- Structured error variants with named fields, not `String` wrappers, so CLI can match on them.

## Verification Criteria

- [ ] `cargo build` succeeds
- [ ] Unit tests for `hash/`:
  - Known content → known SHA-256 hex string
  - Directory hash is deterministic (same content, different creation order → same hash)
  - Empty file → valid hash
- [ ] Unit tests for `fs/`:
  - `atomic_write` creates the file with correct content
  - `atomic_write` to a path where parent dir exists works
  - `FileLock::acquire` returns a lock, second `try_acquire` returns `None`
  - `remove_item` removes files and directories
- [ ] Unit tests for `error.rs`:
  - `MarsError::from(std::io::Error)` works
  - Error messages format correctly
- [ ] `cargo clippy -- -D warnings` passes
- [ ] `cargo test` — all tests pass

## Constraints

- Do NOT use `anyhow` anywhere in the library. `thiserror` only.
- `atomic_write` temp file MUST be in the same directory as destination (cross-filesystem rename is not atomic).
- `FileLock` uses advisory locking only — it's not a security mechanism, just coordination.
- `hash_bytes` must return lowercase hex.
