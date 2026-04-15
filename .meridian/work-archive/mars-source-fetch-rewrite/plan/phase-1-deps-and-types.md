# Phase 1: Dependencies, Error Variants, and Type Changes

**Risk:** Low — mechanical changes, no logic  
**Design doc:** [overview.md](../design/overview.md)

## Scope

Swap dependencies in Cargo.toml, update error types, and change `AvailableVersion.commit_id` from `git2::Oid` to `String`. This phase makes the codebase compile without git2 but with stub implementations.

## Steps

1. **Cargo.toml**: Remove `git2`. Add `ureq = "3"`, `flate2 = "1"`, `tar = "0.4"`.

2. **src/error.rs**:
   - Remove `Git(#[from] git2::Error)` variant
   - Add:
     ```rust
     #[error("HTTP error: {url} — {status}: {message}")]
     Http { url: String, status: u16, message: String },
     
     #[error("git command failed: `{command}` — {message}")]
     GitCli { command: String, message: String },
     ```
   - Update `exit_code()`: both → 3
   - Update tests that reference `MarsError::Git`

3. **src/source/mod.rs**:
   - Change `AvailableVersion.commit_id` from `git2::Oid` to `String`
   - Replace `CacheDir` with `GlobalCache`:
     ```rust
     pub struct GlobalCache { pub root: PathBuf }
     impl GlobalCache {
         pub fn new() -> Result<Self, MarsError> // ~/.mars/cache/ or MARS_CACHE_DIR
         pub fn archives_dir(&self) -> PathBuf
         pub fn git_dir(&self) -> PathBuf
     }
     ```
   - Update `fetch_source()` and `list_versions()` signatures to take `&GlobalCache`

4. **src/resolve/mod.rs**: Update test mock — `git2::Oid::zero()` → `String::new()` or `"0".repeat(40)`

5. **src/sync/mod.rs**: Update `CacheDir::new(root)` calls → `GlobalCache::new()`

6. **src/source/git.rs**: Gut the file — keep `url_to_dirname()`, `FetchOptions`, `parse_semver_tag()` and their tests. Replace all git2 functions with `todo!()` stubs that have the new signatures. Remove git2 imports.

## Verification

- `cargo check` passes (stubs are `todo!()`, that's fine for type checking)
- `cargo test` — unit tests for `url_to_dirname`, `parse_semver_tag`, error types pass
- Integration tests will fail (expected — fetch is stubbed)

## Dependencies

None — this is the foundation phase.
